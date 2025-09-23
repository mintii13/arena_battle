class ArenaRewardCalculator:
    """Portable reward calculator for Arena Battle Game"""
    
    def __init__(self):
        self.reset_state()
        
        # Reward parameters (có thể config sau)
        self.kill_reward = 100.0
        self.death_penalty = -100.0
        
    def reset_state(self):
        """Reset state tracking for new episode"""
        self.last_self_hp = None
        self.last_enemy_hp = None
        
    def calculate_reward(self, observation_dict):
        """
        Calculate reward from observation changes
        observation_dict: dict từ game observation
        """
        reward = 0.0
        
        current_self_hp = observation_dict.get('self_hp', 100)
        current_enemy_hp = observation_dict.get('enemy_hp', 0)
        
        # Detect kill event (enemy HP: >0 → 0)
        if (self.last_enemy_hp is not None and 
            self.last_enemy_hp > 0 and 
            current_enemy_hp <= 0):
            reward += self.kill_reward
            
        # Detect death event (self HP: >0 → 0)  
        if (self.last_self_hp is not None and 
            self.last_self_hp > 0 and 
            current_self_hp <= 0):
            reward += self.death_penalty
            
        # Update state for next calculation
        self.last_self_hp = current_self_hp
        self.last_enemy_hp = current_enemy_hp
        
        return reward