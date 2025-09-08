import asyncio
import uuid
import logging
import time
from typing import Dict, List, Set, Optional
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)

class MatchMode(Enum):
    PVP = "pvp"
    WAITING = "waiting"

class MatchState(Enum):
    WAITING_FOR_PLAYERS = "waiting_for_players"
    ACTIVE = "active"
    ENDING = "ending"

@dataclass
class Player:
    """Represents a connected player"""
    id: str
    bot_name: str
    connection_time: float = field(default_factory=time.time)
    skill_level: int = 1  # For future ELO/ranking
    bot_id: Optional[int] = None  # Assigned bot ID in game

@dataclass
class Match:
    """Represents a PvP match"""
    id: str
    players: List[Player] = field(default_factory=list)
    state: MatchState = MatchState.WAITING_FOR_PLAYERS
    created_time: float = field(default_factory=time.time)
    started_time: Optional[float] = None
    min_players: int = 2
    max_players: int = 8  # Support up to 8 players per arena

class ServerMatchmaker:
    """PvP-only matchmaking system"""
    
    def __init__(self, min_players: int = 2, max_players: int = 8):
        self.min_players = min_players
        self.max_players = max_players
        
        # Active data structures
        self.waiting_players: List[Player] = []
        self.active_matches: Dict[str, Match] = {}
        self.player_to_match: Dict[str, str] = {}  # player_id -> match_id
        
        # Statistics
        self.total_matches_created = 0
        self.total_players_served = 0
        
        logger.info(f"🎮 PvP Matchmaker initialized (min: {min_players}, max: {max_players} players)")
    
    def register_player(self, player_id: str, bot_name: str) -> Dict:
        """Register player for PvP matchmaking"""
        if player_id in self.player_to_match:
            return {
                'success': False,
                'message': f'Player {player_id} already registered',
                'bot_id': 0
            }
        
        player = Player(id=player_id, bot_name=bot_name)
        logger.info(f"👤 Player registered: {player_id} ({bot_name})")
        
        # Try to find or create match
        match = self._find_or_create_match(player)
        
        if match:
            # Add player to match
            match.players.append(player)
            self.player_to_match[player_id] = match.id
            self.total_players_served += 1
            
            # Check if we can start the match
            if len(match.players) >= self.min_players and match.state == MatchState.WAITING_FOR_PLAYERS:
                self._start_match(match)
            
            # Generate single bot ID for this player
            bot_id = self._generate_bot_id(player, match)
            player.bot_id = bot_id
            
            status_msg = self._get_match_status_message(match)
            
            logger.info(f"✅ {player_id} → Match {match.id} ({len(match.players)}/{self.max_players})")
            
            return {
                'success': True,
                'match_id': match.id,
                'match_mode': 'pvp',
                'bot_id': bot_id,
                'message': status_msg,
                'players_in_match': len(match.players),
                'match_state': match.state.value
            }
        else:
            # This shouldn't happen with current logic, but handle gracefully
            return {
                'success': False,
                'message': 'No available matches and could not create new match',
                'bot_id': 0
            }
    
    def _find_or_create_match(self, player: Player) -> Match:
        """Find available match or create new one"""
        # Look for waiting or active matches with space
        for match in self.active_matches.values():
            if len(match.players) < self.max_players:
                logger.debug(f"🔍 Found available match: {match.id}")
                return match
        
        # Create new match
        match_id = f"pvp_{self.total_matches_created + 1:03d}"
        new_match = Match(
            id=match_id,
            min_players=self.min_players,
            max_players=self.max_players
        )
        
        self.active_matches[match_id] = new_match
        self.total_matches_created += 1
        
        logger.info(f"🆕 Created new PvP match: {match_id}")
        return new_match
    
    def _start_match(self, match: Match):
        """Start a match when minimum players reached"""
        if match.state != MatchState.WAITING_FOR_PLAYERS:
            return
        
        match.state = MatchState.ACTIVE
        match.started_time = time.time()
        
        player_names = [p.bot_name for p in match.players]
        logger.info(f"🚀 Match {match.id} STARTED! Players: {', '.join(player_names)}")
        
        # Notify about match start (could be used for events)
        for player in match.players:
            logger.debug(f"   - {player.bot_name} (ID: {player.id}) ready for battle")
    
    def _generate_bot_id(self, player: Player, match: Match) -> int:
        """Generate single bot ID for player"""
        # Use hash to ensure consistent bot ID per player per match
        bot_id = abs(hash(f"{player.id}_{match.id}")) % 10000
        return bot_id
    
    def _get_match_status_message(self, match: Match) -> str:
        """Get human-readable match status"""
        player_count = len(match.players)
        
        if match.state == MatchState.WAITING_FOR_PLAYERS:
            needed = self.min_players - player_count
            if needed > 0:
                return f"⏳ Waiting for {needed} more player(s) to start ({player_count}/{self.min_players})"
            else:
                return f"🎯 Match starting with {player_count} players!"
        elif match.state == MatchState.ACTIVE:
            return f"⚔️ Joined active PvP battle ({player_count}/{self.max_players} players)"
        else:
            return f"🔄 Match in transition ({match.state.value})"
    
    def remove_player(self, player_id: str) -> bool:
        """Remove player from match"""
        match_id = self.player_to_match.get(player_id)
        if not match_id or match_id not in self.active_matches:
            return False
        
        match = self.active_matches[match_id]
        
        # Remove player from match
        match.players = [p for p in match.players if p.id != player_id]
        del self.player_to_match[player_id]
        
        logger.info(f"👋 Player {player_id} left match {match_id} ({len(match.players)} remaining)")
        
        # Handle match cleanup
        if len(match.players) == 0:
            # Empty match - remove it
            del self.active_matches[match_id]
            logger.info(f"🗑️ Removed empty match {match_id}")
        elif len(match.players) < self.min_players and match.state == MatchState.ACTIVE:
            # Not enough players for active match - back to waiting
            match.state = MatchState.WAITING_FOR_PLAYERS
            match.started_time = None
            logger.info(f"⏸️ Match {match_id} paused - waiting for more players ({len(match.players)}/{self.min_players})")
        
        return True
    
    def get_match_info(self, player_id: str) -> Dict:
        """Get detailed match information for player"""
        match_id = self.player_to_match.get(player_id)
        if not match_id:
            return {'error': 'Player not in any match'}
        
        match = self.active_matches.get(match_id)
        if not match:
            return {'error': 'Match not found'}
        
        return {
            'match_id': match.id,
            'state': match.state.value,
            'players': [
                {
                    'id': p.id,
                    'name': p.bot_name,
                    'bot_id': p.bot_id,
                    'connected_time': time.time() - p.connection_time
                }
                for p in match.players
            ],
            'player_count': len(match.players),
            'min_players': match.min_players,
            'max_players': match.max_players,
            'created_time': match.created_time,
            'started_time': match.started_time,
            'is_active': match.state == MatchState.ACTIVE
        }
    
    def get_all_matches(self) -> List[Dict]:
        """Get list of all active matches (for admin/debug)"""
        matches = []
        for match in self.active_matches.values():
            matches.append({
                'id': match.id,
                'state': match.state.value,
                'players': len(match.players),
                'max_players': match.max_players,
                'created_time': match.created_time,
                'started_time': match.started_time,
                'player_names': [p.bot_name for p in match.players]
            })
        return matches
    
    def get_statistics(self) -> Dict:
        """Get matchmaker statistics"""
        active_players = sum(len(match.players) for match in self.active_matches.values())
        waiting_matches = len([m for m in self.active_matches.values() 
                              if m.state == MatchState.WAITING_FOR_PLAYERS])
        active_matches = len([m for m in self.active_matches.values() 
                             if m.state == MatchState.ACTIVE])
        
        return {
            'total_matches_created': self.total_matches_created,
            'total_players_served': self.total_players_served,
            'current_active_matches': active_matches,
            'current_waiting_matches': waiting_matches,
            'current_active_players': active_players,
            'avg_players_per_match': active_players / max(len(self.active_matches), 1)
        }
    
    def force_start_match(self, match_id: str) -> bool:
        """Force start a match (admin function)"""
        match = self.active_matches.get(match_id)
        if not match or match.state != MatchState.WAITING_FOR_PLAYERS:
            return False
        
        if len(match.players) >= 1:  # Allow force start with even 1 player
            self._start_match(match)
            logger.info(f"🔧 Admin force-started match {match_id}")
            return True
        return False