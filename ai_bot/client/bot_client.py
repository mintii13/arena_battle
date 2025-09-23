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
from ai_bot.rewards.arena_reward import ArenaRewardCalculator

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

try:
    from proto import arena_pb2, arena_pb2_grpc
except ImportError:
    print("❌ Proto files not found! Run: python proto/generate.py")
    sys.exit(1)

logger = logging.getLogger(__name__)

class BotClient:
    """AI Bot client with wall avoidance, smart aiming, and auto-save (keeping original class name)"""
    
    def __init__(self, player_id, bot_name, trainer, obs_processor, room_id, room_password):
        self.player_id = player_id
        self.bot_name = bot_name
        self.room_id = room_id
        self.room_password = room_password
        self.trainer = trainer
        self.obs_processor = obs_processor
        
        self.connected = False
        self.bot_id = None
        self.last_obs = None
        self.last_hp = 100.0
        self.last_enemy_hp = 100.0
        self.match_active = False
        
        # Stats
        self.episode_reward = 0
        self.episode_count = 0
        self.total_reward = 0
        self.kills = 0
        self.deaths = 0
        
        # Enhanced movement system
        self.movement_bonus = 0.01
        self.stillness_penalty = -0.05
        self.wall_hit_penalty = -0.1
        self.smart_move_bonus = 0.02
        self.last_position = None
        
        # Wall avoidance tracking
        self.wall_collision_count = 0
        self.stuck_counter = 0
        self.last_wall_avoid_direction = None
        
        # Smart aiming system
        self.last_aim_angle = 0.0
        self.target_locked = False
        self.shots_fired = 0
        self.shots_hit = 0
        
        # Auto-save system
        self.model_save_dir = Path("models") / "checkpoints"
        self.model_save_dir.mkdir(parents=True, exist_ok=True)
        self.last_save_time = time.time()
        self.save_interval = 300  # Save every 5 minutes
        self.save_on_improvement = True
        self.best_kd_ratio = 0.0
        
        # Connection state
        self.waiting_start_time = None

        self.reward_calculator = ArenaRewardCalculator()
        
        logger.info(f"🤖 Smart Combat Bot initialized: {self.bot_name}")
        logger.info(f"💾 Auto-save enabled: {self.model_save_dir}")
    
    async def connect_and_play(self, host='localhost', port=50051):
        """Connect to server and join PvP battle with auto-save"""
        try:
            # Connect to server
            channel = grpc.aio.insecure_channel(f'{host}:{port}')
            stub = arena_pb2_grpc.ArenaBattleServiceStub(channel)
            
            # Register for PvP matchmaking with FULL bot name
            registration = arena_pb2.BotRegistration(
                player_id=self.player_id,
                bot_name=f"{self.bot_name}|{self.room_id}|{self.room_password}"
            )
            
            logger.info(f"🤖 Registering smart combat bot: {self.bot_name}")
            logger.info(f"👤 Player ID: {self.player_id}")
            response = await stub.RegisterBot(registration)
            
            if not response.success:
                logger.error(f"❌ Registration failed: {response.message}")
                return
            
            self.bot_id = response.bot_id
            logger.info(f"✅ Combat bot registered with ID: {self.bot_id}")
            logger.info(f"🧠 Features: Wall avoidance, Smart aiming, Auto-save")
            logger.info(f"📊 Status: {response.message}")
            
            # Check if we're waiting for players
            if "Waiting" in response.message:
                self.waiting_start_time = time.time()
                logger.info("⏳ Waiting for opponents to join battle...")
            
            # Setup auto-save monitoring
            save_task = asyncio.create_task(self._auto_save_monitor())
            
            try:
                # Start enhanced game loop
                await self._game_loop(stub)
            finally:
                # Cancel auto-save and do final save
                save_task.cancel()
                await self._save_model("final_save")
                
        except Exception as e:
            logger.error(f"💥 Connection error: {e}")
        finally:
            if 'channel' in locals():
                await channel.close()
    
    async def _auto_save_monitor(self):
        """Monitor for auto-save conditions"""
        try:
            while True:
                await asyncio.sleep(30)  # Check every 30 seconds
                
                current_time = time.time()
                
                # Time-based auto-save
                if current_time - self.last_save_time > self.save_interval:
                    await self._save_model("auto_time")
                
                # Performance-based auto-save
                if self.save_on_improvement and self.deaths > 0:
                    current_kd = self.kills / self.deaths
                    if current_kd > self.best_kd_ratio + 0.2:  # Significant improvement
                        self.best_kd_ratio = current_kd
                        await self._save_model("auto_improvement")
                        logger.info(f"🏆 Model saved due to K/D improvement: {current_kd:.2f}")
                
        except asyncio.CancelledError:
            pass
    
    async def _save_model(self, save_type="manual"):
        """Save the current model"""
        try:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filename = f"{self.player_id}_{save_type}_{timestamp}.pth"
            filepath = self.model_save_dir / filename
            
            # Prepare save data
            save_data = {
                'network_state_dict': self.trainer.network.state_dict(),
                'optimizer_state_dict': self.trainer.optimizer.state_dict(),
                'player_id': self.player_id,
                'bot_name': self.bot_name,
                'episode_count': self.episode_count,
                'total_reward': self.total_reward,
                'kills': self.kills,
                'deaths': self.deaths,
                'kd_ratio': self.kills / max(self.deaths, 1),
                'shots_fired': self.shots_fired,
                'shots_hit': self.shots_hit,
                'accuracy': self.shots_hit / max(self.shots_fired, 1) * 100,
                'wall_collisions': self.wall_collision_count,
                'save_time': timestamp,
                'save_type': save_type
            }
            
            # Save model
            torch.save(save_data, filepath)
            self.last_save_time = time.time()
            
            logger.info(f"💾 Model saved: {filename}")
            logger.info(f"📊 Stats: {self.kills}K/{self.deaths}D, Acc: {save_data['accuracy']:.1f}%")
            
            # Keep only last 10 auto-saves to prevent disk bloat
            if save_type.startswith("auto"):
                await self._cleanup_old_saves()
                
        except Exception as e:
            logger.error(f"💥 Save error: {e}")
    
    async def _cleanup_old_saves(self):
        """Clean up old auto-save files"""
        try:
            auto_saves = list(self.model_save_dir.glob(f"{self.player_id}_auto_*.pth"))
            auto_saves.sort(key=lambda x: x.stat().st_mtime, reverse=True)
            
            # Keep only 10 most recent auto-saves
            for old_save in auto_saves[10:]:
                old_save.unlink()
                logger.debug(f"🗑️ Cleaned up old save: {old_save.name}")
                
        except Exception as e:
            logger.error(f"💥 Cleanup error: {e}")
    
    def load_model(self, model_path):
        """Load a saved model"""
        try:
            if not os.path.exists(model_path):
                logger.error(f"❌ Model file not found: {model_path}")
                return False
            
            checkpoint = torch.load(model_path, map_location='cpu')
            
            # Load network state
            self.trainer.network.load_state_dict(checkpoint['network_state_dict'])
            self.trainer.optimizer.load_state_dict(checkpoint['optimizer_state_dict'])
            
            # Load stats
            self.episode_count = checkpoint.get('episode_count', 0)
            self.total_reward = checkpoint.get('total_reward', 0)
            self.kills = checkpoint.get('kills', 0)
            self.deaths = checkpoint.get('deaths', 0)
            self.shots_fired = checkpoint.get('shots_fired', 0)
            self.shots_hit = checkpoint.get('shots_hit', 0)
            self.wall_collision_count = checkpoint.get('wall_collisions', 0)
            self.best_kd_ratio = checkpoint.get('kd_ratio', 0)
            
            logger.info(f"✅ Model loaded successfully from: {model_path}")
            logger.info(f"📊 Loaded stats: {self.kills}K/{self.deaths}D, Episodes: {self.episode_count}")
            logger.info(f"🎯 Accuracy: {self.shots_hit}/{self.shots_fired} ({self.shots_hit/max(self.shots_fired,1)*100:.1f}%)")
            
            return True
            
        except Exception as e:
            logger.error(f"💥 Load error: {e}")
            return False
    
    async def _game_loop(self, stub):
        """Main game loop with smart combat AI"""
        logger.info("🎮 Starting smart PvP combat system...")
        
        action_queue = asyncio.Queue()
        
        # Start action sender
        sender_task = asyncio.create_task(self._action_sender(action_queue))
        
        # Start observation receiver
        try:
            async for observation in stub.PlayGame(self._action_generator(action_queue)):
                await self._process_observation(observation, action_queue)
                
        except Exception as e:
            logger.error(f"💥 Game loop error: {e}")
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
        """Action sender with tactical defaults"""
        try:
            while True:
                # Smart default action when AI is not active
                action = arena_pb2.Action(
                    thrust=arena_pb2.Vec2(x=0.0, y=0.0),
                    aim_angle=self.last_aim_angle,  # Maintain last aim
                    fire=False
                )
                
                await action_queue.put(action)
                await asyncio.sleep(1/60)  # 60 FPS
                
        except asyncio.CancelledError:
            pass
    
    async def _process_observation(self, observation, action_queue):
        """Process observation with IMPROVED waiting handling"""
        try:
            # Check if this is a waiting state (no enemy)
            if observation.enemy_hp == 0 and observation.enemy_pos.x == 0:
                if not self.match_active:
                    # Still waiting for players - STABLE WAITING
                    if self.waiting_start_time:
                        wait_time = time.time() - self.waiting_start_time
                        # Log every 10 seconds instead of continuous spam
                        if int(wait_time) % 10 == 0 and wait_time > 0:
                            logger.info(f"⏳ {self.bot_name} waiting for opponents... ({wait_time:.0f}s)")
                    return  # ← IMPORTANT: Don't disconnect, just wait
                else:
                    # Match ended or enemy died
                    self.match_active = False
                    logger.info("🏁 Combat engagement ended")
            else:
                # Match is active
                if not self.match_active:
                    self.match_active = True
                    if self.waiting_start_time:
                        wait_time = time.time() - self.waiting_start_time
                        logger.info(f"⚔️ {self.bot_name} combat engagement started! (waited {wait_time:.1f}s)")
                        self.waiting_start_time = None
                    else:
                        logger.info(f"⚔️ {self.bot_name} joined ongoing combat engagement!")
         
            # Convert observation to enhanced dict
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
            
            # Only generate AI actions if match is active
            if self.match_active:
                # Process observation for enhanced AI
                processed_obs = self.obs_processor.process(obs_dict)
                
                # Get action from enhanced AI
                movement, aim, fire_action, value = self.trainer.network.get_action(processed_obs)
                
                # === ENHANCED WALL AVOIDANCE ===
                move_x = float(movement[0, 0].item())
                move_y = float(movement[0, 1].item())
                
                # Advanced wall collision detection and avoidance
                enhanced_movement = self._enhance_wall_avoidance(
                    move_x, move_y, obs_dict
                )
                move_x, move_y = enhanced_movement
                
                # === ENHANCED SMART AIMING ===
                aim_angle = float(aim[0, 0].item())
                enhanced_aim = self._enhance_smart_aiming(aim_angle, obs_dict)
                
                # === ENHANCED SMART FIRING ===
                should_fire = bool(fire_action[0].item())
                enhanced_fire = self._enhance_smart_firing(should_fire, obs_dict, enhanced_aim)
                
                # Track firing statistics
                if enhanced_fire:
                    self.shots_fired += 1
                    logger.debug(f"🎯 {self.bot_name} shot fired! ({self.shots_fired} total, accuracy: {self.shots_hit/max(self.shots_fired,1)*100:.1f}%)")
                
                # Create enhanced action message
                action = arena_pb2.Action(
                    thrust=arena_pb2.Vec2(x=move_x, y=move_y),
                    aim_angle=enhanced_aim,
                    fire=enhanced_fire
                )
                
                # Store for next iteration
                self.last_aim_angle = enhanced_aim
                
                # Calculate enhanced reward
                reward = self._calculate_reward(obs_dict, move_x, move_y, enhanced_fire)
                self.episode_reward += reward
                
                # Check if episode ended (bot died)
                done = obs_dict['self_hp'] <= 0
                
                if done:
                    # Chỉ log, không tăng death counter ở đây
                    logger.info(f"💀 {self.bot_name} eliminated! Episode reward: {self.episode_reward:.2f}")
                    logger.info(f"📊 Combat stats: {self.kills}K/{self.deaths}D (K/D: {self.kills/max(self.deaths,1):.2f})")
                    logger.info(f"🎯 Firing accuracy: {self.shots_hit}/{self.shots_fired} ({self.shots_hit/max(self.shots_fired,1)*100:.1f}%)")
                    
                    # Auto-save logic
                    if self.episode_count % 10 == 0:
                        await self._save_model("auto_death")
                    
                    self._reset_episode_stats()
                else:
                    self.last_hp = obs_dict['self_hp']
                    self.last_enemy_hp = obs_dict['enemy_hp']
                
                self.episode_reward += reward
                self.last_obs = processed_obs
                
                # Send enhanced action to game
                await action_queue.put(action)
            else:
                # Send neutral action while waiting
                neutral_action = arena_pb2.Action(
                    thrust=arena_pb2.Vec2(x=0.0, y=0.0),
                    aim_angle=0.0,
                    fire=False
                )
                await action_queue.put(neutral_action)
            
        except Exception as e:
            logger.error(f"💥 Observation processing error: {e}")
    
    def _enhance_wall_avoidance(self, move_x, move_y, obs_dict):
        """Enhanced wall avoidance system"""
        self_pos = obs_dict['self_pos']
        arena_width = obs_dict['arena_width']
        arena_height = obs_dict['arena_height']
        
        # Calculate distances to walls
        left_dist = self_pos['x']
        right_dist = arena_width - self_pos['x']
        top_dist = self_pos['y']
        bottom_dist = arena_height - self_pos['y']
        
        # Wall avoidance thresholds
        danger_zone = 50  # Pixels from wall
        critical_zone = 25  # Pixels from wall
        
        # Enhanced wall avoidance forces
        avoid_x = 0.0
        avoid_y = 0.0
        
        # Left wall avoidance
        if left_dist < danger_zone:
            force = (danger_zone - left_dist) / danger_zone
            if left_dist < critical_zone:
                force *= 3.0  # Strong avoidance in critical zone
            avoid_x += force * 0.8
            logger.debug(f"🧱 {self.bot_name} avoiding left wall (dist: {left_dist:.1f})")
        
        # Right wall avoidance
        if right_dist < danger_zone:
            force = (danger_zone - right_dist) / danger_zone
            if right_dist < critical_zone:
                force *= 3.0
            avoid_x -= force * 0.8
            logger.debug(f"🧱 {self.bot_name} avoiding right wall (dist: {right_dist:.1f})")
        
        # Top wall avoidance
        if top_dist < danger_zone:
            force = (danger_zone - top_dist) / danger_zone
            if top_dist < critical_zone:
                force *= 3.0
            avoid_y += force * 0.8
            logger.debug(f"🧱 {self.bot_name} avoiding top wall (dist: {top_dist:.1f})")
        
        # Bottom wall avoidance
        if bottom_dist < danger_zone:
            force = (danger_zone - bottom_dist) / danger_zone
            if bottom_dist < critical_zone:
                force *= 3.0
            avoid_y -= force * 0.8
            logger.debug(f"🧱 {self.bot_name} avoiding bottom wall (dist: {bottom_dist:.1f})")
        
        # Apply wall avoidance to movement
        enhanced_move_x = np.clip(move_x + avoid_x, -1.0, 1.0)
        enhanced_move_y = np.clip(move_y + avoid_y, -1.0, 1.0)
        
        # Anti-stuck mechanism
        if self.last_position:
            distance_moved = math.sqrt(
                (self_pos['x'] - self.last_position[0])**2 + 
                (self_pos['y'] - self.last_position[1])**2
            )
            
            if distance_moved < 1.0:  # Bot is stuck
                self.stuck_counter += 1
                if self.stuck_counter > 30:  # Stuck for 0.5 seconds at 60fps
                    # Emergency unstuck movement
                    emergency_x = random.uniform(-1.0, 1.0)
                    emergency_y = random.uniform(-1.0, 1.0)
                    enhanced_move_x = emergency_x
                    enhanced_move_y = emergency_y
                    self.stuck_counter = 0
                    logger.debug(f"🚨 {self.bot_name} emergency unstuck movement activated!")
            else:
                self.stuck_counter = 0
        
        # Ensure minimum movement (anti-camping)
        movement_magnitude = math.sqrt(enhanced_move_x**2 + enhanced_move_y**2)
        if movement_magnitude < 0.3:
            # Add tactical movement
            enemy_pos = obs_dict['enemy_pos']
            if enemy_pos['x'] > 0:  # Enemy exists
                # Strafe movement relative to enemy
                enemy_angle = math.atan2(
                    enemy_pos['y'] - self_pos['y'],
                    enemy_pos['x'] - self_pos['x']
                )
                strafe_angle = enemy_angle + math.pi/2  # 90 degrees to enemy
                
                strafe_x = math.cos(strafe_angle) * 0.4
                strafe_y = math.sin(strafe_angle) * 0.4
                
                enhanced_move_x = np.clip(enhanced_move_x + strafe_x, -1.0, 1.0)
                enhanced_move_y = np.clip(enhanced_move_y + strafe_y, -1.0, 1.0)
                
                logger.debug(f"🏃 {self.bot_name} tactical strafe movement")
        
        return enhanced_move_x, enhanced_move_y
    
    def _enhance_smart_aiming(self, aim_angle, obs_dict):
        """Enhanced smart aiming system"""
        enemy_pos = obs_dict['enemy_pos']
        self_pos = obs_dict['self_pos']
        has_line_of_sight = obs_dict['has_line_of_sight']
        
        if enemy_pos['x'] == 0 and enemy_pos['y'] == 0:
            # No enemy, maintain current aim
            return aim_angle
        
        # Calculate optimal aim angle to enemy
        dx = enemy_pos['x'] - self_pos['x']
        dy = enemy_pos['y'] - self_pos['y']
        distance = math.sqrt(dx*dx + dy*dy)
        
        if distance == 0:
            return aim_angle
        
        # Direct angle to enemy
        enemy_angle = math.atan2(dy, dx)
        
        # Lead target calculation for moving enemy
        prediction_factor = min(distance / 400.0, 1.0)  # More prediction for distant targets
        
        # Add small random lead for unpredictability
        lead_adjustment = random.uniform(-0.1, 0.1) * prediction_factor
        predicted_angle = enemy_angle + lead_adjustment
        
        # Smart aiming logic
        if has_line_of_sight:
            # Direct line of sight - aim directly at enemy with prediction
            if distance < 150:
                # Close range - aim directly
                optimal_angle = enemy_angle
                self.target_locked = True
            else:
                # Long range - use prediction
                optimal_angle = predicted_angle
                self.target_locked = True
            
            # Smooth aim adjustment (not instant snap)
            angle_diff = optimal_angle - aim_angle
            
            # Handle angle wrapping
            if angle_diff > math.pi:
                angle_diff -= 2 * math.pi
            elif angle_diff < -math.pi:
                angle_diff += 2 * math.pi
            
            # Apply smooth aiming (80% toward target)
            enhanced_aim = aim_angle + angle_diff * 0.8
            
            logger.debug(f"🎯 {self.bot_name} smart aim locked on target (dist: {distance:.1f})")
            
        else:
            # No line of sight - use last known position with some adjustment
            angle_diff = enemy_angle - aim_angle
            
            # Handle angle wrapping
            if angle_diff > math.pi:
                angle_diff -= 2 * math.pi
            elif angle_diff < -math.pi:
                angle_diff += 2 * math.pi
            
            # Slower aim adjustment when no LOS (30% toward target)
            enhanced_aim = aim_angle + angle_diff * 0.3
            self.target_locked = False
            
            logger.debug(f"🔍 {self.bot_name} searching for target (no LOS)")
        
        # Normalize angle to [0, 2π]
        enhanced_aim = enhanced_aim % (2 * math.pi)
        
        return enhanced_aim
    
    def _enhance_smart_firing(self, should_fire, obs_dict, aim_angle):
        """Enhanced smart firing system"""
        enemy_pos = obs_dict['enemy_pos']
        self_pos = obs_dict['self_pos']
        has_line_of_sight = obs_dict['has_line_of_sight']
        enemy_hp = obs_dict['enemy_hp']
        
        # Don't fire if no enemy
        if enemy_pos['x'] == 0 and enemy_pos['y'] == 0:
            return False
        
        # Calculate distance to enemy
        dx = enemy_pos['x'] - self_pos['x']
        dy = enemy_pos['y'] - self_pos['y']
        distance = math.sqrt(dx*dx + dy*dy)
        
        # Calculate aim accuracy
        enemy_angle = math.atan2(dy, dx)
        aim_error = abs(aim_angle - enemy_angle)
        
        # Handle angle wrapping for error calculation
        if aim_error > math.pi:
            aim_error = 2 * math.pi - aim_error
        
        # Firing decision criteria
        fire_conditions = {
            'has_line_of_sight': has_line_of_sight,
            'in_range': 50 < distance < 500,  # Not too close, not too far
            'good_aim': aim_error < 0.3,  # Aim within ~17 degrees
            'enemy_alive': enemy_hp > 0,
            'ai_wants_fire': should_fire
        }
        
        # Conservative firing - only fire when conditions are good
        should_fire_enhanced = all([
            fire_conditions['has_line_of_sight'],
            fire_conditions['in_range'],
            fire_conditions['good_aim'],
            fire_conditions['enemy_alive']
        ])
        
        # Special cases
        if distance < 100 and has_line_of_sight:
            # Close range - fire even with poor aim
            should_fire_enhanced = True
            logger.debug(f"🔥 {self.bot_name} close range engagement (dist: {distance:.1f})")
        elif distance > 400:
            # Long range - require very good aim
            should_fire_enhanced = should_fire_enhanced and aim_error < 0.15
            if should_fire_enhanced:
                logger.debug(f"🎯 {self.bot_name} precision long range shot (dist: {distance:.1f})")
        
        # Don't fire too rapidly (burst control)
        if should_fire_enhanced:
            logger.debug(f"🔫 {self.bot_name} smart firing: LOS={has_line_of_sight}, dist={distance:.1f}, aim_error={aim_error:.2f}")
        
        return should_fire_enhanced
    
    def _calculate_reward(self, obs_dict, move_x, move_y, fired):
        """Calculate reward with KILL STATS tracking"""
        
        reward = self.reward_calculator.calculate_reward(obs_dict)
        
        if reward > 0:
            self.kills += 1
            logger.info(f"🎯 {self.bot_name} KILL CONFIRMED! Total kills: {self.kills}")
        elif reward < 0:
            self.deaths += 1
            logger.info(f"💀 {self.bot_name} DEATH CONFIRMED! Total deaths: {self.deaths}")
        
        return reward
    
    def _reset_episode_stats(self):
        """Reset episode statistics"""
        self.episode_reward = 0
        self.episode_count += 1
        self.total_reward += self.episode_reward
        self.last_hp = 100.0
        self.last_enemy_hp = 100.0
        self.last_position = None
        self.wall_collision_count = 0
        self.stuck_counter = 0
        self.target_locked = False
        self.reward_calculator.reset_state()