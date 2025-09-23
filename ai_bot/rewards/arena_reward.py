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
        """Calculate reward with DEBUG HP tracking"""
        reward = 0.0
        
        current_self_hp = observation_dict.get('self_hp', 100)
        current_enemy_hp = observation_dict.get('enemy_hp', 0)
        
        
        # Only process if we have previous state
        if self.last_self_hp is not None and self.last_enemy_hp is not None:
            
            # DETECT KILL EVENT (enemy respawn from low HP to full HP)
            if self.last_enemy_hp < 50 and current_enemy_hp == 100:
                reward += self.kill_reward
                print(f"🎯 KILL! Enemy respawned: {self.last_enemy_hp} → {current_enemy_hp}, Reward: +{self.kill_reward}")
                    
            # DETECT DEATH EVENT
            if self.last_self_hp > 0 and current_self_hp <= 0:
                reward += self.death_penalty
                print(f"💀 DEATH! Self HP: {self.last_self_hp} → {current_self_hp}, Reward: {self.death_penalty}")
        
        # Update state
        self.last_self_hp = current_self_hp
        self.last_enemy_hp = current_enemy_hp
        
        return reward