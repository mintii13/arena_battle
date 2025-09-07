import asyncio
import grpc
import logging
import sys
import os
import time
import random
import math
import torch
import numpy as np
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

try:
    from proto import arena_pb2, arena_pb2_grpc
except ImportError:
    print("Proto files not found! Run: python proto/generate.py")
    sys.exit(1)

logger = logging.getLogger(__name__)

class BotClient:
    """AI Bot client that connects to game server"""
    
    def __init__(self, player_id, bot_name, trainer, obs_processor):
        self.player_id = player_id
        self.bot_name = bot_name
        self.trainer = trainer
        self.obs_processor = obs_processor
        
        self.connected = False
        self.bot_id = None
        self.last_obs = None
        self.last_hp = 100.0
        self.last_enemy_hp = 100.0
        
        # Stats
        self.episode_reward = 0
        self.episode_count = 0
        self.total_reward = 0
        
        # Movement encouragement
        self.movement_bonus = 0.01  # Small bonus for moving
        self.stillness_penalty = -0.05  # Penalty for staying still
        self.last_position = None
    
    async def connect_and_play(self, host='localhost', port=50051):
        """Connect to server and start playing - server manages matchmaking"""
        try:
            # Connect to server
            channel = grpc.aio.insecure_channel(f'{host}:{port}')
            stub = arena_pb2_grpc.ArenaBattleServiceStub(channel)
            
            # Register bot - server will assign to match
            registration = arena_pb2.BotRegistration(
                player_id=self.player_id,
                bot_name=self.bot_name,
                self_play_mode=False,  # Server decides
                clone_count=1  # Server decides
            )
            
            response = await stub.RegisterBot(registration)
            if not response.success:
                logger.error(f"Registration failed: {response.message}")
                return
            
            self.bot_id = response.bot_id
            logger.info(f"Bot registered with ID: {self.bot_id}")
            logger.info("Server will assign match mode automatically")
            
            # Start game loop
            await self._game_loop(stub)
            
        except Exception as e:
            logger.error(f"Connection error: {e}")
        finally:
            if 'channel' in locals():
                await channel.close()
    
    async def _game_loop(self, stub):
        """Main game loop"""
        logger.info("Starting game loop...")
        
        action_queue = asyncio.Queue()
        
        # Start action sender
        sender_task = asyncio.create_task(self._action_sender(action_queue))
        
        # Start observation receiver
        try:
            async for observation in stub.PlayGame(self._action_generator(action_queue)):
                await self._process_observation(observation, action_queue)
                
        except Exception as e:
            logger.error(f"Game loop error: {e}")
        finally:
            sender_task.cancel()
    
    async def _action_generator(self, action_queue):
        """Generate actions for the server"""
        try:
            while True:
                action = await action_queue.get()
                yield action
        except asyncio.CancelledError:
            pass
    
    async def _action_sender(self, action_queue):
        """Send actions at regular intervals"""
        try:
            while True:
                # Default action - will be overridden by AI
                action = arena_pb2.Action(
                    thrust=arena_pb2.Vec2(x=0.0, y=0.0),
                    aim_angle=0.0,
                    fire=False
                )
                
                await action_queue.put(action)
                await asyncio.sleep(1/60)  # 60 FPS
                
        except asyncio.CancelledError:
            pass
    
    async def _process_observation(self, observation, action_queue):
        """Process observation and generate action"""
        try:
            # Convert observation to dict
            obs_dict = {
                'tick': observation.tick,
                'self_pos': {'x': observation.self_pos.x, 'y': observation.self_pos.y},
                'self_hp': observation.self_hp,
                'enemy_pos': {'x': observation.enemy_pos.x, 'y': observation.enemy_pos.y},
                'enemy_hp': observation.enemy_hp,
                'bullets': [{'x': b.x, 'y': b.y} for b in observation.bullets],
                'walls': list(observation.walls),
                'has_line_of_sight': observation.has_line_of_sight,
                'arena_width': observation.arena_width,
                'arena_height': observation.arena_height
            }
            
            # Process observation for AI
            processed_obs = self.obs_processor.process(obs_dict)
            
            # Get action from AI with movement encouragement
            movement, aim, fire_action, value = self.trainer.network.get_action(processed_obs)
            
            # FORCE MOVEMENT: Add random component if movement too small
            move_x = float(movement[0, 0].item())
            move_y = float(movement[0, 1].item())
            
            # If movement is too small, add random exploration
            movement_magnitude = math.sqrt(move_x**2 + move_y**2)
            if movement_magnitude < 0.3:  # Threshold for "too still"
                # Add random movement bias
                random_x = random.uniform(-0.5, 0.5)
                random_y = random.uniform(-0.5, 0.5)
                move_x = np.clip(move_x + random_x, -1.0, 1.0)
                move_y = np.clip(move_y + random_y, -1.0, 1.0)
                logger.debug(f"Added exploration movement: ({random_x:.2f}, {random_y:.2f})")
            
            # Create action message
            action = arena_pb2.Action(
                thrust=arena_pb2.Vec2(x=move_x, y=move_y),
                aim_angle=float(aim[0, 0].item()),
                fire=bool(fire_action[0].item())
            )
            
            # Calculate reward with movement incentives
            reward = self._calculate_reward(obs_dict)
            
            # Check if episode ended (bot died)
            done = obs_dict['self_hp'] <= 0
            
            if done:
                logger.info(f"Bot died! Episode reward: {self.episode_reward:.2f}")
                self.episode_count += 1
                self.total_reward += self.episode_reward
                self.episode_reward = 0
                self.last_hp = 100.0
                self.last_enemy_hp = 100.0
                self.last_position = None
            else:
                self.last_hp = obs_dict['self_hp']
                self.last_enemy_hp = obs_dict['enemy_hp']
            
            self.episode_reward += reward
            self.last_obs = processed_obs
            
            # Send action to game
            await action_queue.put(action)
            
        except Exception as e:
            logger.error(f"Observation processing error: {e}")
    
    def _calculate_reward(self, obs_dict):
        """Calculate reward with movement incentives"""
        reward = 0.0
        
        # Core rewards: kill/death
        current_hp = obs_dict['self_hp']
        if current_hp <= 0 and self.last_hp > 0:
            reward = -100.0  # Death penalty
            logger.info(f"Death penalty: {reward}")
        
        enemy_hp = obs_dict['enemy_hp']
        if enemy_hp <= 0 and hasattr(self, 'last_enemy_hp') and self.last_enemy_hp > 0:
            reward = +100.0  # Kill reward
            logger.info(f"Kill reward: {reward}")
        
        # Movement incentives
        current_pos = (obs_dict['self_pos']['x'], obs_dict['self_pos']['y'])
        
        if self.last_position is not None:
            # Calculate movement distance
            distance_moved = math.sqrt(
                (current_pos[0] - self.last_position[0])**2 + 
                (current_pos[1] - self.last_position[1])**2
            )
            
            if distance_moved > 2.0:  # Moved significantly
                reward += self.movement_bonus
            elif distance_moved < 0.5:  # Too still
                reward += self.stillness_penalty
        
        self.last_position = current_pos
        
        return reward