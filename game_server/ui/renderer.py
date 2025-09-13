# Modern UI Renderer - Fixed and Compact
import pygame
import math
import asyncio
import time
import logging
import random
from typing import Optional
from ..engine.game_state import BotState, GameState
logger = logging.getLogger(__name__)
class ModernColors:
    """Modern color palette with gradients and effects"""
    # Base colors
    BLACK = (0, 0, 0)
    WHITE = (255, 255, 255)
    # Modern UI colors - Dark theme with neon accents
    BACKGROUND_PRIMARY = (10, 14, 39)      # Deep dark blue
    BACKGROUND_SECONDARY = (15, 20, 40)     # Slightly lighter
    BACKGROUND_TERTIARY = (25, 30, 50)     # Panel backgrounds
    # Neon accent colors
    NEON_CYAN = (0, 212, 255)              # Primary accent
    NEON_PINK = (255, 0, 128)              # Secondary accent  
    NEON_YELLOW = (255, 237, 78)           # Warning/special
    NEON_GREEN = (0, 255, 136)             # Success/health
    # UI element colors
    PANEL_BG = (15, 20, 40, 240)           # Semi-transparent panel
    BUTTON_NORMAL = (30, 35, 55)
    BUTTON_HOVER = (50, 55, 75) 
    BUTTON_ACTIVE = (0, 212, 255, 100)
    # Game element colors
    ARENA_BG = (10, 15, 30)
    WALL_PRIMARY = (100, 120, 150)
    WALL_SECONDARY = (80, 100, 130)
    WALL_BORDER = (150, 170, 200)
    # Bot colors with glow effects
    BOT_ALIVE = (0, 212, 255)
    BOT_ALIVE_GLOW = (0, 212, 255, 100)
    BOT_DEAD = (100, 100, 100)
    BOT_INVULNERABLE = (255, 237, 78)
    BOT_INVULNERABLE_GLOW = (255, 237, 78, 150)
    # Bullet colors
    BULLET_CORE = (255, 237, 78)
    BULLET_GLOW = (255, 136, 0)
    # HP bar colors  
    HP_HIGH = (0, 255, 136)
    HP_MEDIUM = (255, 237, 78)
    HP_LOW = (255, 68, 68)
    HP_BG = (20, 20, 20, 180)
    # Text colors
    TEXT_PRIMARY = (255, 255, 255)
    TEXT_SECONDARY = (200, 200, 200)
    TEXT_ACCENT = (0, 212, 255)
    TEXT_WARNING = (255, 237, 78)
class ModernButton:
    """Modern styled button with hover effects"""
    def __init__(self, x, y, width, height, text, font, active=False):
        self.rect = pygame.Rect(x, y, width, height)
        self.text = text
        self.font = font
        self.active = active
        self.hover = False
        self.click_time = 0
    def handle_event(self, event):
        """Handle button events"""
        if event.type == pygame.MOUSEMOTION:
            self.hover = self.rect.collidepoint(event.pos)
        elif event.type == pygame.MOUSEBUTTONDOWN:
            if self.rect.collidepoint(event.pos):
                self.click_time = time.time()
                return True
        return False
    def draw(self, surface):
        """Draw modern button with effects"""
        # Button background
        if self.active:
            color = ModernColors.NEON_CYAN
        elif self.hover:
            color = ModernColors.BUTTON_HOVER
        else:
            color = ModernColors.BUTTON_NORMAL
        # Draw main button
        pygame.draw.rect(surface, color, self.rect, border_radius=8)
        # Draw border
        border_color = ModernColors.NEON_CYAN if (self.active or self.hover) else ModernColors.TEXT_SECONDARY
        pygame.draw.rect(surface, border_color, self.rect, width=2, border_radius=8)
        # Draw button text
        text_color = ModernColors.TEXT_PRIMARY
        text_surface = self.font.render(self.text, True, text_color)
        text_rect = text_surface.get_rect(center=self.rect.center)
        surface.blit(text_surface, text_rect)
