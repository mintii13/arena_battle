# UI Renderer
import pygame
import math
import asyncio
import time
import logging
from typing import Optional
from ..engine.game_state import BotState, GameState

logger = logging.getLogger(__name__)

class Colors:
    """Color constants"""
    BLACK = (0, 0, 0)
    WHITE = (255, 255, 255)
    RED = (255, 0, 0)
    GREEN = (0, 255, 0)
    BLUE = (0, 100, 255)
    YELLOW = (255, 255, 0)
    GRAY = (128, 128, 128)
    DARK_GRAY = (64, 64, 64)
    LIGHT_GRAY = (192, 192, 192)
    PURPLE = (128, 0, 128)
    ORANGE = (255, 165, 0)
    CYAN = (0, 255, 255)
    
    # UI colors
    UI_BACKGROUND = (40, 40, 50)
    UI_TEXT = (255, 255, 255)
    UI_BUTTON = (70, 70, 90)
    UI_BUTTON_HOVER = (90, 90, 110)
    UI_BUTTON_ACTIVE = (110, 110, 130)
    
    # Game colors
    ARENA_BACKGROUND = (20, 25, 35)
    WALL_COLOR = (100, 100, 120)
    BOT_ALIVE = (0, 150, 255)
    BOT_DEAD = (80, 80, 80)
    BOT_INVULNERABLE = (255, 255, 100)
    BULLET_COLOR = (255, 200, 50)
    HP_BAR_FULL = (50, 255, 50)
    HP_BAR_LOW = (255, 50, 50)
    HP_BAR_BG = (60, 60, 60)

