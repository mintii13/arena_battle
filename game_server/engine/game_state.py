# Game state logic
import numpy as np
import time
import math
from typing import Dict, List
from dataclasses import dataclass
from enum import Enum
import logging
logger = logging.getLogger(__name__)

class BotState(Enum):
    ALIVE = "alive"
    DEAD = "dead"
    INVULNERABLE = "invulnerable"

@dataclass
class Bot:
    id: int
    player_id: str
    name: str
    x: float = 400.0
    y: float = 300.0
    hp: float = 100.0
    max_hp: float = 100.0
    aim_angle: float = 0.0
    vel_x: float = 0.0
    vel_y: float = 0.0
    state: BotState = BotState.ALIVE
    kills: int = 0
    deaths: int = 0
    last_shot_time: float = 0.0
    death_time: float = 0.0
    invulnerable_until: float = 0.0
    radius: float = 15.0
    room_id: str = None

@dataclass
class DummyBot(Bot):
    """Bot di chuyển ngẫu nhiên, không bắn"""
    is_dummy: bool = True
    move_change_interval: float = 0.5  # Đổi hướng mỗi nửa giây
    last_direction_change: float = 0.0
    current_direction: tuple = (0.0, 0.0)
    
    def update_random_movement(self, game_state):
        """Cập nhật hướng di chuyển ngẫu nhiên với wall avoidance mạnh hơn"""
        import random
        current_time = time.time()
        
        # Initialize attributes if not exist
        if not hasattr(self, 'last_pos'):
            self.last_pos = (self.x, self.y)
            self.stuck_counter = 0
        
        # Check if stuck
        dist_moved = math.sqrt((self.x - self.last_pos[0])**2 + (self.y - self.last_pos[1])**2)
        if dist_moved < 1.0:  # Tăng ngưỡng từ 0.5 lên 1.0
            self.stuck_counter = getattr(self, 'stuck_counter', 0) + 1
        else:
            self.stuck_counter = 0
        
        self.last_pos = (self.x, self.y)
        
        # Force change direction if stuck (giảm ngưỡng từ 10 xuống 5)
        force_change = self.stuck_counter > 5
        
        if force_change or (current_time - self.last_direction_change >= self.move_change_interval):
            # Wall avoidance - TĂNG CƯỜNG
            arena_w = game_state.width
            arena_h = game_state.height
            
            left_dist = self.x
            right_dist = arena_w - self.x
            top_dist = self.y
            bottom_dist = arena_h - self.y
            
            danger_zone = 120  # Tăng từ 80 lên 120 (phát hiện tường sớm hơn)
            critical_zone = 50  # Vùng cực kỳ nguy hiểm
            
            avoid_x = 0.0
            avoid_y = 0.0
            
            # Left wall
            if left_dist < danger_zone:
                force = (danger_zone - left_dist) / danger_zone
                if left_dist < critical_zone:
                    force *= 3.0  # Tăng lực tránh gấp 3 nếu quá gần
                avoid_x += force
            
            # Right wall
            if right_dist < danger_zone:
                force = (danger_zone - right_dist) / danger_zone
                if right_dist < critical_zone:
                    force *= 3.0
                avoid_x -= force
            
            # Top wall
            if top_dist < danger_zone:
                force = (danger_zone - top_dist) / danger_zone
                if top_dist < critical_zone:
                    force *= 3.0
                avoid_y += force
            
            # Bottom wall
            if bottom_dist < danger_zone:
                force = (danger_zone - bottom_dist) / danger_zone
                if bottom_dist < critical_zone:
                    force *= 3.0
                avoid_y -= force
            
            # Ưu tiên tránh tường (giảm ngưỡng từ 0.3 xuống 0.2)
            if abs(avoid_x) > 0.2 or abs(avoid_y) > 0.2:
                magnitude = 1.0  # Tăng từ 0.9 lên 1.0 (tốc độ tối đa)
                self.current_direction = (avoid_x * magnitude, avoid_y * magnitude)
                self.stuck_counter = 0
            else:
                # Random movement (xa tường)
                angle = random.uniform(0, 2 * math.pi)
                magnitude = random.uniform(0.7, 1.0)  # Tăng tốc độ tối thiểu
                self.current_direction = (
                    math.cos(angle) * magnitude,
                    math.sin(angle) * magnitude
                )
            
            self.last_direction_change = current_time
        
        return self.current_direction

@dataclass
class Bullet:
    id: int
    shooter_id: int
    x: float
    y: float
    vel_x: float
    vel_y: float
    damage: float = 25.0
    radius: float = 3.0
    created_time: float = 0.0

@dataclass
class Wall:
    x: float
    y: float
    width: float
    height: float

