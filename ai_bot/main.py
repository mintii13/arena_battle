import asyncio
import logging
import argparse
import sys
import os
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from ai_bot.models.network import PPONetwork, ObservationProcessor
from ai_bot.training.ppo import PPOTrainer
from ai_bot.training.buffer import ExperienceBuffer
from ai_bot.client.bot_client import BotClient

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def main():
    parser = argparse.ArgumentParser(description='Arena Battle AI Bot')
    parser.add_argument('--host', default='localhost', help='Server host')
    parser.add_argument('--port', type=int, default=50051, help='Server port')
    parser.add_argument('--player-id', required=True, help='Unique player ID')
    parser.add_argument('--bot-name', help='Bot name (default: player ID)')
    parser.add_argument('--model-path', help='Path to existing model file')
    
    # Removed --self-play, --clones - server manages matchmaking now
    
    args = parser.parse_args()
    
    if not args.bot_name:
        args.bot_name = f"Bot_{args.player_id}"
    
    logger.info(f"Starting AI Bot: {args.bot_name}")
    logger.info(f"Player ID: {args.player_id}")
    if args.model_path:
        logger.info(f"Loading model from: {args.model_path}")
    
    # Create AI components
    network = PPONetwork()
    trainer = PPOTrainer(network)
    obs_processor = ObservationProcessor()
    buffer = ExperienceBuffer()
    
    # Load existing model if provided
    if args.model_path and os.path.exists(args.model_path):
        try:
            import torch
            checkpoint = torch.load(args.model_path, map_location='cpu')
            network.load_state_dict(checkpoint['network_state_dict'])
            logger.info("Model loaded successfully")
        except Exception as e:
            logger.warning(f"Failed to load model: {e}, starting with fresh model")
    
    # Create bot client - no mode selection, server decides
    bot_client = BotClient(args.player_id, args.bot_name, trainer, obs_processor)
    
    try:
        await bot_client.connect_and_play(
            host=args.host,
            port=args.port
        )
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")

if __name__ == "__main__":
    asyncio.run(main())