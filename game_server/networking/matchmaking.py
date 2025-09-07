import asyncio
import uuid
import logging
import time
from typing import Dict, List, Set
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)

class MatchMode(Enum):
    SELF_PLAY = "self_play"
    PVP = "pvp"
    PRACTICE = "practice"

@dataclass
class Player:
    """Represents a connected player"""
    id: str
    bot_name: str
    connection_time: float = field(default_factory=time.time)
    skill_level: int = 1  # For future matchmaking

@dataclass
class Match:
    """Represents a match/room"""
    id: str
    mode: MatchMode
    players: List[Player] = field(default_factory=list)
    bot_count: int = 2  # Total bots in this match
    max_players: int = 1  # Max human players
    created_time: float = field(default_factory=time.time)
    is_active: bool = True

class ServerMatchmaker:
    """Server-side matchmaking system"""
    
    def __init__(self):
        self.waiting_players: List[Player] = []
        self.active_matches: Dict[str, Match] = {}
        self.player_to_match: Dict[str, str] = {}  # player_id -> match_id
        
        # Auto-create matches
        self._create_default_matches()
    
    def _create_default_matches(self):
        """Create default available matches"""
        # Self-play practice match
        self_play_match = Match(
            id="selfplay_001",
            mode=MatchMode.SELF_PLAY,
            bot_count=3,  # 1 player + 2 clones
            max_players=1
        )
        self.active_matches[self_play_match.id] = self_play_match
        
        # PvP match
        pvp_match = Match(
            id="pvp_001", 
            mode=MatchMode.PVP,
            bot_count=2,  # 2 players
            max_players=2
        )
        self.active_matches[pvp_match.id] = pvp_match
        
        logger.info("Created default matches: Self-play and PvP")
    
    def register_player(self, player_id: str, bot_name: str) -> Dict:
        """Register player and auto-assign to match"""
        player = Player(id=player_id, bot_name=bot_name)
        
        # Auto-assign based on simple logic
        assigned_match = self._auto_assign_match(player)
        
        if assigned_match:
            # Add player to match
            assigned_match.players.append(player)
            self.player_to_match[player_id] = assigned_match.id
            
            # Generate bots for this player
            bot_ids = self._generate_bot_ids(player, assigned_match)
            
            logger.info(f"Player {player_id} assigned to {assigned_match.mode.value} match")
            logger.info(f"Generated {len(bot_ids)} bots for player")
            
            return {
                'success': True,
                'match_id': assigned_match.id,
                'match_mode': assigned_match.mode.value,
                'bot_ids': bot_ids,
                'message': f"Assigned to {assigned_match.mode.value} match"
            }
        else:
            # Add to waiting queue
            self.waiting_players.append(player)
            
            return {
                'success': True,
                'match_id': 'waiting',
                'match_mode': 'queue',
                'bot_ids': [],
                'message': 'Added to waiting queue'
            }
    
    def _auto_assign_match(self, player: Player) -> Match:
        """Auto-assign player to best available match"""
        # Priority 1: Self-play if available
        for match in self.active_matches.values():
            if (match.mode == MatchMode.SELF_PLAY and 
                len(match.players) < match.max_players):
                return match
        
        # Priority 2: PvP if available  
        for match in self.active_matches.values():
            if (match.mode == MatchMode.PVP and
                len(match.players) < match.max_players):
                return match
        
        # Priority 3: Create new self-play match
        new_match_id = f"selfplay_{len(self.active_matches) + 1:03d}"
        new_match = Match(
            id=new_match_id,
            mode=MatchMode.SELF_PLAY,
            bot_count=3,
            max_players=1
        )
        self.active_matches[new_match_id] = new_match
        logger.info(f"Created new self-play match: {new_match_id}")
        
        return new_match
    
    def _generate_bot_ids(self, player: Player, match: Match) -> List[int]:
        """Generate bot IDs based on match mode"""
        bot_ids = []
        
        if match.mode == MatchMode.SELF_PLAY:
            # 1 main bot + 2 clones
            for i in range(3):
                bot_id = hash(f"{player.id}_{match.id}_{i}") % 10000
                bot_ids.append(bot_id)
        
        elif match.mode == MatchMode.PVP:
            # 1 bot per player
            bot_id = hash(f"{player.id}_{match.id}") % 10000
            bot_ids.append(bot_id)
        
        return bot_ids
    
    def get_match_info(self, player_id: str) -> Dict:
        """Get match information for player"""
        match_id = self.player_to_match.get(player_id)
        if not match_id:
            return {'error': 'Player not in any match'}
        
        match = self.active_matches.get(match_id)
        if not match:
            return {'error': 'Match not found'}
        
        return {
            'match_id': match.id,
            'mode': match.mode.value,
            'players': [p.bot_name for p in match.players],
            'bot_count': match.bot_count,
            'is_active': match.is_active
        }
    
    def remove_player(self, player_id: str):
        """Remove player from match"""
        match_id = self.player_to_match.get(player_id)
        if match_id and match_id in self.active_matches:
            match = self.active_matches[match_id]
            match.players = [p for p in match.players if p.id != player_id]
            
            # Remove match if empty
            if not match.players and match_id not in ["selfplay_001", "pvp_001"]:
                del self.active_matches[match_id]
        
        if player_id in self.player_to_match:
            del self.player_to_match[player_id]
    
    def get_available_matches(self) -> List[Dict]:
        """Get list of available matches for UI"""
        matches = []
        for match in self.active_matches.values():
            matches.append({
                'id': match.id,
                'mode': match.mode.value,
                'players': len(match.players),
                'max_players': match.max_players,
                'available': len(match.players) < match.max_players
            })
        return matches