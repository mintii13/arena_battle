import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
import math
from typing import Tuple, Dict

class PPONetwork(nn.Module):
    """PPO Actor-Critic network with enhanced wall avoidance and smart aiming"""
    
    def __init__(self, obs_dim: int = 48, action_dim: int = 4, hidden_dim: int = 128):  # Increased obs_dim
        super(PPONetwork, self).__init__()
        
        self.obs_dim = obs_dim
        self.action_dim = action_dim
        self.hidden_dim = hidden_dim
        
        # Shared feature extractor
        self.feature_extractor = nn.Sequential(
            nn.Linear(obs_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU()
        )
        
        # Actor networks (policy) - with wall avoidance bias
        self.movement_mean = nn.Linear(hidden_dim, 2)
        self.movement_std = nn.Parameter(torch.ones(2) * 0.7)  # Higher std for exploration
        
        # Aim: continuous angle with enemy targeting bias
        self.aim_mean = nn.Linear(hidden_dim, 1)
        self.aim_std = nn.Parameter(torch.ones(1) * 0.3)  # Reduced for more precise aiming
        
        # Fire: discrete binary action with smart firing
        self.fire_logits = nn.Linear(hidden_dim, 2)
        
        # Critic network (value function)
        self.value_head = nn.Linear(hidden_dim, 1)
        
        # Initialize weights
        self._initialize_weights()
    
    def _initialize_weights(self):
        """Initialize network weights with smart combat bias"""
        for module in self.modules():
            if isinstance(module, nn.Linear):
                nn.init.orthogonal_(module.weight, gain=np.sqrt(2))
                nn.init.constant_(module.bias, 0.0)
        
        # Initialize movement with wall avoidance bias
        nn.init.orthogonal_(self.movement_mean.weight, gain=0.5)
        nn.init.constant_(self.movement_mean.bias, 0.0)
        
        # Initialize aiming with precision bias
        nn.init.orthogonal_(self.aim_mean.weight, gain=0.3)
        
        # Initialize firing with conservative bias (don't waste ammo) - FIXED
        nn.init.orthogonal_(self.fire_logits.weight, gain=0.1)
        # Fix: Set bias values individually instead of using tensor
        with torch.no_grad():
            self.fire_logits.bias[0] = -0.5  # Bias toward not firing
            self.fire_logits.bias[1] = 0.0   # Neutral for firing
        
        nn.init.orthogonal_(self.value_head.weight, gain=1.0)
    
    def forward(self, observations: torch.Tensor):
        """Forward pass with enhanced decision making"""
        features = self.feature_extractor(observations)
        
        # Movement distribution (wall-aware)
        movement_mean = torch.tanh(self.movement_mean(features))
        movement_std = F.softplus(self.movement_std.expand_as(movement_mean)) + 0.1
        movement_dist = torch.distributions.Normal(movement_mean, movement_std)
        
        # Aim distribution (enemy-targeted)
        aim_mean = self.aim_mean(features)
        aim_std = F.softplus(self.aim_std.expand_as(aim_mean)) + 0.05
        aim_dist = torch.distributions.Normal(aim_mean, aim_std)
        
        # Fire distribution (line-of-sight aware)
        fire_logits = self.fire_logits(features)
        fire_dist = torch.distributions.Categorical(logits=fire_logits)
        
        # Value estimation
        value = self.value_head(features)
        
        return movement_dist, aim_dist, fire_dist, value
    
    def get_action(self, observations: torch.Tensor, deterministic: bool = False):
        """Sample actions with wall avoidance and smart aiming"""
        movement_dist, aim_dist, fire_dist, value = self.forward(observations)
        
        if deterministic:
            movement_action = movement_dist.mean
            aim_action = aim_dist.mean
            fire_action = fire_dist.probs.argmax(dim=-1)
        else:
            movement_action = movement_dist.sample()
            aim_action = aim_dist.sample()
            fire_action = fire_dist.sample()
            
            # Wall avoidance: if near wall, boost movement away from it
            # This uses the wall avoidance info embedded in observations
            batch_size = observations.shape[0]
            for i in range(batch_size):
                obs = observations[i]
                
                # Extract wall avoidance signals (indices 15-22 in enhanced observation)
                if obs.shape[0] >= 23:  # Safety check for observation size
                    wall_distances = obs[15:19]  # [left, right, top, bottom] wall distances
                    
                    # If too close to any wall, adjust movement
                    min_safe_distance = 0.15  # 15% of arena size
                    
                    wall_avoid_x = 0.0
                    wall_avoid_y = 0.0
                    
                    # Left wall
                    if wall_distances[0] < min_safe_distance:
                        wall_avoid_x += 0.5  # Move right
                    
                    # Right wall  
                    if wall_distances[1] < min_safe_distance:
                        wall_avoid_x -= 0.5  # Move left
                    
                    # Top wall
                    if wall_distances[2] < min_safe_distance:
                        wall_avoid_y += 0.5  # Move down
                    
                    # Bottom wall
                    if wall_distances[3] < min_safe_distance:
                        wall_avoid_y -= 0.5  # Move up
                    
                    # Apply wall avoidance
                    if abs(wall_avoid_x) > 0 or abs(wall_avoid_y) > 0:
                        movement_action[i, 0] = torch.clamp(
                            movement_action[i, 0] + wall_avoid_x, -1.0, 1.0
                        )
                        movement_action[i, 1] = torch.clamp(
                            movement_action[i, 1] + wall_avoid_y, -1.0, 1.0
                        )
            
            # Smart aiming: bias toward enemy if visible
            # Extract enemy targeting info from observation
            for i in range(batch_size):
                obs = observations[i]
                if obs.shape[0] >= 10:  # Safety check
                    has_line_of_sight = obs[9]  # Index 9: line of sight
                    if obs.shape[0] >= 8:
                        enemy_angle = obs[7]  # Index 7: angle to enemy
                        
                        if has_line_of_sight > 0.5:  # If we can see enemy
                            # Bias aim toward enemy
                            target_angle = enemy_angle * np.pi  # Convert back to radians
                            current_aim = aim_action[i, 0].item()
                            
                            # Gradually adjust aim toward enemy
                            angle_diff = target_angle - current_aim
                            
                            # Handle angle wrapping
                            if angle_diff > np.pi:
                                angle_diff -= 2 * np.pi
                            elif angle_diff < -np.pi:
                                angle_diff += 2 * np.pi
                            
                            # Apply 50% bias toward enemy
                            aim_action[i, 0] = current_aim + angle_diff * 0.5
        
        # Wrap aim angle to [0, 2π]
        aim_action = torch.fmod(aim_action + 2 * np.pi, 2 * np.pi)
        
        # Calculate log probabilities
        movement_log_prob = movement_dist.log_prob(movement_action).sum(dim=-1)
        aim_log_prob = aim_dist.log_prob(aim_action).squeeze(-1)
        fire_log_prob = fire_dist.log_prob(fire_action)
        
        total_log_prob = movement_log_prob + aim_log_prob + fire_log_prob
        
        return movement_action, aim_action, fire_action, total_log_prob

class ObservationProcessor:
    """Enhanced observation processor with wall avoidance and smart targeting"""
    
    def __init__(self):
        self.obs_dim = 48  # Increased for additional features
    
    def process(self, obs_dict):
        """Convert observation dict to enhanced tensor with wall avoidance info"""
        obs = np.zeros(self.obs_dim, dtype=np.float32)
        
        # Arena dimensions
        arena_width = obs_dict.get('arena_width', 800)
        arena_height = obs_dict.get('arena_height', 600)
        
        # Self state (normalized)
        self_pos = obs_dict.get('self_pos', {'x': 0, 'y': 0})
        obs[0] = self_pos['x'] / arena_width
        obs[1] = self_pos['y'] / arena_height
        obs[2] = obs_dict.get('self_hp', 100) / 100.0
        
        # Enemy state
        enemy_pos = obs_dict.get('enemy_pos', {'x': 0, 'y': 0})
        obs[3] = enemy_pos['x'] / arena_width
        obs[4] = enemy_pos['y'] / arena_height
        obs[5] = obs_dict.get('enemy_hp', 0) / 100.0
        
        # Distance and angle to enemy
        dx = enemy_pos['x'] - self_pos['x']
        dy = enemy_pos['y'] - self_pos['y']
        distance = np.sqrt(dx*dx + dy*dy)
        angle = np.arctan2(dy, dx)
        
        obs[6] = distance / 1000.0
        obs[7] = angle / np.pi  # Normalized to [-1, 1]
        
        # Bullet info
        bullets = obs_dict.get('bullets', [])
        obs[8] = min(len(bullets), 10) / 10.0
        
        # Line of sight (IMPORTANT for smart firing)
        obs[9] = float(obs_dict.get('has_line_of_sight', False))
        
        # Arena bounds
        obs[10] = arena_width / 1000.0
        obs[11] = arena_height / 1000.0
        
        # Combat state features
        obs[12] = 1.0 if distance < 200 else 0.0  # Close to enemy
        obs[13] = 1.0 if len(bullets) > 0 else 0.0  # Bullets nearby
        obs[14] = 1.0 if obs_dict.get('has_line_of_sight', False) and distance < 300 else 0.0  # Good shot opportunity
        
        # === NEW: WALL AVOIDANCE FEATURES ===
        
        # Calculate distances to arena boundaries
        left_dist = self_pos['x'] / arena_width  # Distance to left wall (0-1)
        right_dist = (arena_width - self_pos['x']) / arena_width  # Distance to right wall
        top_dist = self_pos['y'] / arena_height  # Distance to top wall
        bottom_dist = (arena_height - self_pos['y']) / arena_height  # Distance to bottom wall
        
        # Wall distances (normalized, 0 = at wall, 1 = far from wall)
        obs[15] = left_dist
        obs[16] = right_dist
        obs[17] = top_dist
        obs[18] = bottom_dist
        
        # Wall proximity warnings (1 if too close to wall)
        wall_warning_threshold = 0.1  # 10% of arena size
        obs[19] = 1.0 if left_dist < wall_warning_threshold else 0.0
        obs[20] = 1.0 if right_dist < wall_warning_threshold else 0.0
        obs[21] = 1.0 if top_dist < wall_warning_threshold else 0.0
        obs[22] = 1.0 if bottom_dist < wall_warning_threshold else 0.0
        
        # Wall avoidance directions (for movement bias)
        obs[23] = 1.0 if left_dist < 0.2 else 0.0    # Should move right
        obs[24] = -1.0 if right_dist < 0.2 else 0.0  # Should move left
        obs[25] = 1.0 if top_dist < 0.2 else 0.0     # Should move down
        obs[26] = -1.0 if bottom_dist < 0.2 else 0.0 # Should move up
        
        # === NEW: SMART AIMING FEATURES ===
        
        # Angle difference between current aim and enemy direction
        # (This would need current aim angle from game state, using enemy angle as proxy)
        obs[27] = np.cos(angle)  # X component of enemy direction
        obs[28] = np.sin(angle)  # Y component of enemy direction
        
        # Enemy movement prediction (simple)
        obs[29] = dx / arena_width   # Enemy relative X position
        obs[30] = dy / arena_height  # Enemy relative Y position
        
        # === NEW: TACTICAL FEATURES ===
        
        # Corner positions (good for defensive play)
        corners = [
            (50, 50), (arena_width-50, 50), 
            (50, arena_height-50), (arena_width-50, arena_height-50)
        ]
        
        min_corner_dist = float('inf')
        for corner_x, corner_y in corners:
            corner_dist = np.sqrt((self_pos['x'] - corner_x)**2 + (self_pos['y'] - corner_y)**2)
            min_corner_dist = min(min_corner_dist, corner_dist)
        
        obs[31] = min_corner_dist / 200.0  # Distance to nearest corner
        
        # Center control (good for aggressive play)
        center_x, center_y = arena_width / 2, arena_height / 2
        center_dist = np.sqrt((self_pos['x'] - center_x)**2 + (self_pos['y'] - center_y)**2)
        obs[32] = center_dist / 300.0  # Distance to center
        
        # === NEW: BULLET THREAT ANALYSIS ===
        
        # Analyze nearby bullets for threat level
        bullet_threat = 0.0
        for bullet in bullets:
            bullet_dx = bullet['x'] - self_pos['x']
            bullet_dy = bullet['y'] - self_pos['y']
            bullet_dist = np.sqrt(bullet_dx*bullet_dx + bullet_dy*bullet_dy)
            
            if bullet_dist < 100:  # Nearby bullet
                bullet_threat += (100 - bullet_dist) / 100.0
        
        obs[33] = min(bullet_threat, 1.0)  # Bullet threat level
        
        # === NEW: FIRING OPPORTUNITY ASSESSMENT ===
        
        # Good shot conditions
        good_shot = (
            obs_dict.get('has_line_of_sight', False) and  # Can see enemy
            distance < 400 and  # Enemy in range
            distance > 50   # Not too close (avoid friendly fire area)
        )
        obs[34] = 1.0 if good_shot else 0.0
        
        # Enemy visibility duration (would need tracking, using LOS as proxy)
        obs[35] = float(obs_dict.get('has_line_of_sight', False))
        
        # === REMAINING FEATURES (padding) ===
        
        # Fill remaining slots with useful derived features
        obs[36] = np.sin(2 * angle)  # Harmonic of enemy angle
        obs[37] = np.cos(2 * angle)  # Harmonic of enemy angle
        obs[38] = 1.0 if distance < 150 else 0.0  # Very close combat
        obs[39] = 1.0 if distance > 500 else 0.0  # Long range combat
        
        # Health ratio features
        enemy_hp = obs_dict.get('enemy_hp', 0)
        self_hp = obs_dict.get('self_hp', 100)
        health_advantage = (self_hp - enemy_hp) / 100.0
        obs[40] = health_advantage
        obs[41] = 1.0 if health_advantage > 0 else 0.0  # Winning
        obs[42] = 1.0 if health_advantage < -0.5 else 0.0  # Critical health disadvantage
        
        # Movement encouragement (anti-camping)
        obs[43] = 1.0  # Always encourage movement
        obs[44] = np.random.uniform(0, 1)  # Random exploration signal
        
        # Arena position category
        edge_threshold = 0.15
        is_near_edge = (left_dist < edge_threshold or right_dist < edge_threshold or 
                       top_dist < edge_threshold or bottom_dist < edge_threshold)
        obs[45] = 1.0 if is_near_edge else 0.0
        
        # Final tactical signals
        obs[46] = 1.0 if good_shot and health_advantage > 0 else 0.0  # Attack opportunity
        obs[47] = 1.0 if bullet_threat > 0.5 or health_advantage < -0.3 else 0.0  # Retreat signal
        
        return torch.FloatTensor(obs).unsqueeze(0)