class GameRenderer:
    """Pygame-based real-time game renderer"""
    
    def __init__(self, width=1200, height=800):
        self.screen_width = width
        self.screen_height = height
        
        # Layout
        self.ui_panel_width = 300
        self.arena_offset_x = self.ui_panel_width + 20
        self.arena_offset_y = 50
        
        # Pygame objects
        self.screen = None
        self.clock = None
        self.font = None
        self.small_font = None
        self.large_font = None
        
        # State
        self.running = False
        self.selected_bot = None
        self.show_debug = False
        
        # Speed control buttons
        self.speed_buttons = []
        self._setup_ui_elements()
    
    def _setup_ui_elements(self):
        """Setup UI button layouts"""
        button_y = 150
        button_width = 60
        button_height = 35
        button_spacing = 40
        
        speeds = [1.0, 2.0, 4.0, 10.0]
        labels = ["1x", "2x", "4x", "10x"]
        
        for i, (speed, label) in enumerate(zip(speeds, labels)):
            self.speed_buttons.append({
                'speed': speed,
                'label': label,
                'rect': pygame.Rect(20, button_y + i * button_spacing, button_width, button_height),
                'active': speed == 1.0
            })
    
    async def run(self, game_engine):
        """Main rendering loop"""
        if not self._initialize_pygame():
            return
        
        logger.info("🎨 Starting game renderer...")
        self.running = True
        
        try:
            while self.running:
                # Handle events
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        self.running = False
                    elif event.type == pygame.KEYDOWN:
                        self._handle_key_press(event.key, game_engine)
                    elif event.type == pygame.MOUSEBUTTONDOWN:
                        self._handle_mouse_click(event.pos, game_engine)
                
                # Render frame
                self._render_frame(game_engine)
                
                # Control frame rate (60 FPS rendering)
                self.clock.tick(60)
                await asyncio.sleep(0.001)  # Yield control to other tasks
                
        except Exception as e:
            logger.error(f"Renderer error: {e}")
        finally:
            self._cleanup()
    
    def _initialize_pygame(self) -> bool:
        """Initialize Pygame components"""
        try:
            pygame.init()
            self.screen = pygame.display.set_mode((self.screen_width, self.screen_height))
            pygame.display.set_caption("Arena Battle Game - Server")
            self.clock = pygame.time.Clock()
            
            # Initialize fonts
            self.font = pygame.font.Font(None, 24)
            self.small_font = pygame.font.Font(None, 18)
            self.large_font = pygame.font.Font(None, 32)
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize Pygame: {e}")
            return False
    
    def _render_frame(self, game_engine):
        """Render one complete frame"""
        # Clear screen
        self.screen.fill(Colors.BLACK)
        
        # Render UI panel
        self._render_ui_panel(game_engine)
        
        # Render arena
        self._render_arena(game_engine)
        
        # Update display
        pygame.display.flip()
    
    def _render_ui_panel(self, game_engine):
        """Render the left UI panel"""
        # Panel background
        panel_rect = pygame.Rect(0, 0, self.ui_panel_width, self.screen_height)
        pygame.draw.rect(self.screen, Colors.UI_BACKGROUND, panel_rect)
        pygame.draw.line(self.screen, Colors.WHITE, 
                        (self.ui_panel_width, 0), (self.ui_panel_width, self.screen_height), 2)
        
        y = 20
        margin = 20
        
        # Title
        title = self.large_font.render("ARENA BATTLE", True, Colors.UI_TEXT)
        self.screen.blit(title, (margin, y))
        y += 50
        
        # Speed controls
        speed_title = self.font.render("Speed Control:", True, Colors.UI_TEXT)
        self.screen.blit(speed_title, (margin, y))
        y += 30
        
        current_speed = game_engine.game_state.speed_multiplier
        for button in self.speed_buttons:
            color = Colors.UI_BUTTON_ACTIVE if button['speed'] == current_speed else Colors.UI_BUTTON
            
            pygame.draw.rect(self.screen, color, button['rect'])
            pygame.draw.rect(self.screen, Colors.WHITE, button['rect'], 2)
            
            label = self.small_font.render(button['label'], True, Colors.UI_TEXT)
            label_rect = label.get_rect(center=button['rect'].center)
            self.screen.blit(label, label_rect)
        
        y = 350
        
        # Game statistics
        stats = game_engine.game_state.get_game_stats()
        
        stats_title = self.font.render("Game Statistics:", True, Colors.UI_TEXT)
        self.screen.blit(stats_title, (margin, y))
        y += 30
        
        stats_text = [
            f"Tick: {stats['tick']:,}",
            f"FPS: {stats['fps']:.1f}",
            f"Speed: {stats['speed_multiplier']}x",
            f"Uptime: {stats['uptime']:.0f}s",
            "",
            f"Total Bots: {stats['total_bots']}",
            f"Alive Bots: {stats['alive_bots']}",
            f"Active Bullets: {stats['active_bullets']}",
            "",
            f"Total Kills: {stats['total_kills']:,}",
            f"Total Deaths: {stats['total_deaths']:,}",
            f"Bullets Fired: {stats['total_bullets_fired']:,}",
        ]
        
        for text in stats_text:
            if text:  # Skip empty lines
                rendered = self.small_font.render(text, True, Colors.UI_TEXT)
                self.screen.blit(rendered, (margin, y))
            y += 20
        
        # Bot list
        y += 20
        bot_title = self.font.render("Active Bots:", True, Colors.UI_TEXT)
        self.screen.blit(bot_title, (margin, y))
        y += 25
        
        # Show up to 8 bots
        bot_list = list(game_engine.game_state.bots.values())[:8]
        for bot in bot_list:
            # Bot status color
            if bot.state == BotState.ALIVE:
                color = Colors.BOT_ALIVE
            elif bot.state == BotState.INVULNERABLE:
                color = Colors.BOT_INVULNERABLE
            else:
                color = Colors.BOT_DEAD
            
            # Bot info
            bot_text = f"{bot.name[:12]}: {bot.kills}K/{bot.deaths}D"
            if bot == self.selected_bot:
                bot_text = f"► {bot_text}"
            
            rendered = self.small_font.render(bot_text, True, color)
            self.screen.blit(rendered, (margin, y))
            y += 18
        
        # Controls help
        y = self.screen_height - 120
        controls_title = self.font.render("Controls:", True, Colors.UI_TEXT)
        self.screen.blit(controls_title, (margin, y))
        y += 25
        
        controls = [
            "1,2,3,4 - Speed",
            "Click bot - Select",
            "D - Toggle debug",
            "ESC - Quit"
        ]
        
        for control in controls:
            rendered = self.small_font.render(control, True, Colors.LIGHT_GRAY)
            self.screen.blit(rendered, (margin, y))
            y += 18

        y += 30
        matchmaking_title = self.font.render("Server Matchmaking:", True, Colors.UI_TEXT)
        self.screen.blit(matchmaking_title, (margin, y))
        y += 25
        
        # Show auto-assignment info
        auto_info = [
            "AUTO-ASSIGNMENT:",
            "• New players → Self-play",
            "• Self-play: 1+2 clones", 
            "• PvP: 2 players max",
            "• Server manages modes"
        ]
        
        for info in auto_info:
            color = Colors.UI_TEXT if not info.startswith("•") else Colors.LIGHT_GRAY
            rendered = self.small_font.render(info, True, color)
            self.screen.blit(rendered, (margin, y))
            y += 18
    
    def _render_arena(self, game_engine):
        """Render the main arena"""
        game_state = game_engine.game_state
        
        # Calculate arena display area
        available_width = self.screen_width - self.arena_offset_x - 20
        available_height = self.screen_height - self.arena_offset_y - 20
        
        # Scale to fit while maintaining aspect ratio
        scale_x = available_width / game_state.width
        scale_y = available_height / game_state.height
        self.scale = min(scale_x, scale_y, 1.0)  # Don't scale up
        
        # Arena dimensions on screen
        arena_width = game_state.width * self.scale
        arena_height = game_state.height * self.scale
        
        # Arena background
        arena_rect = pygame.Rect(
            self.arena_offset_x, self.arena_offset_y,
            arena_width, arena_height
        )
        pygame.draw.rect(self.screen, Colors.ARENA_BACKGROUND, arena_rect)
        pygame.draw.rect(self.screen, Colors.WHITE, arena_rect, 2)
        
        # Render walls
        for wall in game_state.walls:
            wall_rect = pygame.Rect(
                self.arena_offset_x + wall.x * self.scale,
                self.arena_offset_y + wall.y * self.scale,
                wall.width * self.scale,
                wall.height * self.scale
            )
            pygame.draw.rect(self.screen, Colors.WALL_COLOR, wall_rect)
            if self.show_debug:
                pygame.draw.rect(self.screen, Colors.RED, wall_rect, 1)
        
        # Render bullets
        for bullet in game_state.bullets:
            bullet_x = self.arena_offset_x + bullet.x * self.scale
            bullet_y = self.arena_offset_y + bullet.y * self.scale
            bullet_radius = max(2, bullet.radius * self.scale)
            
            pygame.draw.circle(self.screen, Colors.BULLET_COLOR,
                             (int(bullet_x), int(bullet_y)), int(bullet_radius))
            
            if self.show_debug:
                # Show bullet velocity vector
                vel_scale = 0.1
                end_x = bullet_x + bullet.vel_x * vel_scale
                end_y = bullet_y + bullet.vel_y * vel_scale
                pygame.draw.line(self.screen, Colors.YELLOW,
                               (int(bullet_x), int(bullet_y)),
                               (int(end_x), int(end_y)), 1)
        
        # Render bots
        for bot in game_state.bots.values():
            self._render_bot(bot)
        
        # Render selected bot info
        if self.selected_bot and self.selected_bot.id in game_state.bots:
            self._render_selected_bot_info()
    
    def _render_bot(self, bot):
        """Render a single bot"""
        bot_x = self.arena_offset_x + bot.x * self.scale
        bot_y = self.arena_offset_y + bot.y * self.scale
        bot_radius = max(8, bot.radius * self.scale)
        
        # Bot color based on state
        if bot.state == BotState.ALIVE:
            color = Colors.BOT_ALIVE
        elif bot.state == BotState.INVULNERABLE:
            color = Colors.BOT_INVULNERABLE
        else:
            color = Colors.BOT_DEAD
        
        # Highlight selected bot
        if bot == self.selected_bot:
            pygame.draw.circle(self.screen, Colors.WHITE,
                             (int(bot_x), int(bot_y)), int(bot_radius + 4), 3)
        
        # Draw bot body
        pygame.draw.circle(self.screen, color,
                         (int(bot_x), int(bot_y)), int(bot_radius))
        pygame.draw.circle(self.screen, Colors.WHITE,
                         (int(bot_x), int(bot_y)), int(bot_radius), 2)
        
        # Draw aim direction
        if bot.state in [BotState.ALIVE, BotState.INVULNERABLE]:
            aim_length = bot_radius + 20
            aim_end_x = bot_x + math.cos(bot.aim_angle) * aim_length
            aim_end_y = bot_y + math.sin(bot.aim_angle) * aim_length
            
            pygame.draw.line(self.screen, Colors.WHITE,
                           (int(bot_x), int(bot_y)),
                           (int(aim_end_x), int(aim_end_y)), 3)
            
            # Aim tip
            pygame.draw.circle(self.screen, Colors.YELLOW,
                             (int(aim_end_x), int(aim_end_y)), 3)
        
        # HP bar
        if bot.state != BotState.DEAD:
            self._render_hp_bar(bot, bot_x, bot_y - bot_radius - 12)
        
        # Bot name
        name_text = self.small_font.render(bot.name[:10], True, Colors.WHITE)
        name_rect = name_text.get_rect(center=(int(bot_x), int(bot_y + bot_radius + 20)))
        self.screen.blit(name_text, name_rect)
        
        # Debug info
        if self.show_debug:
            debug_text = f"ID:{bot.id} HP:{bot.hp:.0f}"
            debug_rendered = self.small_font.render(debug_text, True, Colors.CYAN)
            self.screen.blit(debug_rendered, (int(bot_x - 30), int(bot_y + bot_radius + 35)))
    
    def _render_hp_bar(self, bot, x, y):
        """Render bot HP bar"""
        bar_width = 40
        bar_height = 6
        
        # Background
        bg_rect = pygame.Rect(x - bar_width//2, y, bar_width, bar_height)
        pygame.draw.rect(self.screen, Colors.HP_BAR_BG, bg_rect)
        
        # HP fill
        hp_ratio = bot.hp / bot.max_hp
        fill_width = int(bar_width * hp_ratio)
        
        if fill_width > 0:
            fill_color = Colors.HP_BAR_FULL if hp_ratio > 0.3 else Colors.HP_BAR_LOW
            fill_rect = pygame.Rect(x - bar_width//2, y, fill_width, bar_height)
            pygame.draw.rect(self.screen, fill_color, fill_rect)
        
        # Border
        pygame.draw.rect(self.screen, Colors.WHITE, bg_rect, 1)
    
    def _render_selected_bot_info(self):
        """Render detailed info for selected bot"""
        if not self.selected_bot:
            return
        
        # Info panel
        info_x = self.screen_width - 200
        info_y = 50
        panel_width = 180
        panel_height = 150
        
        panel_rect = pygame.Rect(info_x, info_y, panel_width, panel_height)
        pygame.draw.rect(self.screen, Colors.UI_BACKGROUND, panel_rect)
        pygame.draw.rect(self.screen, Colors.WHITE, panel_rect, 2)
        
        y = info_y + 10
        margin = info_x + 10
        
        # Bot details
        details = [
            f"Bot: {self.selected_bot.name}",
            f"ID: {self.selected_bot.id}",
            f"Player: {self.selected_bot.player_id}",
            f"State: {self.selected_bot.state.value}",
            f"HP: {self.selected_bot.hp:.1f}/{self.selected_bot.max_hp}",
            f"Kills: {self.selected_bot.kills}",
            f"Deaths: {self.selected_bot.deaths}",
            f"K/D: {self.selected_bot.kills/max(self.selected_bot.deaths,1):.2f}"
        ]
        
        for detail in details:
            text = self.small_font.render(detail, True, Colors.UI_TEXT)
            self.screen.blit(text, (margin, y))
            y += 16
    
    def _handle_key_press(self, key, game_engine):
        """Handle keyboard input"""
        if key == pygame.K_ESCAPE:
            self.running = False
        elif key == pygame.K_1:
            game_engine.game_state.speed_multiplier = 1.0
        elif key == pygame.K_2:
            game_engine.game_state.speed_multiplier = 2.0
        elif key == pygame.K_3:
            game_engine.game_state.speed_multiplier = 4.0
        elif key == pygame.K_4:
            game_engine.game_state.speed_multiplier = 10.0
        elif key == pygame.K_d:
            self.show_debug = not self.show_debug
        elif key == pygame.K_c:
            self.selected_bot = None
    
    def _handle_mouse_click(self, pos, game_engine):
        """Handle mouse clicks"""
        mouse_x, mouse_y = pos
        
        # Check speed buttons
        for button in self.speed_buttons:
            if button['rect'].collidepoint(mouse_x, mouse_y):
                game_engine.game_state.speed_multiplier = button['speed']
                return
        
        # Check arena clicks (bot selection)
        if mouse_x >= self.arena_offset_x:
            # Convert screen coordinates to arena coordinates
            arena_x = (mouse_x - self.arena_offset_x) / self.scale
            arena_y = (mouse_y - self.arena_offset_y) / self.scale
            
            # Find closest bot
            closest_bot = None
            closest_distance = float('inf')
            
            for bot in game_engine.game_state.bots.values():
                dx = bot.x - arena_x
                dy = bot.y - arena_y
                distance = math.sqrt(dx*dx + dy*dy)
                
                if distance < bot.radius + 20 and distance < closest_distance:
                    closest_bot = bot
                    closest_distance = distance
            
            self.selected_bot = closest_bot
    
    def stop(self):
        """Stop the renderer"""
        self.running = False
    
    def _cleanup(self):
        """Clean up Pygame resources"""
        if pygame.get_init():
            pygame.quit()
        logger.info("🎨 Renderer stopped")