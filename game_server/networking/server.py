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
    print("Proto import successful in server.py")
except ImportError as e:
    print(f"Proto import failed: {e}")
    sys.exit(1)

from .matchmaking import ServerMatchmaker

logger = logging.getLogger(__name__)

class BotConnection:
    """Represents a connected bot client"""
    def __init__(self, bot_id: int, player_id: str):
        self.bot_id = bot_id
        self.player_id = player_id
        self.is_active = True
        self.last_action_time = asyncio.get_event_loop().time()

class ArenaBattleServicer(arena_pb2_grpc.ArenaBattleServiceServicer):
    """gRPC service with server-managed matchmaking"""
    
    def __init__(self, game_engine):
        self.game_engine = game_engine
        self.matchmaker = ServerMatchmaker()
        self.connections: Dict[int, BotConnection] = {}
        
    async def RegisterBot(self, request, context):
        """Register bot with server-managed matchmaking"""
        try:
            player_id = request.player_id
            bot_name = request.bot_name
            
            logger.info(f"Bot registration: {player_id}/{bot_name}")
            
            # Server assigns match automatically
            match_result = self.matchmaker.register_player(player_id, bot_name)
            
            if not match_result['success']:
                return arena_pb2.RegistrationResponse(
                    success=False,
                    message=match_result.get('message', 'Registration failed'),
                    bot_id=0
                )
            
            # Create bots in game engine based on server assignment
            created_bot_ids = []
            for bot_id in match_result['bot_ids']:
                # Use provided bot_id or create new one
                actual_bot_id = self.game_engine.game_state.add_bot(player_id, bot_name)
                created_bot_ids.append(actual_bot_id)
            
            primary_bot_id = created_bot_ids[0] if created_bot_ids else 0
            
            logger.info(f"Server assigned: {match_result['match_mode']} mode")
            logger.info(f"Created {len(created_bot_ids)} bots")
            
            return arena_pb2.RegistrationResponse(
                success=True,
                message=f"Server assigned: {match_result['match_mode']} mode with {len(created_bot_ids)} bots",
                bot_id=primary_bot_id
            )
            
        except Exception as e:
            logger.error(f"Registration error: {e}")
            return arena_pb2.RegistrationResponse(
                success=False,
                message=str(e),
                bot_id=0
            )
    
    async def PlayGame(self, request_iterator, context):
        """Main game streaming with server-managed bots"""
        bot_connection = None
        
        try:
            # Find unconnected bot
            bot_id = None
            for bid, bot in self.game_engine.game_state.bots.items():
                if bid not in self.connections:
                    bot_id = bid
                    break
            
            if bot_id is None:
                logger.error("No available bot for connection")
                return
            
            # Create connection
            bot = self.game_engine.game_state.bots[bot_id]
            bot_connection = BotConnection(bot_id, bot.player_id)
            self.connections[bot_id] = bot_connection
            
            logger.info(f"Bot {bot_id} ({bot.name}) connected")
            
            # Start observation sender
            observation_task = asyncio.create_task(
                self._send_observations(bot_connection, context)
            )
            
            # Process actions
            try:
                async for action_request in request_iterator:
                    await self._process_action(action_request, bot_id)
                    bot_connection.last_action_time = asyncio.get_event_loop().time()
                    
            except Exception as e:
                logger.error(f"Action processing error for bot {bot_id}: {e}")
            
            await observation_task
            
        except Exception as e:
            logger.error(f"PlayGame error: {e}")
        finally:
            if bot_connection:
                bot_connection.is_active = False
                if bot_connection.bot_id in self.connections:
                    del self.connections[bot_connection.bot_id]
                
                # Clean up matchmaker
                self.matchmaker.remove_player(bot_connection.player_id)
                
                logger.info(f"Bot {bot_connection.bot_id} disconnected")
    
    async def _process_action(self, action_request, bot_id: int):
        """Process action from bot"""
        try:
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
            logger.error(f"Action processing error: {e}")
    
    async def _send_observations(self, connection: BotConnection, context):
        """Send observations to connected bot"""
        try:
            while connection.is_active:
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
                
                await asyncio.sleep(1/60)  # 60 FPS
                
        except Exception as e:
            logger.error(f"Observation sending error: {e}")
            connection.is_active = False
    
    async def GetStats(self, request, context):
        """Get match statistics"""
        player_id = request.player_id
        match_info = self.matchmaker.get_match_info(player_id)
        
        return arena_pb2.GameStats(
            total_kills=0,  # Placeholder
            total_deaths=0,
            kill_death_ratio=0,
            games_played=1,
            average_survival_time=45.0
        )

async def run_server(game_engine, port=50051):
    """Run the gRPC server with matchmaking"""
    server = grpc.aio.server(futures.ThreadPoolExecutor(max_workers=10))
    
    servicer = ArenaBattleServicer(game_engine)
    arena_pb2_grpc.add_ArenaBattleServiceServicer_to_server(servicer, server)
    
    listen_addr = f'[::]:{port}'
    server.add_insecure_port(listen_addr)
    
    logger.info(f"gRPC Server with matchmaking starting on {listen_addr}")
    await server.start()
    
    try:
        await server.wait_for_termination()
    except KeyboardInterrupt:
        logger.info("gRPC Server stopped")
        await server.stop(5)