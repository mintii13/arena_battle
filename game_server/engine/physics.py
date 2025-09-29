# Physics logic
import numpy as np
import math
import time
import logging
from typing import List, Tuple
from .game_state import Bot, Bullet, BotState, GameState, DummyBot

logger = logging.getLogger(__name__)

class PhysicsEngine:
    """Handles all physics simulation"""
    
    def __init__(self, game_state: GameState):
        self.game_state = game_state
        
        # Physics constants
        self.bullet_speed = 400.0  # pixels per second
        self.max_bot_speed = 200.0
        self.bot_acceleration = 800.0
        self.friction = 0.85
        self.shot_cooldown = 0.3  # seconds
        self.respawn_delay = 1.0  # seconds
        self.invulnerability_time = 1.0  # seconds
    
    def update(self, dt: float):
        """Update physics for one frame"""
        # Clamp dt to prevent instability
        dt = min(dt, 0.1)
        
        # Update bots
        self._update_bots(dt)
        
        # Update bullets
        self._update_bullets(dt)
        
        # Check collisions
        self._check_bullet_collisions()
        self._check_bot_collisions()
        
        # Handle respawns
        self._handle_respawns()
        
        # Increment tick
        self.game_state.tick += 1
    
    def _update_bots(self, dt: float):
        """Update bot physics"""
        for bot in self.game_state.bots.values():
            if bot.state not in [BotState.ALIVE, BotState.INVULNERABLE]:
                continue

            if isinstance(bot, DummyBot):
                thrust_x, thrust_y = bot.update_random_movement()
                bot.vel_x += thrust_x * self.bot_acceleration * dt
                bot.vel_y += thrust_y * self.bot_acceleration * dt
            
            # Apply friction
            bot.vel_x *= self.friction
            bot.vel_y *= self.friction
            
            # Update position
            new_x = bot.x + bot.vel_x * dt
            new_y = bot.y + bot.vel_y * dt
            
            # Check bounds and walls
            if self.game_state._is_position_valid(new_x, bot.y, bot.radius):
                bot.x = new_x
            else:
                bot.vel_x = 0
            
            if self.game_state._is_position_valid(bot.x, new_y, bot.radius):
                bot.y = new_y
            else:
                bot.vel_y = 0
    
    def _update_bullets(self, dt: float):
        """Update bullet physics"""
        bullets_to_remove = []
        
        for bullet in self.game_state.bullets:
            # Update position
            bullet.x += bullet.vel_x * dt
            bullet.y += bullet.vel_y * dt
            
            # Check bounds
            if (bullet.x < 0 or bullet.x > self.game_state.width or
                bullet.y < 0 or bullet.y > self.game_state.height):
                bullets_to_remove.append(bullet)
                continue
            
            # Check wall collisions
            if self._bullet_wall_collision(bullet):
                bullets_to_remove.append(bullet)
                continue
        
        # Remove bullets
        for bullet in bullets_to_remove:
            self.game_state.remove_bullet(bullet)
    
    def _bullet_wall_collision(self, bullet: Bullet) -> bool:
        """Check if bullet collides with walls"""
        for wall in self.game_state.walls:
            if self.game_state._circle_rect_collision(
                bullet.x, bullet.y, bullet.radius, wall
            ):
                return True
        return False
    
    def _check_bullet_collisions(self):
        """Check bullet-bot collisions"""
        bullets_to_remove = []
        
        for bullet in self.game_state.bullets:
            for bot in self.game_state.bots.values():
                # Skip shooter and non-alive bots
                if (bot.id == bullet.shooter_id or 
                    bot.state != BotState.ALIVE):
                    continue
                
                # Check collision
                dx = bullet.x - bot.x
                dy = bullet.y - bot.y
                distance = math.sqrt(dx*dx + dy*dy)
                
                if distance < bullet.radius + bot.radius:
                    # Hit!
                    self._damage_bot(bot, bullet.damage, bullet.shooter_id)
                    bullets_to_remove.append(bullet)
                    break
        
        # Remove hit bullets
        for bullet in bullets_to_remove:
            self.game_state.remove_bullet(bullet)
    
    def _check_bot_collisions(self):
        """Check bot-bot collisions"""
        alive_bots = self.game_state.get_alive_bots()
        
        for i in range(len(alive_bots)):
            for j in range(i + 1, len(alive_bots)):
                bot1, bot2 = alive_bots[i], alive_bots[j]
                
                dx = bot2.x - bot1.x
                dy = bot2.y - bot1.y
                distance = math.sqrt(dx*dx + dy*dy)
                min_distance = bot1.radius + bot2.radius
                
                if distance < min_distance and distance > 0:
                    # Collision! Separate bots
                    overlap = min_distance - distance
                    separation = overlap / 2
                    
                    # Normalize direction
                    nx = dx / distance
                    ny = dy / distance
                    
                    # Separate
                    bot1.x -= nx * separation
                    bot1.y -= ny * separation
                    bot2.x += nx * separation
                    bot2.y += ny * separation
                    
                    # Bounce velocities
                    v1n = bot1.vel_x * nx + bot1.vel_y * ny
                    v2n = bot2.vel_x * nx + bot2.vel_y * ny
                    
                    # Simple elastic collision
                    bot1.vel_x += (v2n - v1n) * nx * 0.5
                    bot1.vel_y += (v2n - v1n) * ny * 0.5
                    bot2.vel_x += (v1n - v2n) * nx * 0.5
                    bot2.vel_y += (v1n - v2n) * ny * 0.5
    
    def _damage_bot(self, bot: Bot, damage: float, attacker_id: int):
        """Apply damage to bot"""
        bot.hp -= damage
        
        if bot.hp <= 0:
            self._kill_bot(bot, attacker_id)
    
    def _kill_bot(self, bot: Bot, killer_id: int):
        """Handle bot death - NO REWARD CALCULATION"""
        bot.state = BotState.DEAD
        bot.death_time = time.time()
        bot.hp = 0
        bot.deaths += 1
        
        # Award kill stats
        if killer_id in self.game_state.bots:
            self.game_state.bots[killer_id].kills += 1
            self.game_state.total_kills += 1
        
        self.game_state.total_deaths += 1

        # Handle dummy bot death
        if isinstance(bot, DummyBot) and bot.room_id:
            logger.info(f"🤖 Dummy bot #{bot.id} killed, will respawn 2 more")
            # Set flag để server biết cần spawn thêm
            if not hasattr(self.game_state, 'pending_dummy_respawns'):
                self.game_state.pending_dummy_respawns = {}
            
            room_id = bot.room_id
            if room_id not in self.game_state.pending_dummy_respawns:
                self.game_state.pending_dummy_respawns[room_id] = 0
            self.game_state.pending_dummy_respawns[room_id] += 1
        
    def _handle_respawns(self):
        """Handle bot respawning"""
        current_time = time.time()
        
        for bot in self.game_state.bots.values():
            if bot.state == BotState.DEAD:
                if current_time - bot.death_time >= self.respawn_delay:
                    # Respawn at random location instead of death location
                    bot.x, bot.y = self.game_state._find_spawn_position()
                    
                    bot.state = BotState.INVULNERABLE
                    bot.hp = bot.max_hp
                    bot.vel_x = 0
                    bot.vel_y = 0
                    bot.invulnerable_until = current_time + self.invulnerability_time
                    
                    logger.info(f"♻️  Bot {bot.name} respawned")
            
            elif bot.state == BotState.INVULNERABLE:
                if current_time >= bot.invulnerable_until:
                    bot.state = BotState.ALIVE

        if hasattr(self.game_state, 'pending_dummy_respawns'):
            for room_id, count in list(self.game_state.pending_dummy_respawns.items()):
                if count > 0:
                    for _ in range(count):
                        self.game_state.add_dummy_bot(room_id)
                    logger.info(f"🤖 Respawned {count} dummy bots in room {room_id}")
            self.game_state.pending_dummy_respawns.clear()
    
    def apply_bot_action(self, bot_id: int, action: dict):
        """Apply action to bot"""
        bot = self.game_state.bots.get(bot_id)
        if not bot or bot.state not in [BotState.ALIVE, BotState.INVULNERABLE]:
            return
        
        if isinstance(bot, DummyBot):
            return
        
        # Apply thrust
        thrust = action.get('thrust', {'x': 0, 'y': 0})
        thrust_x = max(-1, min(1, thrust.get('x', 0)))
        thrust_y = max(-1, min(1, thrust.get('y', 0)))
        
        # Add acceleration
        bot.vel_x += thrust_x * self.bot_acceleration * (1/60)  # Assume 60fps
        bot.vel_y += thrust_y * self.bot_acceleration * (1/60)
        
        # Limit speed
        speed = math.sqrt(bot.vel_x**2 + bot.vel_y**2)
        if speed > self.max_bot_speed:
            factor = self.max_bot_speed / speed
            bot.vel_x *= factor
            bot.vel_y *= factor
        
        # Update aim
        bot.aim_angle = action.get('aim_angle', bot.aim_angle)
        
        # Handle shooting
        if action.get('fire', False) and bot.state == BotState.ALIVE:
            self._try_shoot(bot)
    
    def _try_shoot(self, bot: Bot):
        """Try to make bot shoot"""
        if isinstance(bot, DummyBot):
            return
        
        current_time = time.time()
        
        if current_time - bot.last_shot_time >= self.shot_cooldown:
            # Create bullet
            bullet_offset = 25  # Distance from bot center
            bullet_x = bot.x + math.cos(bot.aim_angle) * bullet_offset
            bullet_y = bot.y + math.sin(bot.aim_angle) * bullet_offset
            
            vel_x = math.cos(bot.aim_angle) * self.bullet_speed
            vel_y = math.sin(bot.aim_angle) * self.bullet_speed
            
            self.game_state.add_bullet(bot.id, bullet_x, bullet_y, vel_x, vel_y)
            bot.last_shot_time = current_time