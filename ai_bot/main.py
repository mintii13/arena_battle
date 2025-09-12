import asyncio
import logging
import argparse
import sys
import os
import signal
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from ai_bot.models.network import PPONetwork, ObservationProcessor
from ai_bot.training.ppo import PPOTrainer
from ai_bot.training.buffer import ExperienceBuffer
from ai_bot.client.bot_client import BotClient

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Global bot client for graceful shutdown
bot_client = None

def signal_handler(sig, frame):
    """Handle Ctrl+C gracefully with auto-save"""
    global bot_client
    if bot_client:
        logger.info("🛑 Received shutdown signal - saving model...")
        asyncio.create_task(bot_client._save_model("manual_shutdown"))
    sys.exit(0)

def find_latest_model(player_id, models_dir):
    """Find the latest model for a player"""
    models_path = Path(models_dir)
    if not models_path.exists():
        return None
    
    # Look for models matching player ID pattern
    pattern = f"{player_id}_*.pth"
    model_files = list(models_path.glob(pattern))
    
    if not model_files:
        return None
    
    # Sort by modification time, newest first
    model_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
    return str(model_files[0])

def list_available_models(player_id, models_dir):
    """List available models for a player"""
    models_path = Path(models_dir)
    if not models_path.exists():
        return []
    
    pattern = f"{player_id}_*.pth"
    model_files = list(models_path.glob(pattern))
    
    # Sort by modification time, newest first
    model_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
    
    models_info = []
    for model_file in model_files:
        try:
            import torch
            checkpoint = torch.load(model_file, map_location='cpu')
            info = {
                'file': str(model_file),
                'name': model_file.name,
                'save_type': checkpoint.get('save_type', 'unknown'),
                'kd_ratio': checkpoint.get('kd_ratio', 0),
                'accuracy': checkpoint.get('accuracy', 0),
                'episodes': checkpoint.get('episode_count', 0),
                'save_time': checkpoint.get('save_time', 'unknown')
            }
            models_info.append(info)
        except Exception as e:
            logger.warning(f"⚠️ Could not read model {model_file}: {e}")
    
    return models_info

async def main():
    global bot_client
    
    parser = argparse.ArgumentParser(description='Arena Battle AI Bot - Enhanced PvP with Auto-Save')
    parser.add_argument('--host', default='localhost', help='Server host')
    parser.add_argument('--port', type=int, default=50051, help='Server port')
    parser.add_argument('--player-id', required=True, help='Unique player ID')
    parser.add_argument('--bot-name', help='Bot name (default: enhanced player ID)')
    parser.add_argument('--model-path', help='Path to specific model file to load')
    parser.add_argument('--auto-load', action='store_true', help='Auto-load latest model for player')
    parser.add_argument('--list-models', action='store_true', help='List available models and exit')
    parser.add_argument('--models-dir', default='models/checkpoints', help='Models directory')
    parser.add_argument('--save-interval', type=int, default=300, help='Auto-save interval in seconds')
    parser.add_argument('--room-id', required=True, help='Room ID to join')
    parser.add_argument('--room-password', required=True, help='Room password')
    
    args = parser.parse_args()
    
    # Set up signal handler for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    
    if not args.bot_name:
        args.bot_name = f"{args.player_id}"
    
    # List models if requested
    if args.list_models:
        logger.info(f"📋 Available models for player '{args.player_id}':")
        models = list_available_models(args.player_id, args.models_dir)
        
        if not models:
            logger.info("❌ No models found for this player")
        else:
            for i, model in enumerate(models):
                logger.info(f"  {i+1}. {model['name']}")
                logger.info(f"     Type: {model['save_type']}, K/D: {model['kd_ratio']:.2f}")
                logger.info(f"     Accuracy: {model['accuracy']:.1f}%, Episodes: {model['episodes']}")
                logger.info(f"     Saved: {model['save_time']}")
                logger.info("")
        return
    
    # Display enhanced startup banner
    logger.info("🤖 ==========================================")
    logger.info("🤖   ARENA BATTLE AI BOT")
    logger.info("🤖 ==========================================")
    logger.info(f"🤖 Bot Name: {args.bot_name}")
    logger.info(f"🤖 Player ID: {args.player_id}")
    logger.info(f"🌐 Server: {args.host}:{args.port}")
    logger.info("⚔️ Mode: PvP Combat")
    logger.info("🧠 Features: Wall Avoidance + Smart Aiming + Auto-Save")
    logger.info(f"💾 Models Directory: {args.models_dir}")
    logger.info(f"⏰ Auto-save Interval: {args.save_interval}s")
    
    # Model loading logic
    model_to_load = None
    
    if args.model_path:
        # Specific model requested
        if os.path.exists(args.model_path):
            model_to_load = args.model_path
            logger.info(f"🎯 Loading specific model: {args.model_path}")
        else:
            logger.error(f"❌ Model file not found: {args.model_path}")
            return
    elif args.auto_load:
        # Auto-load latest model
        model_to_load = find_latest_model(args.player_id, args.models_dir)
        if model_to_load:
            logger.info(f"🔄 Auto-loading latest model: {model_to_load}")
        else:
            logger.info("🆕 No existing models found - starting fresh")
    else:
        # Check if models exist and offer to load
        latest_model = find_latest_model(args.player_id, args.models_dir)
        if latest_model:
            logger.info(f"💡 Found existing model: {Path(latest_model).name}")
            logger.info("   Use --auto-load to load it automatically")
            logger.info("   Use --list-models to see all available models")
        logger.info("🆕 Starting with fresh neural network")
    
    logger.info("🤖 ==========================================")
    
    # Create AI components
    network = PPONetwork()
    trainer = PPOTrainer(network)
    obs_processor = ObservationProcessor()
    buffer = ExperienceBuffer()
    
    # Create enhanced bot client
    bot_client = BotClient(args.player_id, args.bot_name, trainer, obs_processor, args.room_id, args.room_password)
    
    # Set auto-save interval
    bot_client.save_interval = args.save_interval
    
    # Load model if specified
    if model_to_load:
        success = bot_client.load_model(model_to_load)
        if not success:
            logger.warning("⚠️ Model loading failed - continuing with fresh network")
    
    try:
        logger.info("🔌 Connecting to Arena Battle Server...")
        logger.info("⏳ Server will automatically assign to PvP match")
        logger.info("🎯 Minimum 2 players required to start battle")
        logger.info("💾 Model will auto-save periodically and on improvements")
        logger.info("🛑 Press Ctrl+C to stop and save model")
        
        await bot_client.connect_and_play(
            host=args.host,
            port=args.port
        )
    except KeyboardInterrupt:
        logger.info("🛑 Bot stopped by user - saving final model...")
        await bot_client._save_model("user_stop")
        logger.info("👋 Goodbye!")
    except Exception as e:
        logger.error(f"💥 Unexpected error: {e}")
        if bot_client:
            await bot_client._save_model("error_save")

if __name__ == "__main__":
    asyncio.run(main())