import json
import logging
import time
import os
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

@dataclass
class Player:
    """Represents a connected player"""
    id: str
    bot_name: str
    connection_time: float = field(default_factory=time.time)
    bot_id: Optional[int] = None

@dataclass 
class Room:
    """Represents a game room"""
    id: str
    password: str
    max_players: int
    arena_config: dict
    players: List[Player] = field(default_factory=list)
    created_time: float = field(default_factory=time.time)

class RoomManager:
    """Room-based system replacing matchmaking - FIXED"""
    
    def __init__(self, rooms_config_path: str = "arena_battle_game/rooms.json"):
        print(f"🔧 ROOM_MANAGER: Init started")
        self.rooms_config_path = rooms_config_path
        self.rooms: Dict[str, Room] = {}
        self.player_to_room: Dict[str, str] = {}
        
        # Statistics
        self.total_players_served = 0
        
        # Load rooms from config - FIXED PATH RESOLUTION
        self._load_rooms_config()
        print(f"✅ ROOM_MANAGER: Initialized with {len(self.rooms)} rooms")
    
    def _load_rooms_config(self):
        """Load rooms from JSON config file - FIXED PATH RESOLUTION"""
        try:
            # ✅ FIX: Tìm file từ project root
            current_file = os.path.abspath(__file__)
            current_dir = os.path.dirname(current_file)
            
            # Đi từ game_server/networking/room_manager.py -> project root
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
            config_path = os.path.join(project_root, self.rooms_config_path)
            
            print(f"🔍 ROOM_MANAGER: Looking for config at: {config_path}")
            print(f"🔍 ROOM_MANAGER: File exists: {os.path.exists(config_path)}")
            
            if not os.path.exists(config_path):
                logger.error(f"❌ rooms.json not found at {config_path}")
                self._create_default_rooms()
                return
                
            with open(config_path, 'r', encoding='utf-8') as f:
                rooms_data = json.load(f)
            
            print(f"📋 ROOM_MANAGER: Successfully loaded {len(rooms_data)} rooms")
            
            for room_id, room_config in rooms_data.items():
                room = Room(
                    id=room_id,
                    password=room_config['password'],
                    max_players=room_config['max_players'],
                    arena_config=room_config['arena']
                )
                self.rooms[room_id] = room
                
                # Debug obstacle info
                obstacle_count = len(room_config['arena'].get('obstacles', []))
                print(f"🏠 ROOM_MANAGER: Room '{room_id}' -> {obstacle_count} obstacles")
                for i, obs in enumerate(room_config['arena'].get('obstacles', [])):
                    print(f"   Obstacle {i+1}: ({obs['x']}, {obs['y']}) {obs['width']}x{obs['height']}")
                
                logger.info(f"📋 Loaded room: {room_id} (max: {room.max_players} players, {obstacle_count} obstacles)")
                
        except Exception as e:
            logger.error(f"💥 Failed to load rooms config: {e}")
            print(f"🔥 ROOM_MANAGER ERROR: {e}")
            import traceback
            traceback.print_exc()
            self._create_default_rooms()
    
    def _create_default_rooms(self):
        """Create default rooms if config loading fails"""
        print("🔧 ROOM_MANAGER: Creating default rooms...")
        default_rooms = {
            "room_default": {
                "password": "default123",
                "max_players": 4,
                "arena": {
                    "width": 800,
                    "height": 600,
                    "obstacles": [
                        {"x": 300, "y": 200, "width": 6000, "height": 120},
                        {"x": 500, "y": 350, "width": 120, "height": 60}
                    ]
                }
            }
        }
        
        for room_id, room_config in default_rooms.items():
            room = Room(
                id=room_id,
                password=room_config['password'],
                max_players=room_config['max_players'],
                arena_config=room_config['arena']
            )
            self.rooms[room_id] = room
            logger.info(f"📋 Created default room: {room_id}")
    
    # Rest of the methods remain the same...
    def join_room(self, player_id: str, bot_name: str, room_id: str, room_password: str) -> Dict:
        """Join a specific room with password"""
        
        # Check if player already in a room
        if player_id in self.player_to_room:
            return {
                'success': False,
                'message': f'Player {player_id} already in room {self.player_to_room[player_id]}',
                'bot_id': 0
            }
        
        # Check if room exists
        if room_id not in self.rooms:
            available_rooms = list(self.rooms.keys())
            return {
                'success': False,
                'message': f"❌ Room ID '{room_id}' does not exist. Available: {available_rooms}",
                'bot_id': 0
            }
        
        room = self.rooms[room_id]
        
        # Check password
        if room.password != room_password:
            return {
                'success': False,
                'message': f"❌ Wrong password for room '{room_id}'",
                'bot_id': 0
            }
        
        # Check room capacity
        if len(room.players) >= room.max_players:
            return {
                'success': False,
                'message': f"❌ Room '{room_id}' is full ({len(room.players)}/{room.max_players} players)",
                'bot_id': 0
            }
        
        # Join room
        player = Player(id=player_id, bot_name=bot_name)
        room.players.append(player)
        self.player_to_room[player_id] = room_id
        self.total_players_served += 1
        
        # Generate bot ID
        bot_id = self._generate_bot_id(player, room)
        player.bot_id = bot_id
        
        players_count = len(room.players)
        status_msg = f"✅ Joined room {room_id} ({players_count}/{room.max_players} players)"
        
        if players_count >= 2:
            status_msg += " - ⚔️ Battle active!"
        else:
            status_msg += " - ⏳ Waiting for more players..."
        
        # Debug arena config being returned
        obstacle_count = len(room.arena_config.get('obstacles', []))
        print(f"🎯 ROOM_MANAGER: Returning arena config with {obstacle_count} obstacles for room {room_id}")
        
        logger.info(f"👤 {player_id} → Room {room_id} ({players_count}/{room.max_players})")
        
        return {
            'success': True,
            'room_id': room_id,
            'bot_id': bot_id,
            'message': status_msg,
            'players_in_room': players_count,
            'arena_config': room.arena_config 
        }
    
    def _generate_bot_id(self, player: Player, room: Room) -> int:
        """Generate unique bot ID for player in room"""
        bot_id = abs(hash(f"{player.id}_{room.id}")) % 10000
        return bot_id
    
    def leave_room(self, player_id: str) -> bool:
        """Remove player from room"""
        room_id = self.player_to_room.get(player_id)
        if not room_id or room_id not in self.rooms:
            return False
        
        room = self.rooms[room_id]
        
        # Remove player from room
        room.players = [p for p in room.players if p.id != player_id]
        del self.player_to_room[player_id]
        
        logger.info(f"👋 Player {player_id} left room {room_id} ({len(room.players)} remaining)")
        return True
    
    def get_room_info(self, room_id: str) -> Dict:
        """Get detailed room information"""
        if room_id not in self.rooms:
            return {'error': f'Room {room_id} not found'}
        
        room = self.rooms[room_id]
        return {
            'room_id': room.id,
            'players': [
                {
                    'id': p.id,
                    'name': p.bot_name,
                    'bot_id': p.bot_id,
                    'connected_time': time.time() - p.connection_time
                }
                for p in room.players
            ],
            'player_count': len(room.players),
            'max_players': room.max_players,
            'arena_config': room.arena_config,
            'is_active': len(room.players) >= 2
        }
    
    def get_all_rooms(self) -> List[Dict]:
        """Get list of all rooms with player counts"""
        rooms_list = []
        for room in self.rooms.values():
            rooms_list.append({
                'id': room.id,
                'players': len(room.players),
                'max_players': room.max_players,
                'is_active': len(room.players) >= 2,
                'player_names': [p.bot_name for p in room.players]
            })
        return rooms_list
    
    def get_statistics(self) -> Dict:
        """Get room manager statistics"""
        total_active_players = sum(len(room.players) for room in self.rooms.values())
        active_rooms = len([r for r in self.rooms.values() if len(r.players) >= 2])
        
        return {
            'total_rooms': len(self.rooms),
            'active_rooms': active_rooms,
            'total_active_players': total_active_players,
            'total_players_served': self.total_players_served,
            'rooms_info': self.get_all_rooms()
        }