class GameRenderer:
    """Compact game renderer with fixed debug key"""
    def __init__(self, arena_width=800, arena_height=600):
        # Calculate window size based on arena + UI
        self.ui_panel_width = 320
        self.arena_width = arena_width
        self.arena_height = arena_height
        # Compact window - just fit the content
        self.screen_width = self.ui_panel_width + arena_width + 40  # 20px margin on each side
        self.screen_height = max(arena_height + 100, 700)  # At least 700px height for UI
        # Layout
        self.arena_offset_x = self.ui_panel_width + 20
        self.arena_offset_y = 60
        # Pygame objects
        self.screen = None
        self.clock = None
        self.fonts = {}
        # State
        self.running = False
        self.selected_bot = None
        self.show_debug = False  # Debug state tracking
        # UI elements
        self.speed_buttons = []
        # Animation timers
        self.title_glow_phase = 0
        logger.info(f"Compact renderer initialized: {self.screen_width}x{self.screen_height}")
        self._setup_ui_elements()
        self.current_viewing_room = None  # For spectator mode
        self.available_rooms = []  # List of all rooms
        self.viewing_mode = "room_001"
    def _setup_ui_elements(self):
        """Setup UI elements with compact layout"""
        # Speed control buttons - 2x2 grid
        button_width, button_height = 70, 35
        start_x, start_y = 25, 130
        speeds = [1.0, 2.0, 4.0, 10.0]
        labels = ["1x", "2x", "4x", "10x"]
        for i, (speed, label) in enumerate(zip(speeds, labels)):
            row = i // 2
            col = i % 2
            x = start_x + col * (button_width + 10)
            y = start_y + row * (button_height + 8)
            button = ModernButton(x, y, button_width, button_height, label, None, active=(speed == 1.0))
            button.speed = speed
            self.speed_buttons.append(button)
    def _initialize_fonts(self):
        """Initialize font system"""
        try:
            self.fonts = {
                'title': pygame.font.Font(None, 28),
                'subtitle': pygame.font.Font(None, 18),
                'normal': pygame.font.Font(None, 16),
                'small': pygame.font.Font(None, 14),
                'tiny': pygame.font.Font(None, 12),
            }
            # Update button fonts
            for button in self.speed_buttons:
                button.font = self.fonts['normal']
        except Exception as e:
            logger.error(f"Font initialization error: {e}")
            # Emergency fallback
            default_font = pygame.font.Font(None, 16)
            self.fonts = {key: default_font for key in ['title', 'subtitle', 'normal', 'small', 'tiny']}
    async def run(self, game_engine):
        """Main rendering loop"""
        if not self._initialize_pygame():
            return
        logger.info("Starting compact game renderer...")
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
                    elif event.type == pygame.MOUSEMOTION:
                        self._handle_mouse_motion(event)
                # Update animations
                self.title_glow_phase += 0.08
                # Render frame
                self._render_frame(game_engine)
                # Control frame rate
                self.clock.tick(60)
                await asyncio.sleep(0.001)
        except Exception as e:
            logger.error(f"Renderer error: {e}")
        finally:
            self._cleanup()
    def _initialize_pygame(self) -> bool:
        """Initialize Pygame with compact window"""
        try:
            pygame.init()
            # Create compact window
            self.screen = pygame.display.set_mode((self.screen_width, self.screen_height))
            pygame.display.set_caption("Arena Battle - Compact View")
            self.clock = pygame.time.Clock()
            # Initialize font system
            self._initialize_fonts()
            logger.info(f"Pygame initialized - Window: {self.screen_width}x{self.screen_height}")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize Pygame: {e}")
            return False
    def _render_frame(self, game_engine):
        """Render complete frame"""
        # Clear with gradient background
        self._render_background()
        # Render UI panel
        self._render_ui_panel(game_engine)
        # Render arena (perfectly fitted)
        self._render_arena(game_engine)
        # Update display
        pygame.display.flip()
    def _render_background(self):
        """Render background"""
        # Simple gradient
        for y in range(self.screen_height):
            ratio = y / self.screen_height
            r = int(ModernColors.BACKGROUND_PRIMARY[0] * (1-ratio) + ModernColors.BACKGROUND_SECONDARY[0] * ratio)
            g = int(ModernColors.BACKGROUND_PRIMARY[1] * (1-ratio) + ModernColors.BACKGROUND_SECONDARY[1] * ratio)  
            b = int(ModernColors.BACKGROUND_PRIMARY[2] * (1-ratio) + ModernColors.BACKGROUND_SECONDARY[2] * ratio)
            pygame.draw.line(self.screen, (r, g, b), (0, y), (self.screen_width, y))
    def _render_ui_panel(self, game_engine):
        """Render compact left UI panel"""
        # Panel background
        panel_rect = pygame.Rect(0, 0, self.ui_panel_width, self.screen_height)
        pygame.draw.rect(self.screen, ModernColors.BACKGROUND_TERTIARY, panel_rect)
        # Panel border
        pygame.draw.line(self.screen, ModernColors.NEON_CYAN, 
                        (self.ui_panel_width, 0), (self.ui_panel_width, self.screen_height), 2)
        y_offset = 20
        # Title
        self._render_title(y_offset)
        y_offset += 60
        # PvP mode
        mode_text = "🔥 PvP Combat Mode"
        mode_surface = self.fonts['normal'].render(mode_text, True, ModernColors.NEON_PINK)
        self.screen.blit(mode_surface, (25, y_offset))
        y_offset += 40
        # Speed control
        speed_title = self.fonts['subtitle'].render("⚡ Speed Control", True, ModernColors.NEON_CYAN)
        self.screen.blit(speed_title, (25, y_offset-20))
        y_offset += 25
        # Draw speed buttons
        for button in self.speed_buttons:
            button.draw(self.screen)
        y_offset += 100
        # Game statistics
        self._render_stats(game_engine, y_offset)
        y_offset += 180
        
        # # Room info
        # room_title = self.fonts['subtitle'].render("🏠 Room Info", True, ModernColors.NEON_CYAN)
        # self.screen.blit(room_title, (25, y_offset + 5))
        # y_offset += 25
        
        # # Display current room (placeholder)
        # room_text = f"Current: room_001"
        # room_surface = self.fonts['small'].render(room_text, True, ModernColors.TEXT_SECONDARY)
        # self.screen.blit(room_surface, (25, y_offset))
        # y_offset += 40
        
        # Bot list
        self._render_bot_list(game_engine, y_offset)
        y_offset += 150
        # Controls (at bottom)
        self._render_controls(self.screen_height - 120)
    def _render_title(self, y):
        """Render animated title"""
        title_text = "ARENA BATTLE"
        # Glow effect
        glow_intensity = int(100 + 50 * math.sin(self.title_glow_phase))
        glow_color = (*ModernColors.NEON_CYAN[:3], glow_intensity)
        # Main title
        title_surface = self.fonts['title'].render(title_text, True, ModernColors.TEXT_PRIMARY)
        title_rect = title_surface.get_rect(center=(self.ui_panel_width//2, y + 20))
        self.screen.blit(title_surface, title_rect)
    def _render_stats(self, game_engine, y):
        """Render compact statistics"""
        stats_title = self.fonts['subtitle'].render("📊 Statistics", True, ModernColors.NEON_CYAN)
        self.screen.blit(stats_title, (25, y))
        y += 25
        stats = game_engine.game_state.get_game_stats()
        # Compact stat display
        stat_lines = [
            f"Tick: {stats['tick']:,}",
            f"FPS: {stats['fps']:.1f}",
            f"Speed: {stats['speed_multiplier']}x",
            f"Uptime: {stats['uptime']:.0f}s",
            "",
            f"Bots: {stats['total_bots']} ({stats['alive_bots']} alive)",
            f"Bullets: {stats['active_bullets']}",
            f"Kills: {stats['total_kills']:,}",
            f"Deaths: {stats['total_deaths']:,}",
            f"Shots: {stats['total_bullets_fired']:,}",
        ]
        for line in stat_lines:
            if line:  # Skip empty lines
                line_surface = self.fonts['small'].render(line, True, ModernColors.TEXT_SECONDARY)
                self.screen.blit(line_surface, (25, y))
            y += 16
    def _render_bot_list(self, game_engine, y):
        """Render compact bot list"""
        bots_title = self.fonts['subtitle'].render("🤖 Active Bots", True, ModernColors.NEON_CYAN)
        self.screen.blit(bots_title, (25, y + 10))
        y += 25

        # Get bots from current viewing room
        if self.viewing_mode != "default":
            room_state = game_engine.get_room_state(self.viewing_mode)
            if room_state:
                bots = list(room_state.bots.values())[:5]
            else:
                bots = []
        else:
            # Fallback: get bots from first available room
            available_rooms = list(game_engine.room_states.keys())
            if available_rooms:
                first_room = game_engine.room_states[available_rooms[0]]
                bots = list(first_room.bots.values())[:5]
            else:
                bots = []

        print(f"🎨 RENDERER: Showing {len(bots)} bots from room {self.viewing_mode}")
        for bot in bots:
            # Status color
            if bot.state == BotState.ALIVE:
                color = ModernColors.BOT_ALIVE
                icon = "🟢"
            elif bot.state == BotState.INVULNERABLE:
                color = ModernColors.BOT_INVULNERABLE
                icon = "🟡"
            else:
                color = ModernColors.BOT_DEAD
                icon = "🔴"
            # Bot info
            bot_name = bot.name if len(bot.name) <= 12 else bot.name[:9] + "..."
            bot_text = f"{icon} {bot_name}"
            if bot == self.selected_bot:
                bot_text = f"► {bot_text}"
                color = ModernColors.NEON_CYAN
            bot_surface = self.fonts['small'].render(bot_text, True, color)
            self.screen.blit(bot_surface, (25, y))
            # K/D on same line
            kd_text = f"{bot.kills}K/{bot.deaths}D"
            kd_surface = self.fonts['tiny'].render(kd_text, True, ModernColors.TEXT_SECONDARY)
            self.screen.blit(kd_surface, (200, y))
            y += 18
    def _render_controls(self, y):
        """Render controls section"""
        controls_title = self.fonts['subtitle'].render("🎮 Controls", True, ModernColors.NEON_CYAN)
        self.screen.blit(controls_title, (25, y))
        y += 20
        controls = [
            "1,2,3,4 - Speed",
            "Click - Select Bot", 
            "D - Debug Mode",
            "R - Cycle Rooms",
            "S - Save Models",
            "ESC - Quit"
        ]
        for control in controls:
            control_surface = self.fonts['tiny'].render(control, True, ModernColors.TEXT_SECONDARY)
            self.screen.blit(control_surface, (25, y))
            y += 14
    def _render_arena(self, game_engine):
        """Render arena với room selection đúng - FIXED"""
        
        # 🔥 FIX: Logic chọn game state
        game_state = None
        room_info = ""
        
        print(f"🎨 RENDERER: Rendering arena, viewing_mode = {self.viewing_mode}")
        
        if self.viewing_mode != "default":
            # Hiển thị room cụ thể
            room_state = game_engine.get_room_state(self.viewing_mode)
            if room_state:
                game_state = room_state
                wall_count = len(room_state.walls)
                obstacle_count = wall_count - 4  # Trừ 4 boundary walls
                room_info = f"Room: {self.viewing_mode} ({wall_count} walls, {obstacle_count} obstacles)"
                print(f"🎨 RENDERER: Using room state '{self.viewing_mode}' with {wall_count} walls")
            else:
                # Fallback nếu không tìm thấy room state
                game_state = game_engine.game_state
                room_info = f"Default State (room '{self.viewing_mode}' not found)"
                print(f"🎨 RENDERER: Room '{self.viewing_mode}' not found, using default")
        else:
            # Fallback to first available room instead of default
            available_rooms = list(game_engine.room_states.keys())
            if available_rooms:
                fallback_room = available_rooms[0]
                game_state = game_engine.room_states[fallback_room]
                wall_count = len(game_state.walls)
                obstacle_count = wall_count - 4
                room_info = f"Viewing: {fallback_room} ({wall_count} walls, {obstacle_count} obstacles)"
                print(f"🎨 RENDERER: Using fallback room {fallback_room} with {wall_count} walls")
            else:
                # Create empty state for display
                from game_server.engine.game_state import GameState
                game_state = GameState()
                room_info = "No rooms available"
        
        # Arena layout
        arena_rect = pygame.Rect(
            self.arena_offset_x, 
            self.arena_offset_y,
            self.arena_width, 
            self.arena_height
        )
        
        # Header với room info
        header_text = f"🏟️ Combat Arena ({self.arena_width}x{self.arena_height})"
        header_surface = self.fonts['normal'].render(header_text, True, ModernColors.TEXT_PRIMARY)
        self.screen.blit(header_surface, (self.arena_offset_x, self.arena_offset_y - 30))
        
        # Room info detail
        room_surface = self.fonts['small'].render(room_info, True, ModernColors.TEXT_SECONDARY)
        self.screen.blit(room_surface, (self.arena_offset_x, self.arena_offset_y - 10))
        
        # Arena background
        pygame.draw.rect(self.screen, ModernColors.ARENA_BG, arena_rect)
        
        # Border color theo room
        if self.viewing_mode == "room_001":
            border_color = ModernColors.NEON_CYAN
        elif self.viewing_mode == "room_002":
            border_color = ModernColors.NEON_PINK
        else:
            border_color = ModernColors.NEON_YELLOW
            
        pygame.draw.rect(self.screen, border_color, arena_rect, width=2)
        
        # Render walls (QUAN TRỌNG)
        print(f"🎨 RENDERER: Rendering {len(game_state.walls)} walls")
        self._render_walls(game_state, arena_rect)
        
        # Render các element khác
        self._render_bullets(game_state, arena_rect)
        self._render_bots(game_state, arena_rect)
        
        # Debug info
        if self.show_debug:
            self._render_debug_overlay(game_state, arena_rect)
    
    def _render_walls(self, game_state, arena_rect):
        """Render walls với debug info"""
        print(f"🧱 RENDERER: Rendering {len(game_state.walls)} walls")
        
        for i, wall in enumerate(game_state.walls):
            wall_rect = pygame.Rect(
                arena_rect.x + wall.x,
                arena_rect.y + wall.y,
                wall.width,
                wall.height
            )
            
            # Debug: In thông tin wall
            if i < 6:  # Chỉ in 6 walls đầu để không spam
                print(f"🧱 Wall {i}: ({wall.x}, {wall.y}) {wall.width}x{wall.height}")
            
            # Render wall
            pygame.draw.rect(self.screen, ModernColors.WALL_PRIMARY, wall_rect)
            pygame.draw.rect(self.screen, ModernColors.WALL_BORDER, wall_rect, width=2)
            
            # Debug outline
            if self.show_debug:
                pygame.draw.rect(self.screen, ModernColors.NEON_YELLOW, wall_rect, width=1)
    
    def _render_bullets(self, game_state, arena_rect):
        """Render bullets with glow"""
        for bullet in game_state.bullets:
            bullet_x = arena_rect.x + bullet.x
            bullet_y = arena_rect.y + bullet.y
            bullet_radius = max(3, bullet.radius)
            
            # Glow effect
            for i in range(3, 0, -1):
                glow_radius = bullet_radius * (1 + i * 0.5)
                glow_alpha = 80 // i
                glow_color = (*ModernColors.BULLET_GLOW[:3], glow_alpha)
                
                glow_surf = pygame.Surface((glow_radius * 4, glow_radius * 4), pygame.SRCALPHA)
                pygame.draw.circle(glow_surf, glow_color, (glow_radius * 2, glow_radius * 2), glow_radius)
                self.screen.blit(glow_surf, (bullet_x - glow_radius * 2, bullet_y - glow_radius * 2), 
                               special_flags=pygame.BLEND_ALPHA_SDL2)
            
            # Core bullet
            pygame.draw.circle(self.screen, ModernColors.BULLET_CORE,
                             (int(bullet_x), int(bullet_y)), int(bullet_radius))
            
            # Debug info
            if self.show_debug:
                # Velocity vector
                vel_scale = 0.1
                end_x = bullet_x + bullet.vel_x * vel_scale
                end_y = bullet_y + bullet.vel_y * vel_scale
                pygame.draw.line(self.screen, ModernColors.NEON_YELLOW,
                               (int(bullet_x), int(bullet_y)),
                               (int(end_x), int(end_y)), 2)
    
    def _render_bots(self, game_state, arena_rect):
        """Render bots"""
        for bot in game_state.bots.values():
            self._render_bot(bot, arena_rect)
    
    def _render_bot(self, bot, arena_rect):
        """Render individual bot"""
        bot_x = arena_rect.x + bot.x
        bot_y = arena_rect.y + bot.y
        bot_radius = max(12, bot.radius)
        
        # Bot colors
        if bot.state == BotState.ALIVE:
            core_color = ModernColors.BOT_ALIVE
            glow_color = ModernColors.BOT_ALIVE_GLOW
        elif bot.state == BotState.INVULNERABLE:
            core_color = ModernColors.BOT_INVULNERABLE
            glow_color = ModernColors.BOT_INVULNERABLE_GLOW
        else:
            core_color = ModernColors.BOT_DEAD
            glow_color = (*ModernColors.BOT_DEAD[:3], 50)
        
        # Selection highlight
        if bot == self.selected_bot:
            for i in range(4, 0, -1):
                highlight_radius = bot_radius + i * 4
                highlight_alpha = 60 // i
                highlight_color = (*ModernColors.NEON_CYAN[:3], highlight_alpha)
                
                highlight_surf = pygame.Surface((highlight_radius * 4, highlight_radius * 4), pygame.SRCALPHA)
                pygame.draw.circle(highlight_surf, highlight_color,
                                 (highlight_radius * 2, highlight_radius * 2), highlight_radius)
                self.screen.blit(highlight_surf,
                               (bot_x - highlight_radius * 2, bot_y - highlight_radius * 2),
                               special_flags=pygame.BLEND_ALPHA_SDL2)
        
        # Bot glow
        if bot.state != BotState.DEAD:
            for i in range(3, 0, -1):
                glow_radius = bot_radius * (1 + i * 0.3)
                glow_alpha = 60 // i
                current_glow = (*glow_color[:3], glow_alpha)
                
                glow_surf = pygame.Surface((glow_radius * 4, glow_radius * 4), pygame.SRCALPHA)
                pygame.draw.circle(glow_surf, current_glow,
                                 (glow_radius * 2, glow_radius * 2), glow_radius)
                self.screen.blit(glow_surf,
                               (bot_x - glow_radius * 2, bot_y - glow_radius * 2),
                               special_flags=pygame.BLEND_ALPHA_SDL2)
        
        # Main bot body
        pygame.draw.circle(self.screen, core_color, (int(bot_x), int(bot_y)), int(bot_radius))
        pygame.draw.circle(self.screen, ModernColors.WHITE, (int(bot_x), int(bot_y)), int(bot_radius), 2)
        
        # Aim line
        if bot.state in [BotState.ALIVE, BotState.INVULNERABLE]:
            aim_length = bot_radius + 25
            aim_end_x = bot_x + math.cos(bot.aim_angle) * aim_length
            aim_end_y = bot_y + math.sin(bot.aim_angle) * aim_length
            
            pygame.draw.line(self.screen, ModernColors.NEON_YELLOW,
                           (int(bot_x), int(bot_y)),
                           (int(aim_end_x), int(aim_end_y)), 3)
            
            pygame.draw.circle(self.screen, ModernColors.NEON_YELLOW,
                             (int(aim_end_x), int(aim_end_y)), 5)
        
        # HP bar
        if bot.state != BotState.DEAD:
            self._render_hp_bar(bot, bot_x, bot_y - bot_radius - 18)
        
        # Bot name
        name_display = bot.name if len(bot.name) <= 10 else bot.name[:7] + "..."
        name_surface = self.fonts['tiny'].render(name_display, True, ModernColors.TEXT_PRIMARY)
        name_rect = name_surface.get_rect(center=(int(bot_x), int(bot_y + bot_radius + 20)))
        
        # Name background
        bg_rect = name_rect.inflate(6, 2)
        pygame.draw.rect(self.screen, (*ModernColors.BLACK[:3], 180), bg_rect)
        self.screen.blit(name_surface, name_rect)
        
        # Debug info
        if self.show_debug:
            debug_text = f"ID:{bot.id} HP:{bot.hp:.0f} K/D:{bot.kills}/{bot.deaths}"
            debug_surface = self.fonts['tiny'].render(debug_text, True, ModernColors.NEON_CYAN)
            self.screen.blit(debug_surface, (int(bot_x - 40), int(bot_y + bot_radius + 35)))
    
    def _render_hp_bar(self, bot, x, y):
        """Render HP bar"""
        bar_width = 50
        bar_height = 6
        
        # Background
        bg_rect = pygame.Rect(x - bar_width//2, y, bar_width, bar_height)
        pygame.draw.rect(self.screen, (*ModernColors.HP_BG[:3], 200), bg_rect)
        
        # HP fill
        hp_ratio = bot.hp / bot.max_hp
        fill_width = int(bar_width * hp_ratio)
        
        if fill_width > 0:
            if hp_ratio > 0.6:
                fill_color = ModernColors.HP_HIGH
            elif hp_ratio > 0.3:
                fill_color = ModernColors.HP_MEDIUM
            else:
                fill_color = ModernColors.HP_LOW
            
            fill_rect = pygame.Rect(x - bar_width//2, y, fill_width, bar_height)
            pygame.draw.rect(self.screen, fill_color, fill_rect)
        
        # Border
        pygame.draw.rect(self.screen, ModernColors.WHITE, bg_rect, width=1)
        
        # HP text
        hp_text = f"{bot.hp:.0f}"
        hp_surface = self.fonts['tiny'].render(hp_text, True, ModernColors.TEXT_PRIMARY)
        hp_rect = hp_surface.get_rect(center=(int(x), int(y - 8)))
        self.screen.blit(hp_surface, hp_rect)
    
    def _render_debug_overlay(self, game_state, arena_rect):
        """Render debug information overlay"""
        debug_y = arena_rect.bottom + 10
        
        debug_info = [
            f"Debug Mode: ON",
            f"Arena: {arena_rect.width}x{arena_rect.height}",
            f"Scale: {self.scale:.2f}",
            f"Bots: {len(game_state.bots)}",
            f"Bullets: {len(game_state.bullets)}",
            f"Walls: {len(game_state.walls)}"
        ]
        
        for i, info in enumerate(debug_info):
            debug_surface = self.fonts['tiny'].render(info, True, ModernColors.NEON_YELLOW)
            self.screen.blit(debug_surface, (arena_rect.x, debug_y + i * 12))
    
    def _render_selected_bot_info(self):
        """Render selected bot info panel"""
        if not self.selected_bot:
            return
        
        # Compact info panel
        panel_width = 200
        panel_height = 160
        panel_x = self.screen_width - panel_width - 10
        panel_y = 80
        
        panel_rect = pygame.Rect(panel_x, panel_y, panel_width, panel_height)
        
        # Panel background
        pygame.draw.rect(self.screen, (*ModernColors.BACKGROUND_TERTIARY[:3], 240), panel_rect)
        pygame.draw.rect(self.screen, ModernColors.NEON_CYAN, panel_rect, width=2)
        
        # Title
        title_surface = self.fonts['normal'].render("🎯 Selected Bot", True, ModernColors.NEON_CYAN)
        self.screen.blit(title_surface, (panel_x + 10, panel_y + 10))
        
        # Bot details
        details = [
            f"Name: {self.selected_bot.name[:15]}",
            f"ID: {self.selected_bot.id}",
            f"Player: {self.selected_bot.player_id[:12]}",
            f"State: {self.selected_bot.state.value.upper()}",
            f"HP: {self.selected_bot.hp:.1f}/{self.selected_bot.max_hp}",
            f"Position: ({self.selected_bot.x:.0f}, {self.selected_bot.y:.0f})",
            f"Kills: {self.selected_bot.kills}",
            f"Deaths: {self.selected_bot.deaths}",
            f"K/D: {self.selected_bot.kills/max(self.selected_bot.deaths,1):.2f}"
        ]
        
        detail_y = panel_y + 35
        for detail in details:
            detail_surface = self.fonts['small'].render(detail, True, ModernColors.TEXT_SECONDARY)
            self.screen.blit(detail_surface, (panel_x + 10, detail_y))
            detail_y += 14
    
    def _handle_key_press(self, key, game_engine):
        """Handle keyboard input - FIXED DEBUG KEY"""
        if key == pygame.K_ESCAPE:
            self.running = False
            logger.info("Exiting renderer...")
        elif key == pygame.K_1:
            self._set_speed(0, game_engine)
        elif key == pygame.K_2:
            self._set_speed(1, game_engine)
        elif key == pygame.K_3:
            self._set_speed(2, game_engine)
        elif key == pygame.K_4:
            self._set_speed(3, game_engine)
        elif key == pygame.K_d:
            # FIXED: Debug toggle now works properly
            self.show_debug = not self.show_debug
            debug_status = "ON" if self.show_debug else "OFF"
            logger.info(f"Debug mode: {debug_status}")
        elif key == pygame.K_c:
            self.selected_bot = None
            logger.info("Bot selection cleared")
        elif key == pygame.K_s:
            logger.info("Manual model save triggered")
        elif key == pygame.K_r:
            self._cycle_viewing_room(game_engine)
    
    def _set_speed(self, button_index, game_engine):
        """Set game speed with visual feedback"""
        if 0 <= button_index < len(self.speed_buttons):
            # Update button states
            for i, button in enumerate(self.speed_buttons):
                button.active = (i == button_index)
            
            # Update game speed
            game_engine.game_state.speed_multiplier = self.speed_buttons[button_index].speed
            logger.info(f"Speed changed to {self.speed_buttons[button_index].speed}x")
    
    def _handle_mouse_click(self, pos, game_engine):
        """Handle mouse clicks"""
        mouse_x, mouse_y = pos
        
        # Check speed buttons
        for i, button in enumerate(self.speed_buttons):
            if button.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=pos)):
                self._set_speed(i, game_engine)
                return
        
        # Check arena clicks for bot selection
        if mouse_x >= self.arena_offset_x and mouse_y >= self.arena_offset_y:
            # Convert screen coordinates to arena coordinates
            arena_x = mouse_x - self.arena_offset_x
            arena_y = mouse_y - self.arena_offset_y
            
            # Check if click is within arena bounds
            if 0 <= arena_x <= self.arena_width and 0 <= arena_y <= self.arena_height:
                # Find closest bot
                closest_bot = None
                closest_distance = float('inf')
                
                for bot in game_engine.game_state.bots.values():
                    dx = bot.x - arena_x
                    dy = bot.y - arena_y
                    distance = math.sqrt(dx*dx + dy*dy)
                    
                    if distance < bot.radius + 25 and distance < closest_distance:
                        closest_bot = bot
                        closest_distance = distance
                
                if closest_bot:
                    self.selected_bot = closest_bot
                    logger.info(f"Selected bot: {closest_bot.name} (ID: {closest_bot.id})")
                else:
                    self.selected_bot = None
    
    def _handle_mouse_motion(self, event):
        """Handle mouse motion for hover effects"""
        for button in self.speed_buttons:
            button.handle_event(event)
    
    def stop(self):
        """Stop the renderer"""
        self.running = False
        logger.info("Renderer stopping...")
    
    def _cleanup(self):
        """Clean up Pygame resources"""
        if pygame.get_init():
            pygame.quit()
        logger.info("Renderer stopped")

    def _cycle_viewing_room(self, game_engine):
        """Cycle through available room states - FIXED TO WORK IMMEDIATELY"""
        room_states = game_engine.get_all_room_states()
        
        print(f"🔄 RENDERER: Available room states: {list(room_states.keys())}")
        print(f"🔄 RENDERER: Current viewing mode: {self.viewing_mode}")
        
        if not room_states:
            logger.info("🔄 No room states available")
            return
        
        # Danh sách rooms: default + room states
        room_ids = list(room_states.keys())
        
        if self.viewing_mode not in room_ids:
            # Chuyển tới room đầu tiên (không phải default)
            self.viewing_mode = room_ids[1] if len(room_ids) > 1 else room_ids[0]
        else:
            # Cycle tới room tiếp theo
            current_idx = room_ids.index(self.viewing_mode)
            next_idx = (current_idx + 1) % len(room_ids)
            self.viewing_mode = room_ids[next_idx]
        
        logger.info(f"🔄 Now viewing: {self.viewing_mode}")
        print(f"🔄 RENDERER: Switched to: {self.viewing_mode}")


# Keep the original class name for compatibility
ModernGameRenderer = GameRenderer