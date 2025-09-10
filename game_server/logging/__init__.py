"""
Server-side JSON logging package for Arena Battle Game

This package provides JSON logging capabilities for gRPC data without
requiring any changes to AI bot clients.

Usage:
    from game_server.logging.json_logger import ServerJSONLogger
    
    logger = ServerJSONLogger(log_dir="logs/grpc_data", rotation_minutes=5)
    logger.log_observation_sent(bot_id, player_id, observation_data)
    logger.log_action_received(bot_id, player_id, action_data)
    logger.close()
"""

from .json_logger import ServerJSONLogger, observation_to_dict, action_to_dict

__all__ = ['ServerJSONLogger', 'observation_to_dict', 'action_to_dict']

__version__ = "1.0.0"