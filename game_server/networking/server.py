import asyncio
import grpc
import logging
import sys
import os
from typing import Dict, Set
from concurrent import futures

# Path fix
current_dir = os.path.dirname(__file__)
project_root = os.path.dirname(os.path.dirname(current_dir))
proto_dir = os.path.join(project_root, "proto")
sys.path.insert(0, proto_dir)

try:
    from proto import arena_pb2, arena_pb2_grpc
    print("✅ Proto import successful in server.py")
except ImportError as e:
    print(f"⚠️ Proto import failed at server: {e}")
    sys.exit(1)

from .room_manager import RoomManager
from game_server.engine.game_state import DummyBot
# Import JSON logger
from ..logging.json_logger import ServerJSONLogger, observation_to_dict, action_to_dict

logger = logging.getLogger(__name__)

class BotConnection:
    """Represents a connected bot client with timing info"""
    def __init__(self, bot_id: int, player_id: str, room_id: str):
        self.bot_id = bot_id
        self.player_id = player_id
        self.room_id = room_id  # Changed from match_id
        self.is_active = True
        self.last_action_time = asyncio.get_event_loop().time()
        self.connection_time = asyncio.get_event_loop().time()

class ArenaBattleServicer(arena_pb2_grpc.ArenaBattleServiceServicer):
    """gRPC service với JSON logging cho tất cả gRPC data"""
    
    def __init__(self, game_engine, enable_logging=True):
        self.game_engine = game_engine
        
        try:
            self.room_manager = RoomManager()
        except Exception as e:
            import traceback
            traceback.print_exc()
            
        self.connections: Dict[int, BotConnection] = {}
        self.waiting_connections: Dict[str, BotConnection] = {}
        
        # Initialize JSON logger
        self.json_logger = None
        if enable_logging:
            self.json_logger = ServerJSONLogger(
                log_dir="logs/server_grpc_data", 
                rotation_minutes=5
            )
            logger.info("📝 Server JSON logging enabled")
    async def RegisterBot(self, request, context):
        """Register bot with JSON logging"""
        try:
            player_id = request.player_id
            bot_name = request.bot_name
            
            logger.info(f"🤖 Bot registration request: {player_id} ({bot_name})")
            
            # Parse room info from bot_name hack
            parts = bot_name.split('|')
            if len(parts) == 3:
                actual_bot_name, room_id, room_password = parts
            else:
                if self.json_logger:
                    self.json_logger.log_bot_registration(
                        player_id, bot_name, 0, False, "❌ Invalid room connection format"
                    )
                return arena_pb2.RegistrationResponse(
                    success=False, message="❌ Invalid room connection format", bot_id=0
                )

            room_result = self.room_manager.join_room(player_id, actual_bot_name, room_id, room_password)

            if not room_result['success']:
                if self.json_logger:
                    self.json_logger.log_bot_registration(
                        player_id, actual_bot_name, 0, False, room_result['message']
                    )
                return arena_pb2.RegistrationResponse(
                    success=False, message=room_result['message'], bot_id=0
                )
            
            # Create bot in game engine using RoomManager's bot ID
            # Get or create room state
            room_state = self.game_engine.get_or_create_room_state(room_id, room_result['arena_config'])
            
            # ⭐ Debug: Log before adding bot
            logger.info(f"🔍 DEBUG: About to add bot {player_id} with bot_id={room_result['bot_id']}")
            logger.info(f"🔍 DEBUG: Room state before add: {len(room_state.bots)} bots")
            
            # ⭐ FIX: Always add AI bot FIRST
            bot_id = room_result['bot_id']
            room_state.add_bot(player_id, actual_bot_name, room_result['arena_config'], room_id, bot_id)
            
            logger.info(f"🔍 DEBUG: Room state after add AI bot: {len(room_state.bots)} bots")
            logger.info(f"🔍 DEBUG: Bot IDs in room: {list(room_state.bots.keys())}")
            
            # ⭐ Then spawn dummy bots if PvE room
            room_info = self.room_manager.get_room_info(room_id)
            if room_info.get('player_count', 0) == 1:  # First player in room
                room = self.room_manager.rooms.get(room_id)
                if room and room.is_pve_mode:
                    logger.info(f"🎯 PvE room detected - spawning {room.initial_dummy_count} dummy bots")
                    self.room_manager.spawn_initial_dummy_bots(room_id, room_state)
                    logger.info(f"🔍 DEBUG: After dummy spawn: {len(room_state.bots)} bots")
            
            logger.info(f"🔍 Final bot count in room {room_id}: {len(room_state.bots)}")
            logger.info(f"🔍 Final bot details:")
            for bid, bot in room_state.bots.items():
                bot_type = "DUMMY" if isinstance(bot, DummyBot) else "AI"
                logger.info(f"   Bot {bid}: {bot.name} ({bot_type})")
            players_count = room_result['players_in_room']
            max_players = room_result.get('max_players', 4)  # fallback to 4
            
            if players_count >= 2:
                status_msg = f"Joined {room_id} ({players_count}/{max_players}) - ⚔️ Combat active!"
            else:
                needed = 2 - players_count
                status_msg = f"Joined {room_id} ({players_count}/{max_players}) - ⏳ Waiting for {needed} more player(s)..."
            # Log successful registration
            if self.json_logger:
                self.json_logger.log_bot_registration(
                    player_id, actual_bot_name, bot_id, True, room_result['message']
                )
                
                self.json_logger.log_match_event(room_result['room_id'], "player_assigned", {
                    "player_id": player_id,
                    "bot_id": bot_id,
                    "bot_name": actual_bot_name,
                    "players_in_room": room_result['players_in_room'],
                    "room_id": room_result['room_id']
                })
            
            # Log registration success
            logger.info(f"✅ {player_id} registered → Bot ID: {bot_id}")
            logger.info(f"🏠 Room: {room_result['room_id']} ({room_result['players_in_room']} players)")
            logger.info(f"🎯 Status: {room_result['message']}")
            
            return arena_pb2.RegistrationResponse(
                success=True,
                message=status_msg,
                bot_id=room_result['bot_id']
            )
            
        except Exception as e:
            logger.error(f"💥 Registration error: {e}")
            
            # Log registration error
            if self.json_logger:
                self.json_logger.log_game_event("registration_error", {
                    "player_id": player_id if 'player_id' in locals() else 'unknown',
                    "error": str(e)
                })
            
            return arena_pb2.RegistrationResponse(
                success=False,
                message=f"Registration failed: {str(e)}",
                bot_id=0
            )
    
    async def PlayGame(self, request_iterator, context):
        """Main game streaming với comprehensive JSON logging"""
        bot_connection = None
        
        try:
            # Find available bot and establish connection
            bot_id = None
            player_id = None

            # First, find which player needs connection by checking all room states
            for room_id, room_state in self.game_engine.room_states.items():
                for bid, bot in room_state.bots.items():
                    if bid not in self.connections:
                        bot_id = bid
                        player_id = bot.player_id
                        break
                if bot_id:
                    break
            
            if bot_id is None:
                logger.error("⚠️ No available bot for PlayGame connection")
                return
            
            # ⭐ FIX: Dummy bots don't need gRPC connection
            if player_id.startswith("dummy_"):
                logger.debug(f"🤖 Dummy bot {bot_id} ({player_id}) - controlled by server")
                return
            
            # Get room info
            player_room_id = self.room_manager.player_to_room.get(player_id, "")
            
            # ⭐ FIX: Skip room check for dummy bots
            if player_id.startswith("dummy_"):
                logger.debug(f"🤖 Dummy bot {player_id} - skip room tracking")
                return  # Dummy bots don't need PlayGame connection
            
            room_info = self.room_manager.get_room_info(player_room_id)
            if 'error' in room_info:
                logger.error(f"⚠️ No room found for player {player_id}")
                return
            
            room_id = room_info['room_id']
            room_active = room_info['is_active']
            
            # Create connection
            bot_connection = BotConnection(bot_id, player_id, room_id)
            self.connections[bot_id] = bot_connection
            
            logger.info(f"🔌 Bot {bot_id} ({player_id}) connected to room {room_id}")
            
            # Log connection event
            if self.json_logger:
                self.json_logger.log_game_event("bot_connected", {
                    "bot_id": bot_id,
                    "player_id": player_id,
                    "room_id": room_id,
                    "room_active": room_active
                })
            
            # Check if room is ready to start
            if room_active:
                logger.info(f"⚔️ {player_id} joining active room battle")
            else:
                logger.info(f"⏳ {player_id} waiting for more players...")
            
            # Start observation sender với logging
            observation_task = asyncio.create_task(
                self._send_observations_with_logging(bot_connection, context)
            )
            
            # Process actions from client với logging
            try:
                async for action_request in request_iterator:
                    await self._process_action_with_logging(action_request, bot_id, player_id)
                    bot_connection.last_action_time = asyncio.get_event_loop().time()
                    
            except Exception as e:
                logger.error(f"💥 Action processing error for bot {bot_id}: {e}")
            
            # Wait for observation task to complete
            await observation_task
            
        except Exception as e:
            logger.error(f"💥 PlayGame error: {e}")
            
            # Log PlayGame error
            if self.json_logger and bot_connection:
                self.json_logger.log_game_event("playgame_error", {
                    "bot_id": bot_connection.bot_id,
                    "player_id": bot_connection.player_id,
                    "error": str(e)
                })
        finally:
            # Cleanup connection
            if bot_connection:
                await self._cleanup_connection_with_logging(bot_connection)
    
    async def _process_action_with_logging(self, action_request, bot_id: int, player_id: str):
        """Process action với JSON logging"""
        try:
            # Log received action
            if self.json_logger:
                action_dict = action_to_dict(action_request)
                self.json_logger.log_action_received(bot_id, player_id, action_dict)
            
            # Check if bot's room is active
            connection = self.connections.get(bot_id)
            if not connection:
                return

            player_room_id = self.room_manager.player_to_room.get(connection.player_id, "")
            
            # FIX: Handle case where room not found
            if not player_room_id:
                logger.warning(f"⚠️ Bot {bot_id} ({player_id}) has no room assignment")
                return  # ✅ SỬA THÀNH return
            
            room_info = self.room_manager.get_room_info(player_room_id)
            
            # Process action for the correct room
            action = {
                'thrust': {
                    'x': action_request.thrust.x,
                    'y': action_request.thrust.y
                },
                'aim_angle': action_request.aim_angle,
                'fire': action_request.fire
            }

            # Apply action to correct room's physics engine
            if player_room_id and player_room_id in self.game_engine.physics_engines:
                self.game_engine.physics_engines[player_room_id].apply_bot_action(bot_id, action)
            
        except Exception as e:
            logger.error(f"💥 Action processing error: {e}")
            
            # Log action processing error
            if self.json_logger:
                self.json_logger.log_game_event("action_processing_error", {
                    "bot_id": bot_id,
                    "player_id": player_id,
                    "error": str(e)
                })
    
    async def _send_observations_with_logging(self, connection: BotConnection, context):
        """Send observations with IMPROVED waiting logic"""
        try:
            observation_count = 0
            last_status_log = 0
            
            while connection.is_active:
                # Get room status
                player_room_id = self.room_manager.player_to_room.get(connection.player_id, "")
                room_info = self.room_manager.get_room_info(player_room_id)
                is_room_active = room_info.get('is_active', False) if 'error' not in room_info else False
                
                if is_room_active:
                    # ACTIVE COMBAT - Send real observations
                    room_state = self.game_engine.get_room_state(player_room_id)
                    if room_state:
                        obs_data = room_state.get_observation(connection.bot_id)
                        
                        if obs_data:
                            observation = arena_pb2.Observation(
                                tick=obs_data['tick'],
                                self_pos=arena_pb2.Vec2(x=obs_data['self_pos']['x'], y=obs_data['self_pos']['y']),
                                self_hp=obs_data['self_hp'],
                                enemy_pos=arena_pb2.Vec2(x=obs_data['enemy_pos']['x'], y=obs_data['enemy_pos']['y']),
                                enemy_hp=obs_data['enemy_hp'],
                                has_line_of_sight=obs_data['has_line_of_sight'],
                                arena_width=obs_data['arena_width'],
                                arena_height=obs_data['arena_height']
                            )
                            
                            # Add bullets and walls
                            for bullet in obs_data['bullets']:
                                observation.bullets.append(arena_pb2.Vec2(x=bullet['x'], y=bullet['y']))
                            observation.walls.extend(obs_data['walls'])
                            
                            await context.write(observation)
                            
                else:
                    # ⏳ WAITING STATE - Send stable waiting observations
                    player_count = room_info.get('player_count', 1)
                    
                    # Log waiting status periodically (every 5 seconds)
                    if observation_count % 300 == 0:  # 300 frames = 5 seconds at 60fps
                        logger.info(f"⏳ {connection.player_id} waiting in {player_room_id} ({player_count}/2 players)")
                    
                    # Send stable waiting observation
                    waiting_obs = arena_pb2.Observation(
                        tick=observation_count,
                        self_pos=arena_pb2.Vec2(x=400.0, y=300.0),  # Center position
                        self_hp=100.0,  # Full health
                        enemy_pos=arena_pb2.Vec2(x=0.0, y=0.0),    # No enemy
                        enemy_hp=0.0,   # No enemy
                        has_line_of_sight=False,
                        arena_width=800.0,
                        arena_height=600.0
                    )
                    await context.write(waiting_obs)
                
                observation_count += 1
                
                # IMPORTANT: Stable frame rate
                await asyncio.sleep(1/60)  # 60 FPS
                
        except Exception as e:
            logger.error(f"💥 Observation sending error: {e}")
            connection.is_active = False
            
            # Log observation sending error
            if self.json_logger:
                self.json_logger.log_game_event("observation_sending_error", {
                    "bot_id": connection.bot_id,
                    "player_id": connection.player_id,
                    "observation_count": observation_count,
                    "error": str(e)
                })
    
    async def _cleanup_connection_with_logging(self, connection: BotConnection):
        """Clean up connection với JSON logging"""
        try:
            connection.is_active = False
            
            # Calculate connection duration
            connection_duration = asyncio.get_event_loop().time() - connection.connection_time
            
            # Remove from connections
            if connection.bot_id in self.connections:
                del self.connections[connection.bot_id]
            
            # Remove from room manager
            removed = self.room_manager.leave_room(connection.player_id)

            # Remove bot from correct room state
            player_room_id = self.room_manager.player_to_room.get(connection.player_id)
            if player_room_id:
                room_state = self.game_engine.get_room_state(player_room_id)
                if room_state:
                    room_state.remove_bot(connection.bot_id)
            
            # Log disconnection
            if self.json_logger:
                self.json_logger.log_bot_disconnect(
                    connection.bot_id,
                    connection.player_id,
                    connection_duration
                )
            
            logger.info(f"🚪 Bot {connection.bot_id} ({connection.player_id}) disconnected")
            logger.info(f"   Connection duration: {connection_duration:.1f}s")
            
            if removed:
                logger.info(f"   Removed from room {connection.room_id}")
            
        except Exception as e:
            logger.error(f"💥 Cleanup error: {e}")
            
            # Log cleanup error
            if self.json_logger:
                self.json_logger.log_game_event("cleanup_error", {
                    "bot_id": connection.bot_id,
                    "player_id": connection.player_id,
                    "error": str(e)
                })
    
    async def GetStats(self, request, context):
        """Get statistics với logging"""
        try:
            player_id = request.player_id
            
            # Get room stats
            room_stats = self.room_manager.get_statistics()
            
            # Get player-specific stats if available
            player_room_id = self.room_manager.player_to_room.get(player_id, "")
            room_info = self.room_manager.get_room_info(player_room_id) if player_room_id else {}
            
            # Get game stats
            game_stats = self.game_engine.game_state.get_game_stats()
            
            # Find player's bot for kill/death stats
            player_kills = 0
            player_deaths = 0
            
            for bot in self.game_engine.game_state.bots.values():
                if bot.player_id == player_id:
                    player_kills = bot.kills
                    player_deaths = bot.deaths
                    break
            
            # Log stats request
            if self.json_logger:
                self.json_logger.log_game_event("stats_request", {
                    "player_id": player_id,
                    "player_stats": {
                        "kills": player_kills,
                        "deaths": player_deaths,
                        "kd_ratio": player_kills / max(player_deaths, 1)
                    },
                    "server_stats": room_stats
                })
            
            return arena_pb2.GameStats(
                total_kills=player_kills,
                total_deaths=player_deaths,
                kill_death_ratio=player_kills / max(player_deaths, 1),
                games_played=room_stats['total_players_served'],
                average_survival_time=45.0  # Placeholder
            )
            
        except Exception as e:
            logger.error(f"💥 GetStats error: {e}")
            
            # Log stats error
            if self.json_logger:
                self.json_logger.log_game_event("stats_error", {
                    "player_id": request.player_id,
                    "error": str(e)
                })
            
            return arena_pb2.GameStats(
                total_kills=0,
                total_deaths=0,
                kill_death_ratio=0.0,
                games_played=0,
                average_survival_time=0.0
            )
    
    def close_logger(self):
        """Close JSON logger"""
        if self.json_logger:
            self.json_logger.close()

async def run_server(game_engine, port=50051, enable_logging=True):
    """Run the gRPC server với JSON logging"""
    
    server = grpc.aio.server(futures.ThreadPoolExecutor(max_workers=10))
    servicer = ArenaBattleServicer(game_engine, enable_logging=enable_logging)
    arena_pb2_grpc.add_ArenaBattleServiceServicer_to_server(servicer, server)
    
    listen_addr = f'[::]:{port}'
    server.add_insecure_port(listen_addr)
    
    logger.info(f"🚀 Arena Battle Server (Room-Based) starting on {listen_addr}")
    
    try:
        await server.start()
        # Small delay to ensure server is ready
        await asyncio.sleep(0.1)
        await server.wait_for_termination()
    except Exception as e:
        raise
    except KeyboardInterrupt:
        logger.info("🛑 gRPC Server stopped")
        servicer.close_logger()
        await server.stop(5)