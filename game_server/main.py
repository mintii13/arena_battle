import asyncio
import logging
import sys
import os
import time
from pathlib import Path

# Simple path handling
current_dir = os.path.dirname(__file__)
project_root = os.path.dirname(os.path.dirname(current_dir))
proto_dir = os.path.join(project_root, "proto")

# Add proto directory to Python path
sys.path.insert(0, proto_dir)

# Direct import from proto directory
try:
    from proto import arena_pb2, arena_pb2_grpc
    print("✅ Proto import successful in server main")
except ImportError as e:
    print(f"⚠️ Proto import failed at main: {e}")
    print(f"Proto dir: {proto_dir}")
    print(f"Files exist: {os.path.exists(os.path.join(proto_dir, 'arena_pb2.py'))}")
    sys.exit(1)

from game_server.engine.game_state import GameState
from game_server.engine.physics import PhysicsEngine
from game_server.networking.server import run_server
from game_server.ui.renderer import GameRenderer

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class GameEngine:
    def __init__(self):
        self.game_state = GameState()
        self.room_states = {}  # room_id -> GameState mapping
        self.physics_engines = {}  # room_id -> PhysicsEngine mapping
        self.physics = PhysicsEngine(self.game_state)
        self.running = False
        self.last_time = time.time()
        
        # Track match state for conditional physics
        self.match_active = False
        self.active_player_count = 0

    def get_or_create_room_state(self, room_id, arena_config=None):
        """Get existing room state or create new one"""
        if room_id not in self.room_states:
            room_state = GameState()
            room_state.room_id = room_id
            if arena_config:
                room_state._create_arena_walls(arena_config)
            self.room_states[room_id] = room_state
            self.physics_engines[room_id] = PhysicsEngine(room_state)
        return self.room_states[room_id]
    
    def get_room_state(self, room_id):
        """Get specific room state"""
        return self.room_states.get(room_id)
    
    def get_all_room_states(self):
        """Get all room states"""
        return self.room_states
    
    async def run(self):
        """Main game loop with multi-room physics"""
        logger.info("🎮 Starting multi-room game engine...")
        self.running = True
        
        while self.running:
            current_time = time.time()
            dt = (current_time - self.last_time) * self.game_state.speed_multiplier
            self.last_time = current_time
            
            # Update physics for each room
            for room_id, room_state in self.room_states.items():
                alive_bots = len(room_state.get_alive_bots())
                
                if alive_bots >= 2:
                    # Active room - full physics
                    self.physics_engines[room_id].update(min(dt, 0.1))
                elif alive_bots > 0:
                    # Waiting room - slow physics
                    self.physics_engines[room_id].update(min(dt, 0.1) * 0.1)
            
            # Also update default state for compatibility
            alive_bots = len(self.game_state.get_alive_bots())
            if alive_bots > 0:
                self.physics.update(min(dt, 0.1))
            # Control game speed - MUST yield control to other tasks
            sleep_time = 1/60 / self.game_state.speed_multiplier  
            await asyncio.sleep(max(0.001, sleep_time))
    
    def stop(self):
        self.running = False

async def main():
    """Main entry point for PvP Arena Battle Server với JSON logging options"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Arena Battle Game Server - PvP Only with JSON Logging')
    parser.add_argument('--port', type=int, default=50051, help='Server port')
    parser.add_argument('--no-ui', action='store_true', help='Run without UI (headless)')
    parser.add_argument('--log-level', default='INFO', help='Log level')
    parser.add_argument('--min-players', type=int, default=2, help='Minimum players to start match')
    parser.add_argument('--max-players', type=int, default=8, help='Maximum players per match')
    
    # JSON Logging options
    parser.add_argument('--enable-json-logging', action='store_true', default=True, 
                       help='Enable JSON logging of gRPC data (default: True)')
    parser.add_argument('--disable-json-logging', action='store_true', 
                       help='Disable JSON logging completely')
    parser.add_argument('--log-rotation-minutes', type=int, default=5,
                       help='JSON log file rotation interval in minutes (default: 5)')
    parser.add_argument('--log-dir', default='logs/server_grpc_data',
                       help='Directory for JSON log files')
    
    args = parser.parse_args()
    
    # Determine logging settings
    enable_logging = args.enable_json_logging and not args.disable_json_logging
    
    # Set log level
    logging.getLogger().setLevel(getattr(logging, args.log_level))
    
    # Create log directory if logging enabled
    if enable_logging:
        log_path = Path(args.log_dir)
        log_path.mkdir(parents=True, exist_ok=True)
    
    # Create game engine
    game_engine = GameEngine()
    
    # Create renderer if UI enabled
    renderer = None
    if not args.no_ui:
        try:
            renderer = GameRenderer()
            logger.info("✅ Renderer created successfully")
        except Exception as e:
            logger.error(f"❌ Renderer creation failed: {e}")
            renderer = None
    
    # Display startup banner
    logger.info("🤖 ==========================================")
    logger.info("🤖     ARENA BATTLE SERVER - ROOM MODE")
    logger.info("🤖 ==========================================")
    logger.info(f"🌐 Server port: {args.port}")
    logger.info(f"👥 Players required: {args.min_players}-{args.max_players}")
    logger.info(f"🎮 UI enabled: {'Yes' if not args.no_ui else 'No (headless)'}")
    logger.info("⚔️ Mode: PvP Only")
    logger.info("🎯 Waiting for AI bots to connect...")
    
    # JSON Logging info
    if enable_logging:
        logger.info("📝 ========== JSON LOGGING ENABLED ==========")
        logger.info(f"📁 Log directory: {args.log_dir}")
        logger.info(f"⏰ Rotation interval: {args.log_rotation_minutes} minutes")
        logger.info("📊 Logged data:")
        logger.info("   • Bot registrations & disconnections")
        logger.info("   • All observations sent to bots")
        logger.info("   • All actions received from bots")
        logger.info("   • Game events (kills, deaths, matches)")
        logger.info("   • Match events (start, end, player assignments)")
        logger.info("   • Error events & debugging info")
        logger.info("📝 =========================================")
    else:
        logger.info("📝 JSON Logging: DISABLED")
    
    if renderer:
        logger.info("🎨 UI Controls: 1,2,3,4 (speed), D (debug), ESC (quit)")
    
    logger.info("🤖 ==========================================")
    
    try:
        
        print("MAIN DEBUG: Starting game engine...")
        game_task = asyncio.create_task(game_engine.run())

        print("MAIN DEBUG: Starting server...")
        server_task = asyncio.create_task(run_server(game_engine, args.port, enable_logging=enable_logging))

        # Wait a moment for server to be ready
        await asyncio.sleep(0.5)

        if renderer:
            print("MAIN DEBUG: Starting renderer...")
            renderer_task = asyncio.create_task(renderer.run(game_engine))
            await asyncio.gather(game_task, server_task, renderer_task)
        else:
            await asyncio.gather(game_task, server_task)
    except KeyboardInterrupt:
        logger.info("🛑 Server stopped by user")
        if enable_logging:
            logger.info("📁 JSON log files saved to: " + args.log_dir)
    finally:
        game_engine.stop()
        if renderer:
            renderer.stop()

if __name__ == "__main__":
    asyncio.run(main())