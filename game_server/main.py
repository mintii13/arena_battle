# Main server entry
import asyncio
import logging
import sys
import os
import time
from pathlib import Path

# ✅ FIXED: Simple path handling
current_dir = os.path.dirname(__file__)
project_root = os.path.dirname(os.path.dirname(current_dir))
proto_dir = os.path.join(project_root, "proto")


# Import proto as a package (works with python -m ... from project root)
try:
    import proto.arena_pb2 as arena_pb2
    import proto.arena_pb2_grpc as arena_pb2_grpc
    print("✅ Proto import successful in server.py")
except ImportError as e:
    print(f"❌ Proto import failed: {e}")
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
    
    async def run(self):
        """Main game loop"""
        logger.info("🎮 Starting game engine...")
        self.running = True
        
        while self.running:
            current_time = time.time()
            dt = (current_time - self.last_time) * self.game_state.speed_multiplier
            self.last_time = current_time
            
            # Update physics
            self.physics.update(min(dt, 0.1))  # Cap dt to prevent large jumps
            
            # Control game speed
            sleep_time = 1/60 / self.game_state.speed_multiplier
            await asyncio.sleep(max(0.001, sleep_time))
    
    def stop(self):
        self.running = False

async def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Arena Battle Game Server')
    parser.add_argument('--port', type=int, default=50051, help='Server port')
    parser.add_argument('--no-ui', action='store_true', help='Run without UI')
    parser.add_argument('--log-level', default='INFO', help='Log level')
    
    args = parser.parse_args()
    
    # Set log level
    logging.getLogger().setLevel(getattr(logging, args.log_level))
    
    # Create game engine
    game_engine = GameEngine()
    
    # Create renderer if UI enabled
    renderer = None
    if not args.no_ui:
        renderer = GameRenderer()
    
    logger.info(f"🚀 Starting Arena Battle Server on port {args.port}")
    if renderer:
        logger.info("🎨 UI enabled - Press 1,2,3,4 for speed control")
    
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
        logger.info("⏹️ Server stopped by user")
    finally:
        game_engine.stop()
        if renderer:
            renderer.stop()

if __name__ == "__main__":
    asyncio.run(main())