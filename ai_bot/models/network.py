import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
from typing import Tuple, Dict

class PPONetwork(nn.Module):
    """PPO Actor-Critic network with movement bias"""
    
    def __init__(self, obs_dim: int = 32, action_dim: int = 4, hidden_dim: int = 128):
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
        
        # Actor networks (policy) - with movement bias
        self.movement_mean = nn.Linear(hidden_dim, 2)
        self.movement_std = nn.Parameter(torch.ones(2) * 0.7)  # Higher std for exploration
        
        # Aim: continuous angle
        self.aim_mean = nn.Linear(hidden_dim, 1)
        self.aim_std = nn.Parameter(torch.ones(1) * 0.5)
        
        # Fire: discrete binary action
        self.fire_logits = nn.Linear(hidden_dim, 2)
        
        # Critic network (value function)
        self.value_head = nn.Linear(hidden_dim, 1)
        
        # Initialize weights
        self._initialize_weights()
    
    def _initialize_weights(self):
        """Initialize network weights with movement bias"""
        for module in self.modules():
            if isinstance(module, nn.Linear):
                nn.init.orthogonal_(module.weight, gain=np.sqrt(2))
                nn.init.constant_(module.bias, 0.0)
        
        # Initialize movement with slight bias toward action
        nn.init.orthogonal_(self.movement_mean.weight, gain=0.5)
        nn.init.constant_(self.movement_mean.bias, 0.1)  # Slight movement bias
        
        # Other outputs
        nn.init.orthogonal_(self.aim_mean.weight, gain=0.1)
        nn.init.orthogonal_(self.fire_logits.weight, gain=0.1)
        nn.init.orthogonal_(self.value_head.weight, gain=1.0)
    
    def forward(self, observations: torch.Tensor):
        """Forward pass"""
        features = self.feature_extractor(observations)
        
        # Movement distribution (biased toward action)
        movement_mean = torch.tanh(self.movement_mean(features))
        movement_std = F.softplus(self.movement_std.expand_as(movement_mean)) + 0.1
        movement_dist = torch.distributions.Normal(movement_mean, movement_std)
        
        # Aim distribution
        aim_mean = self.aim_mean(features)
        aim_std = F.softplus(self.aim_std.expand_as(aim_mean)) + 0.05
        aim_dist = torch.distributions.Normal(aim_mean, aim_std)
        
        # Fire distribution
        fire_logits = self.fire_logits(features)
        fire_dist = torch.distributions.Categorical(logits=fire_logits)
        
        # Value estimation
        value = self.value_head(features)
        
        return movement_dist, aim_dist, fire_dist, value
    
    def get_action(self, observations: torch.Tensor, deterministic: bool = False):
        """Sample actions with movement encouragement"""
        movement_dist, aim_dist, fire_dist, value = self.forward(observations)
        
        if deterministic:
            movement_action = movement_dist.mean
            aim_action = aim_dist.mean
            fire_action = fire_dist.probs.argmax(dim=-1)
        else:
            movement_action = movement_dist.sample()
            aim_action = aim_dist.sample()
            fire_action = fire_dist.sample()
            
            # Encourage movement: if sampled movement is too small, boost it
            movement_magnitude = torch.norm(movement_action, dim=1, keepdim=True)
            boost_mask = movement_magnitude < 0.3
            if boost_mask.any():
                # Add random exploration to small movements
                noise = torch.randn_like(movement_action) * 0.3
                movement_action = torch.where(
                    boost_mask.expand_as(movement_action),
                    torch.tanh(movement_action + noise),
                    movement_action
                )
        
        # Wrap aim angle to [0, 2π]
        aim_action = torch.fmod(aim_action + 2 * np.pi, 2 * np.pi)
        
        # Calculate log probabilities
        movement_log_prob = movement_dist.log_prob(movement_action).sum(dim=-1)
        aim_log_prob = aim_dist.log_prob(aim_action).squeeze(-1)
        fire_log_prob = fire_dist.log_prob(fire_action)
        
        total_log_prob = movement_log_prob + aim_log_prob + fire_log_prob
        
        return movement_action, aim_action, fire_action, total_log_prob

class ObservationProcessor:
    """Process game observations into neural network input"""
    
    def __init__(self):
        self.obs_dim = 32
    
    def process(self, obs_dict):
        """Convert observation dict to tensor"""
        obs = np.zeros(self.obs_dim, dtype=np.float32)
        
        # Self state (normalized)
        arena_width = obs_dict.get('arena_width', 800)
        arena_height = obs_dict.get('arena_height', 600)
        
        self_pos = obs_dict.get('self_pos', {'x': 0, 'y': 0})
        obs[0] = self_pos['x'] / arena_width
        obs[1] = self_pos['y'] / arena_height
        obs[2] = obs_dict.get('self_hp', 100) / 100.0
        
        # Enemy state
        enemy_pos = obs_dict.get('enemy_pos', {'x': 0, 'y': 0})
        obs[3] = enemy_pos['x'] / arena_width
        obs[4] = enemy_pos['y'] / arena_height
        obs[5] = obs_dict.get('enemy_hp', 0) / 100.0
        
        # Distance and angle to enemy (encourages movement toward enemy)
        dx = enemy_pos['x'] - self_pos['x']
        dy = enemy_pos['y'] - self_pos['y']
        distance = np.sqrt(dx*dx + dy*dy)
        angle = np.arctan2(dy, dx)
        
        obs[6] = distance / 1000.0
        obs[7] = angle / np.pi
        
        # Bullet info
        bullets = obs_dict.get('bullets', [])
        obs[8] = min(len(bullets), 10) / 10.0
        
        # Line of sight
        obs[9] = float(obs_dict.get('has_line_of_sight', False))
        
        # Arena bounds
        obs[10] = arena_width / 1000.0
        obs[11] = arena_height / 1000.0
        
        # Add movement urgency features
        obs[12] = 1.0 if distance < 200 else 0.0  # Close to enemy
        obs[13] = 1.0 if len(bullets) > 0 else 0.0  # Bullets nearby
        
        return torch.FloatTensor(obs).unsqueeze(0)