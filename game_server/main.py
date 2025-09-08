# Main server entry
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
    print(f"❌ Proto import failed at main: {e}")
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
        self.physics = PhysicsEngine(self.game_state)
        self.running = False
        self.last_time = time.time()
        
        # Track match state for conditional physics
        self.match_active = False
        self.active_player_count = 0
    
    async def run(self):
        """Main game loop with conditional physics"""
        logger.info("🎮 Starting PvP game engine...")
        self.running = True
        
        while self.running:
            current_time = time.time()
            dt = (current_time - self.last_time) * self.game_state.speed_multiplier
            self.last_time = current_time
            
            # Check if we have enough players for active gameplay
            alive_bots = len(self.game_state.get_alive_bots())
            
            if alive_bots >= 2:
                if not self.match_active:
                    self.match_active = True
                    logger.info(f"⚔️ PvP match activated! {alive_bots} players in arena")
                
                # Run physics when match is active
                self.physics.update(min(dt, 0.1))
                self.active_player_count = alive_bots
                
            else:
                if self.match_active:
                    self.match_active = False
                    logger.info(f"⏸️ Match paused - waiting for players ({alive_bots}/2 minimum)")
                
                # Still update physics but at reduced rate for waiting players
                if alive_bots > 0:
                    self.physics.update(min(dt, 0.1) * 0.1)  # Slow physics
                self.active_player_count = alive_bots
            
            # Control game speed
            sleep_time = 1/60 / self.game_state.speed_multiplier
            await asyncio.sleep(max(0.001, sleep_time))
    
    def stop(self):
        self.running = False

async def main():
    """Main entry point for PvP Arena Battle Server"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Arena Battle Game Server - PvP Only')
    parser.add_argument('--port', type=int, default=50051, help='Server port')
    parser.add_argument('--no-ui', action='store_true', help='Run without UI (headless)')
    parser.add_argument('--log-level', default='INFO', help='Log level')
    parser.add_argument('--min-players', type=int, default=2, help='Minimum players to start match')
    parser.add_argument('--max-players', type=int, default=8, help='Maximum players per match')
    
    args = parser.parse_args()
    
    # Set log level
    logging.getLogger().setLevel(getattr(logging, args.log_level))
    
    # Create game engine
    game_engine = GameEngine()
    
    # Create renderer if UI enabled
    renderer = None
    if not args.no_ui:
        renderer = GameRenderer()
    
    # Display startup banner
    logger.info("🤖 ==========================================")
    logger.info("🤖     ARENA BATTLE SERVER - PVP MODE")
    logger.info("🤖 ==========================================")
    logger.info(f"🌐 Server port: {args.port}")
    logger.info(f"👥 Players required: {args.min_players}-{args.max_players}")
    logger.info(f"🎮 UI enabled: {'Yes' if not args.no_ui else 'No (headless)'}")
    logger.info("⚔️ Mode: PvP Only (no self-play)")
    logger.info("🎯 Waiting for AI bots to connect...")
    
    if renderer:
        logger.info("🎨 UI Controls: 1,2,3,4 (speed), D (debug), ESC (quit)")
    
    logger.info("🤖 ==========================================")
    
    try:
        # Start all tasks
        tasks = [
            game_engine.run(),
            run_server(game_engine, args.port)
        ]
        
        if renderer:
            tasks.append(renderer.run(game_engine))
        
        await asyncio.gather(*tasks)
        
    except KeyboardInterrupt:
        logger.info("🛑 Server stopped by user")
    finally:
        game_engine.stop()
        if renderer:
            renderer.stop()

if __name__ == "__main__":
    asyncio.run(main())