class GameState:
    """Manages the complete game state"""
    
    def __init__(self):
        self.width = 800
        self.height = 600
        self.bots: Dict[int, Bot] = {}
        self.bullets: List[Bullet] = []
        self.walls: List[Wall] = []
        self.tick = 0
        self.next_bot_id = 1
        self.next_bullet_id = 1
        self.speed_multiplier = 1.0
        self.start_time = time.time()
        
        # Game statistics
        self.total_kills = 0
        self.total_deaths = 0
        self.total_bullets_fired = 0
        
        # Initialize walls
        self._create_arena_walls()
        self.room_id = None
    
    def _create_arena_walls(self, arena_config: dict = None):
        """Create arena walls and room-specific obstacles"""
        wall_thickness = 20
        
        # Boundary walls (luôn giống nhau)
        self.walls = [
            Wall(0, 0, self.width, wall_thickness),  # Top
            Wall(0, self.height - wall_thickness, self.width, wall_thickness),  # Bottom
            Wall(0, 0, wall_thickness, self.height),  # Left
            Wall(self.width - wall_thickness, 0, wall_thickness, self.height),  # Right
        ]
        
        # Add room-specific obstacles
        if arena_config and 'obstacles' in arena_config:
            for i, obs in enumerate(arena_config['obstacles']):
                wall = Wall(obs['x'], obs['y'], obs['width'], obs['height'])
                self.walls.append(wall)
        else:
            # Default obstacles (fallback)
            center_x, center_y = self.width // 2, self.height // 2
            self.walls.extend([
                Wall(center_x - 60, center_y - 15, 120, 30),  # Horizontal center
                Wall(center_x - 15, center_y - 80, 30, 160),   # Vertical center
        ])
    
    def add_bot(self, player_id: str, name: str, arena_config: dict = None, room_id: str = None, custom_bot_id: int = None) -> int:
        if custom_bot_id is not None:
            bot_id = custom_bot_id
        else:
            bot_id = self.next_bot_id
            self.next_bot_id += 1
        
        # Find valid spawn position
        spawn_x, spawn_y = self._find_spawn_position()
        
        bot = Bot(
            id=bot_id,
            player_id=player_id,
            name=name,
            x=spawn_x,
            y=spawn_y
        )
        
        # Store room info in bot
        bot.room_id = room_id  # Add this line
        
        self.bots[bot_id] = bot
        
        # Update arena walls if room-specific config provided
        if arena_config and len(self.bots) == 0:
            self._create_arena_walls(arena_config)
            self.room_id = room_id  # Track room for this state
        
        return bot_id
    
    def add_dummy_bot(self, room_id: str, arena_config: dict = None) -> int:
        """Thêm dummy bot (di chuyển ngẫu nhiên, không bắn)"""
        # Use negative IDs for dummy bots to avoid conflict with AI bots
        # AI bots use positive IDs (1, 2, 3, ...)
        # Dummy bots use negative IDs (-1, -2, -3, ...)
        
        if not hasattr(self, 'next_dummy_id'):
            self.next_dummy_id = -1
        
        bot_id = self.next_dummy_id
        self.next_dummy_id -= 1  # Decrease for next dummy bot
        
        # Find valid spawn position
        spawn_x, spawn_y = self._find_spawn_position()
        
        dummy_bot = DummyBot(
            id=bot_id,
            player_id=f"dummy_{abs(bot_id)}",
            name=f"Dummy#{abs(bot_id)}",
            x=spawn_x,
            y=spawn_y,
            room_id=room_id
        )
        
        self.bots[bot_id] = dummy_bot
        logger.info(f"🤖 Spawned dummy bot #{abs(bot_id)} (ID: {bot_id}) at ({spawn_x:.0f}, {spawn_y:.0f})")
        
        return bot_id
    
    def _find_spawn_position(self) -> tuple:
        """Find a random valid spawn position away from walls and other bots"""
        import random
        
        # Create larger pool of valid positions
        potential_spawns = []
        
        # Generate grid of potential spawn points
        for x in range(80, self.width - 80, 40):  # Every 40 pixels
            for y in range(80, self.height - 80, 40):
                if self._is_position_valid(x, y, 30):  # 30px clearance
                    potential_spawns.append((x, y))
        
        # Return random valid position
        if potential_spawns:
            return random.choice(potential_spawns)
        
        # Fallback to center if no valid positions found
        return self.width // 2, self.height // 2
    
    def _is_position_valid(self, x: float, y: float, radius: float) -> bool:
        """Check if position is valid (no wall collision, within bounds)"""
        # Check bounds
        if x - radius < 0 or x + radius > self.width:
            return False
        if y - radius < 0 or y + radius > self.height:
            return False
        
        # Check wall collisions
        for wall in self.walls:
            if self._circle_rect_collision(x, y, radius, wall):
                return False
        
        return True
    
    def _circle_rect_collision(self, cx: float, cy: float, radius: float, wall: Wall) -> bool:
        """Check collision between circle and rectangle"""
        # Find closest point on rectangle to circle center
        closest_x = max(wall.x, min(cx, wall.x + wall.width))
        closest_y = max(wall.y, min(cy, wall.y + wall.height))
        
        # Calculate distance
        dx = cx - closest_x
        dy = cy - closest_y
        distance_squared = dx * dx + dy * dy
        
        return distance_squared < radius * radius
    
    def remove_bot(self, bot_id: int):
        """Remove a bot from the game"""
        if bot_id in self.bots:
            del self.bots[bot_id]
    
    def add_bullet(self, shooter_id: int, x: float, y: float, vel_x: float, vel_y: float) -> int:
        """Add a new bullet"""
        bullet_id = self.next_bullet_id
        self.next_bullet_id += 1
        
        bullet = Bullet(
            id=bullet_id,
            shooter_id=shooter_id,
            x=x,
            y=y,
            vel_x=vel_x,
            vel_y=vel_y,
            created_time=time.time()
        )
        
        self.bullets.append(bullet)
        self.total_bullets_fired += 1
        return bullet_id
    
    def remove_bullet(self, bullet: Bullet):
        """Remove a bullet from the game"""
        if bullet in self.bullets:
            self.bullets.remove(bullet)
    
    def get_observation(self, bot_id: int) -> dict:
        """Get observation for a specific bot"""
        bot = self.bots.get(bot_id)
        if not bot:
            return {}
        
        # Find enemies (different player_id)
        enemies = [b for b in self.bots.values() 
                  if b.id != bot_id and b.player_id != bot.player_id and b.state == BotState.ALIVE]
        
        # Use closest enemy
        enemy_pos = (0, 0)
        enemy_hp = 0
        has_line_of_sight = False
        
        if enemies:
            closest_enemy = min(enemies, 
                key=lambda e: math.sqrt((e.x - bot.x)**2 + (e.y - bot.y)**2))
            enemy_pos = (closest_enemy.x, closest_enemy.y)
            enemy_hp = closest_enemy.hp
            has_line_of_sight = self._has_line_of_sight(
                (bot.x, bot.y), (closest_enemy.x, closest_enemy.y)
            )
        
        # Get nearby bullets (within 300 pixels)
        nearby_bullets = []
        for bullet in self.bullets:
            dx = bullet.x - bot.x
            dy = bullet.y - bot.y
            distance = math.sqrt(dx*dx + dy*dy)
            if distance <= 300:
                nearby_bullets.append({'x': bullet.x, 'y': bullet.y})
        
        # Serialize walls
        wall_data = []
        for wall in self.walls:
            wall_data.extend([wall.x, wall.y, wall.width, wall.height])
        
        return {
            'tick': self.tick,
            'self_pos': {'x': bot.x, 'y': bot.y},
            'self_hp': bot.hp,
            'enemy_pos': {'x': enemy_pos[0], 'y': enemy_pos[1]},
            'enemy_hp': enemy_hp,
            'bullets': nearby_bullets,
            'walls': wall_data,
            'has_line_of_sight': has_line_of_sight,
            'arena_width': self.width,
            'arena_height': self.height
        }
    
    def _has_line_of_sight(self, start: tuple, end: tuple) -> bool:
        """Check if there's line of sight between two points"""
        x1, y1 = start
        x2, y2 = end
        
        # Check if line intersects any wall
        for wall in self.walls:
            if self._line_rect_intersection(x1, y1, x2, y2, wall):
                return False
        
        return True
    
    def _line_rect_intersection(self, x1: float, y1: float, x2: float, y2: float, wall: Wall) -> bool:
        """Check if line segment intersects rectangle"""
        # Simplified line-rectangle intersection
        # Check if line crosses any of the four rectangle edges
        
        def line_intersect(x1, y1, x2, y2, x3, y3, x4, y4):
            """Check if two line segments intersect"""
            denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
            if abs(denom) < 1e-10:
                return False
            
            t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denom
            u = -((x1 - x2) * (y1 - y3) - (y1 - y2) * (x1 - x3)) / denom
            
            return 0 <= t <= 1 and 0 <= u <= 1
        
        # Wall edges
        wall_edges = [
            (wall.x, wall.y, wall.x + wall.width, wall.y),  # Top
            (wall.x + wall.width, wall.y, wall.x + wall.width, wall.y + wall.height),  # Right
            (wall.x + wall.width, wall.y + wall.height, wall.x, wall.y + wall.height),  # Bottom
            (wall.x, wall.y + wall.height, wall.x, wall.y)  # Left
        ]
        
        for edge in wall_edges:
            if line_intersect(x1, y1, x2, y2, *edge):
                return True
        
        return False
    
    def get_alive_bots(self) -> List[Bot]:
        """Get all alive bots"""
        return [bot for bot in self.bots.values() if bot.state == BotState.ALIVE]
    
    def get_game_stats(self) -> dict:
        """Get current game statistics"""
        uptime = time.time() - self.start_time
        alive_bots = len(self.get_alive_bots())
        
        return {
            'tick': self.tick,
            'uptime': uptime,
            'speed_multiplier': self.speed_multiplier,
            'total_bots': len(self.bots),
            'alive_bots': alive_bots,
            'active_bullets': len(self.bullets),
            'total_kills': self.total_kills,
            'total_deaths': self.total_deaths,
            'total_bullets_fired': self.total_bullets_fired,
            'fps': self.tick / max(uptime, 1)
        }