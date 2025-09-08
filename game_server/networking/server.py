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
    print(f"❌ Proto import failed at server: {e}")
    sys.exit(1)

from .matchmaking import ServerMatchmaker, MatchState

logger = logging.getLogger(__name__)

class BotConnection:
    """Represents a connected bot client"""
    def __init__(self, bot_id: int, player_id: str, match_id: str):
        self.bot_id = bot_id
        self.player_id = player_id
        self.match_id = match_id
        self.is_active = True
        self.last_action_time = asyncio.get_event_loop().time()
        self.connection_time = asyncio.get_event_loop().time()

class ArenaBattleServicer(arena_pb2_grpc.ArenaBattleServiceServicer):
    """gRPC service with PvP-only matchmaking"""
    
    def __init__(self, game_engine):
        self.game_engine = game_engine
        self.matchmaker = ServerMatchmaker(min_players=2, max_players=8)
        self.connections: Dict[int, BotConnection] = {}
        self.waiting_connections: Dict[str, BotConnection] = {}  # player_id -> connection
        
    async def RegisterBot(self, request, context):
        """Register bot for PvP matchmaking"""
        try:
            player_id = request.player_id
            bot_name = request.bot_name
            
            logger.info(f"🤖 Bot registration request: {player_id} ({bot_name})")
            
            # Register with matchmaker
            match_result = self.matchmaker.register_player(player_id, bot_name)
            
            if not match_result['success']:
                logger.warning(f"❌ Registration failed: {match_result['message']}")
                return arena_pb2.RegistrationResponse(
                    success=False,
                    message=match_result['message'],
                    bot_id=0
                )
            
            # Create bot in game engine
            bot_id = self.game_engine.game_state.add_bot(player_id, bot_name)
            
            # Get match info
            match_id = match_result['match_id']
            match_info = self.matchmaker.get_match_info(player_id)
            
            # Log registration success
            logger.info(f"✅ {player_id} registered → Bot ID: {bot_id}")
            logger.info(f"📊 Match: {match_id} ({match_result['players_in_match']} players)")
            logger.info(f"🎯 Status: {match_result['message']}")
            
            return arena_pb2.RegistrationResponse(
                success=True,
                message=match_result['message'],
                bot_id=bot_id
            )
            
        except Exception as e:
            logger.error(f"💥 Registration error: {e}")
            return arena_pb2.RegistrationResponse(
                success=False,
                message=f"Registration failed: {str(e)}",
                bot_id=0
            )
    
    async def PlayGame(self, request_iterator, context):
        """Main game streaming for PvP battles"""
        bot_connection = None
        
        try:
            # Find unconnected bot and establish connection
            bot_id = None
            player_id = None
            
            # Find available bot
            for bid, bot in self.game_engine.game_state.bots.items():
                if bid not in self.connections:
                    bot_id = bid
                    player_id = bot.player_id
                    break
            
            if bot_id is None:
                logger.error("❌ No available bot for PlayGame connection")
                return
            
            # Get match info
            match_info = self.matchmaker.get_match_info(player_id)
            if 'error' in match_info:
                logger.error(f"❌ No match found for player {player_id}")
                return
            
            match_id = match_info['match_id']
            match_state = match_info['is_active']
            
            # Create connection
            bot_connection = BotConnection(bot_id, player_id, match_id)
            self.connections[bot_id] = bot_connection
            
            logger.info(f"🔌 Bot {bot_id} ({player_id}) connected to match {match_id}")
            
            # Check if match is ready to start
            if match_state:
                logger.info(f"⚔️ {player_id} joining active PvP battle")
            else:
                logger.info(f"⏳ {player_id} waiting for more players...")
            
            # Start observation sender
            observation_task = asyncio.create_task(
                self._send_observations(bot_connection, context)
            )
            
            # Process actions from client
            try:
                async for action_request in request_iterator:
                    await self._process_action(action_request, bot_id)
                    bot_connection.last_action_time = asyncio.get_event_loop().time()
                    
            except Exception as e:
                logger.error(f"💥 Action processing error for bot {bot_id}: {e}")
            
            # Wait for observation task to complete
            await observation_task
            
        except Exception as e:
            logger.error(f"💥 PlayGame error: {e}")
        finally:
            # Cleanup connection
            if bot_connection:
                await self._cleanup_connection(bot_connection)
    
    async def _process_action(self, action_request, bot_id: int):
        """Process action from bot"""
        try:
            # Check if bot's match is active
            connection = self.connections.get(bot_id)
            if not connection:
                return
            
            match_info = self.matchmaker.get_match_info(connection.player_id)
            if 'error' in match_info or not match_info.get('is_active', False):
                # Match not active yet, ignore actions but keep connection alive
                return
            
            # Process action normally for active matches
            action = {
                'thrust': {
                    'x': action_request.thrust.x,
                    'y': action_request.thrust.y
                },
                'aim_angle': action_request.aim_angle,
                'fire': action_request.fire
            }
            
            self.game_engine.physics.apply_bot_action(bot_id, action)
            
        except Exception as e:
            logger.error(f"💥 Action processing error: {e}")
    
    async def _send_observations(self, connection: BotConnection, context):
        """Send observations to connected bot"""
        try:
            while connection.is_active:
                # Check if match is active
                match_info = self.matchmaker.get_match_info(connection.player_id)
                is_match_active = match_info.get('is_active', False) if 'error' not in match_info else False
                
                if is_match_active:
                    # Send real game observations
                    obs_data = self.game_engine.game_state.get_observation(connection.bot_id)
                    
                    if obs_data:
                        observation = arena_pb2.Observation(
                            tick=obs_data['tick'],
                            self_pos=arena_pb2.Vec2(
                                x=obs_data['self_pos']['x'],
                                y=obs_data['self_pos']['y']
                            ),
                            self_hp=obs_data['self_hp'],
                            enemy_pos=arena_pb2.Vec2(
                                x=obs_data['enemy_pos']['x'],
                                y=obs_data['enemy_pos']['y']
                            ),
                            enemy_hp=obs_data['enemy_hp'],
                            has_line_of_sight=obs_data['has_line_of_sight'],
                            arena_width=obs_data['arena_width'],
                            arena_height=obs_data['arena_height']
                        )
                        
                        # Add bullets
                        for bullet in obs_data['bullets']:
                            observation.bullets.append(
                                arena_pb2.Vec2(x=bullet['x'], y=bullet['y'])
                            )
                        
                        # Add walls
                        observation.walls.extend(obs_data['walls'])
                        
                        await context.write(observation)
                else:
                    # Send waiting state observation (neutral state)
                    waiting_obs = arena_pb2.Observation(
                        tick=0,
                        self_pos=arena_pb2.Vec2(x=400.0, y=300.0),  # Center position
                        self_hp=100.0,
                        enemy_pos=arena_pb2.Vec2(x=0.0, y=0.0),     # No enemy
                        enemy_hp=0.0,
                        has_line_of_sight=False,
                        arena_width=800.0,
                        arena_height=600.0
                    )
                    await context.write(waiting_obs)
                
                # Control update rate
                await asyncio.sleep(1/60)  # 60 FPS
                
        except Exception as e:
            logger.error(f"💥 Observation sending error: {e}")
            connection.is_active = False
    
    async def _cleanup_connection(self, connection: BotConnection):
        """Clean up when connection ends"""
        try:
            connection.is_active = False
            
            # Remove from connections
            if connection.bot_id in self.connections:
                del self.connections[connection.bot_id]
            
            # Remove from matchmaker
            removed = self.matchmaker.remove_player(connection.player_id)
            
            # Remove bot from game
            self.game_engine.game_state.remove_bot(connection.bot_id)
            
            connection_time = asyncio.get_event_loop().time() - connection.connection_time
            
            logger.info(f"🚪 Bot {connection.bot_id} ({connection.player_id}) disconnected")
            logger.info(f"   Connection duration: {connection_time:.1f}s")
            
            if removed:
                logger.info(f"   Removed from match {connection.match_id}")
            
        except Exception as e:
            logger.error(f"💥 Cleanup error: {e}")
    
    async def GetStats(self, request, context):
        """Get match and player statistics"""
        try:
            player_id = request.player_id
            
            # Get matchmaker stats
            matchmaker_stats = self.matchmaker.get_statistics()
            
            # Get player-specific stats if available
            match_info = self.matchmaker.get_match_info(player_id)
            
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
            
            return arena_pb2.GameStats(
                total_kills=player_kills,
                total_deaths=player_deaths,
                kill_death_ratio=player_kills / max(player_deaths, 1),
                games_played=matchmaker_stats['total_matches_created'],
                average_survival_time=45.0  # Placeholder
            )
            
        except Exception as e:
            logger.error(f"💥 GetStats error: {e}")
            return arena_pb2.GameStats(
                total_kills=0,
                total_deaths=0,
                kill_death_ratio=0.0,
                games_played=0,
                average_survival_time=0.0
            )

async def run_server(game_engine, port=50051):
    """Run the gRPC server with PvP-only matchmaking"""
    server = grpc.aio.server(futures.ThreadPoolExecutor(max_workers=10))
    
    servicer = ArenaBattleServicer(game_engine)
    arena_pb2_grpc.add_ArenaBattleServiceServicer_to_server(servicer, server)
    
    listen_addr = f'[::]:{port}'
    server.add_insecure_port(listen_addr)
    
    logger.info(f"🚀 Arena Battle Server (PvP-Only) starting on {listen_addr}")
    logger.info(f"⚔️ Minimum {servicer.matchmaker.min_players} players required to start matches")
    await server.start()
    
    try:
        await server.wait_for_termination()
    except KeyboardInterrupt:
        logger.info("🛑 gRPC Server stopped")
        await server.stop(5)