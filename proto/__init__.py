# proto/__init__.py
# Protocol buffer package

# Import generated files
from .arena_pb2 import *
from .arena_pb2_grpc import *

# Make available at package level
from . import arena_pb2
from . import arena_pb2_grpc

__all__ = ['arena_pb2', 'arena_pb2_grpc']