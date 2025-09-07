# PPO training logic
import torch
import torch.nn as nn
import torch.optim as optim
import numpy as np
import logging

logger = logging.getLogger(__name__)

class PPOTrainer:
    """Simple PPO trainer"""
    
    def __init__(self, network, lr=3e-4, clip_epsilon=0.2, value_coef=0.5, entropy_coef=0.01):
        self.network = network
        self.optimizer = optim.Adam(network.parameters(), lr=lr)
        
        self.clip_epsilon = clip_epsilon
        self.value_coef = value_coef
        self.entropy_coef = entropy_coef
        
        self.update_count = 0
        
    def update(self, batch):
        """Update policy using PPO"""
        obs = batch['obs']
        actions = batch['actions']
        old_log_probs = batch['log_probs'] 
        rewards = batch['rewards']
        values = batch['values']
        dones = batch['dones']
        
        # Calculate advantages
        advantages = self._calculate_advantages(rewards, values, dones)
        returns = advantages + values.squeeze()
        
        # Normalize advantages
        advantages = (advantages - advantages.mean()) / (advantages.std() + 1e-8)
        
        # Forward pass
        movement, aim, fire_logits, new_values = self.network(obs)
        
        # Calculate new log probs (simplified)
        new_log_probs = self._calculate_log_probs(movement, aim, fire_logits, actions)
        
        # PPO loss
        ratio = torch.exp(new_log_probs - old_log_probs)
        surr1 = ratio * advantages
        surr2 = torch.clamp(ratio, 1.0 - self.clip_epsilon, 1.0 + self.clip_epsilon) * advantages
        policy_loss = -torch.min(surr1, surr2).mean()
        
        # Value loss
        value_loss = nn.MSELoss()(new_values.squeeze(), returns)
        
        # Entropy loss (for exploration)
        entropy = self._calculate_entropy(fire_logits)
        entropy_loss = -entropy.mean()
        
        # Total loss
        loss = policy_loss + self.value_coef * value_loss + self.entropy_coef * entropy_loss
        
        # Update
        self.optimizer.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(self.network.parameters(), 0.5)
        self.optimizer.step()
        
        self.update_count += 1
        
        return {
            'policy_loss': policy_loss.item(),
            'value_loss': value_loss.item(),
            'entropy_loss': entropy_loss.item(),
            'total_loss': loss.item()
        }
    
    def _calculate_advantages(self, rewards, values, dones, gamma=0.99, gae_lambda=0.95):
        """Calculate GAE advantages"""
        advantages = torch.zeros_like(rewards)
        gae = 0
        
        for i in reversed(range(len(rewards))):
            if i == len(rewards) - 1:
                next_value = 0
            else:
                next_value = values[i + 1] if not dones[i] else 0
            
            delta = rewards[i] + gamma * next_value - values[i]
            gae = delta + gamma * gae_lambda * gae * (1 - dones[i])
            advantages[i] = gae
        
        return advantages
    
    def _calculate_log_probs(self, movement, aim, fire_logits, actions):
        """Calculate log probabilities of actions (simplified)"""
        # This is a simplified version - in practice you'd need proper action handling
        movement_log_prob = -0.5 * torch.sum((movement - torch.zeros_like(movement))**2, dim=1)
        aim_log_prob = -0.5 * (aim.squeeze() - torch.zeros_like(aim.squeeze()))**2
        
        fire_dist = torch.distributions.Categorical(logits=fire_logits)
        fire_log_prob = fire_dist.log_prob(torch.zeros(fire_logits.shape[0], dtype=torch.long))
        
        return movement_log_prob + aim_log_prob + fire_log_prob
    
    def _calculate_entropy(self, fire_logits):
        """Calculate entropy for exploration"""
        fire_dist = torch.distributions.Categorical(logits=fire_logits)
        return fire_dist.entropy()