#  PPO training with tactical rewards
import torch
import torch.nn as nn
import torch.optim as optim
import numpy as np
import logging

logger = logging.getLogger(__name__)

class PPOTrainer:
    """ PPO trainer with tactical combat rewards"""
    
    def __init__(self, network, lr=3e-4, clip_epsilon=0.2, value_coef=0.5, entropy_coef=0.01):
        self.network = network
        self.optimizer = optim.Adam(network.parameters(), lr=lr)
        
        self.clip_epsilon = clip_epsilon
        self.value_coef = value_coef
        self.entropy_coef = entropy_coef
        
        self.update_count = 0
        
        #  training metrics
        self.combat_metrics = {
            'wall_avoidance_score': 0.0,
            'aiming_accuracy': 0.0,
            'tactical_movement': 0.0,
            'firing_efficiency': 0.0
        }
        
    def update(self, batch):
        """ update with tactical combat analysis"""
        obs = batch['obs']
        actions = batch['actions']
        old_log_probs = batch['log_probs'] 
        rewards = batch['rewards']
        values = batch['values']
        dones = batch['dones']
        
        #  advantage calculation with tactical bonuses
        advantages = self._calculate_advantages(rewards, values, dones, obs)
        returns = advantages + values.squeeze()
        
        # Normalize advantages
        advantages = (advantages - advantages.mean()) / (advantages.std() + 1e-8)
        
        # Forward pass
        movement_dist, aim_dist, fire_dist, new_values = self.network(obs)
        
        # Calculate new log probs
        new_log_probs = self._calculate_log_probs(
            movement_dist, aim_dist, fire_dist, actions, obs
        )
        
        #  PPO loss with tactical components
        ratio = torch.exp(new_log_probs - old_log_probs)
        surr1 = ratio * advantages
        surr2 = torch.clamp(ratio, 1.0 - self.clip_epsilon, 1.0 + self.clip_epsilon) * advantages
        policy_loss = -torch.min(surr1, surr2).mean()
        
        # Value loss
        value_loss = nn.MSELoss()(new_values.squeeze(), returns)
        
        #  entropy loss with tactical exploration
        entropy = self._calculate_entropy(movement_dist, aim_dist, fire_dist, obs)
        entropy_loss = -entropy.mean()
        
        # Tactical bonus losses
        tactical_loss = self._calculate_tactical_loss(obs, movement_dist, aim_dist, fire_dist)
        
        # Total  loss
        loss = (policy_loss + 
                self.value_coef * value_loss + 
                self.entropy_coef * entropy_loss +
                0.1 * tactical_loss)  # Tactical component weight
        
        # Update
        self.optimizer.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(self.network.parameters(), 0.5)
        self.optimizer.step()
        
        self.update_count += 1
        
        # Update combat metrics
        self._update_combat_metrics(obs, movement_dist, aim_dist, fire_dist)
        
        return {
            'policy_loss': policy_loss.item(),
            'value_loss': value_loss.item(),
            'entropy_loss': entropy_loss.item(),
            'tactical_loss': tactical_loss.item(),
            'total_loss': loss.item(),
            'wall_avoidance': self.combat_metrics['wall_avoidance_score'],
            'aiming_accuracy': self.combat_metrics['aiming_accuracy'],
            'tactical_movement': self.combat_metrics['tactical_movement']
        }
    
    def _calculate_advantages(self, rewards, values, dones, obs, gamma=0.99, gae_lambda=0.95):
        """ GAE with tactical situation awareness"""
        advantages = torch.zeros_like(rewards)
        gae = 0
        
        for i in reversed(range(len(rewards))):
            if i == len(rewards) - 1:
                next_value = 0
            else:
                next_value = values[i + 1] if not dones[i] else 0
            
            # Base temporal difference error
            delta = rewards[i] + gamma * next_value - values[i]
            
            # Tactical situation bonus/penalty
            if i < len(obs):
                tactical_modifier = self._get_tactical_modifier(obs[i])
                delta = delta * tactical_modifier
            
            gae = delta + gamma * gae_lambda * gae * (1 - dones[i])
            advantages[i] = gae
        
        return advantages
    
    def _get_tactical_modifier(self, observation):
        """Calculate tactical situation modifier for advantage"""
        # Extract tactical features from observation
        has_los = observation[9].item()  # Line of sight
        wall_distances = observation[15:19]  # Wall distances
        bullet_threat = observation[33].item()  # Bullet threat
        good_shot = observation[34].item()  # Good shot opportunity
        
        modifier = 1.0
        
        # Bonus for good tactical positions
        if has_los > 0.5 and good_shot > 0.5:
            modifier *= 1.1  # Good shooting position
        
        # Penalty for poor wall management
        min_wall_dist = torch.min(wall_distances).item()
        if min_wall_dist < 0.1:  # Too close to wall
            modifier *= 0.9
        
        # Penalty for high bullet threat
        if bullet_threat > 0.5:
            modifier *= 0.95
        
        return modifier
    
    def _calculate_log_probs(self, movement_dist, aim_dist, fire_dist, actions, obs):
        """ log probability calculation with tactical awareness"""
        # Extract actions (this would need proper action handling in real implementation)
        # For now, using simplified approach
        
        batch_size = obs.shape[0]
        log_probs = torch.zeros(batch_size)
        
        # Movement log prob with wall avoidance bonus
        movement_samples = movement_dist.sample()
        movement_log_prob = movement_dist.log_prob(movement_samples).sum(dim=-1)
        
        # Aim log prob with target tracking bonus
        aim_samples = aim_dist.sample()
        aim_log_prob = aim_dist.log_prob(aim_samples).squeeze(-1)
        
        # Fire log prob with tactical firing bonus
        fire_samples = fire_dist.sample()
        fire_log_prob = fire_dist.log_prob(fire_samples)
        
        # Combine with tactical bonuses
        for i in range(batch_size):
            tactical_bonus = self._get_action_tactical_bonus(obs[i], movement_samples[i], 
                                                           aim_samples[i], fire_samples[i])
            log_probs[i] = movement_log_prob[i] + aim_log_prob[i] + fire_log_prob[i] + tactical_bonus
        
        return log_probs
    
    def _get_action_tactical_bonus(self, obs, movement, aim, fire):
        """Calculate tactical bonus for action quality"""
        bonus = 0.0
        
        # Wall avoidance movement bonus
        wall_distances = obs[15:19]
        min_wall_dist = torch.min(wall_distances).item()
        
        if min_wall_dist < 0.15:  # Near wall
            # Check if movement is away from wall
            wall_avoid_dirs = obs[23:27]
            movement_alignment = torch.dot(movement, wall_avoid_dirs[:2]).item()
            if movement_alignment > 0:  # Moving away from wall
                bonus += 0.1
        
        # Smart aiming bonus
        has_los = obs[9].item()
        enemy_angle_x = obs[27].item()  # Enemy direction X
        enemy_angle_y = obs[28].item()  # Enemy direction Y
        
        if has_los > 0.5:
            # Calculate aim alignment with enemy
            enemy_angle = torch.atan2(torch.tensor(enemy_angle_y), torch.tensor(enemy_angle_x))
            aim_error = torch.abs(aim - enemy_angle).item()
            if aim_error < 0.2:  # Good aim
                bonus += 0.05
        
        # Smart firing bonus
        good_shot = obs[34].item()
        if fire > 0.5 and good_shot > 0.5:  # Firing when good shot available
            bonus += 0.05
        elif fire > 0.5 and good_shot < 0.5:  # Firing when bad shot
            bonus -= 0.1
        
        return bonus
    
    def _calculate_entropy(self, movement_dist, aim_dist, fire_dist, obs):
        """ entropy calculation with tactical exploration"""
        # Base entropy
        movement_entropy = movement_dist.entropy().sum(dim=-1)
        aim_entropy = aim_dist.entropy().squeeze(-1)
        fire_entropy = fire_dist.entropy()
        
        total_entropy = movement_entropy + aim_entropy + fire_entropy
        
        # Tactical exploration bonus
        batch_size = obs.shape[0]
        exploration_bonus = torch.zeros(batch_size)
        
        for i in range(batch_size):
            # Encourage exploration in safe situations
            bullet_threat = obs[i, 33].item()
            wall_safety = torch.min(obs[i, 15:19]).item()
            
            if bullet_threat < 0.3 and wall_safety > 0.2:  # Safe to explore
                exploration_bonus[i] = 0.1
        
        return total_entropy + exploration_bonus
    
    def _calculate_tactical_loss(self, obs, movement_dist, aim_dist, fire_dist):
        """Calculate tactical behavior loss to encourage smart play"""
        batch_size = obs.shape[0]
        tactical_loss = 0.0
        
        for i in range(batch_size):
            # Wall safety loss
            wall_distances = obs[i, 15:19]
            min_wall_dist = torch.min(wall_distances)
            if min_wall_dist < 0.1:  # Too close to wall
                tactical_loss += (0.1 - min_wall_dist) ** 2
            
            # Firing efficiency loss
            has_los = obs[i, 9]
            good_shot = obs[i, 34]
            fire_prob = fire_dist.probs[i, 1]  # Probability of firing
            
            if has_los < 0.5 and fire_prob > 0.5:  # Likely to fire without LOS
                tactical_loss += fire_prob * 0.5
            
            if good_shot > 0.5 and fire_prob < 0.3:  # Not taking good shots
                tactical_loss += (0.3 - fire_prob) * 0.3
        
        return tactical_loss / batch_size
    
    def _update_combat_metrics(self, obs, movement_dist, aim_dist, fire_dist):
        """Update combat performance metrics"""
        batch_size = obs.shape[0]
        
        # Wall avoidance score
        wall_scores = []
        for i in range(batch_size):
            min_wall_dist = torch.min(obs[i, 15:19]).item()
            wall_scores.append(min(min_wall_dist * 10, 1.0))  # Normalize to 0-1
        
        # Aiming accuracy (when LOS available)
        aim_scores = []
        for i in range(batch_size):
            has_los = obs[i, 9].item()
            if has_los > 0.5:
                good_shot = obs[i, 34].item()
                aim_scores.append(good_shot)
        
        # Tactical movement (anti-camping)
        movement_scores = []
        for i in range(batch_size):
            movement_magnitude = torch.norm(movement_dist.mean[i]).item()
            movement_scores.append(min(movement_magnitude, 1.0))
        
        # Firing efficiency
        firing_scores = []
        for i in range(batch_size):
            has_los = obs[i, 9].item()
            good_shot = obs[i, 34].item()
            fire_prob = fire_dist.probs[i, 1].item()
            
            if has_los > 0.5 and good_shot > 0.5:
                firing_scores.append(fire_prob)  # Should fire when good shot
            elif has_los < 0.5:
                firing_scores.append(1.0 - fire_prob)  # Should not fire without LOS
            else:
                firing_scores.append(0.5)  # Neutral
        
        # Update running averages
        alpha = 0.1  # Learning rate for metrics
        self.combat_metrics['wall_avoidance_score'] = (
            (1 - alpha) * self.combat_metrics['wall_avoidance_score'] + 
            alpha * np.mean(wall_scores)
        )
        
        if aim_scores:
            self.combat_metrics['aiming_accuracy'] = (
                (1 - alpha) * self.combat_metrics['aiming_accuracy'] + 
                alpha * np.mean(aim_scores)
            )
        
        self.combat_metrics['tactical_movement'] = (
            (1 - alpha) * self.combat_metrics['tactical_movement'] + 
            alpha * np.mean(movement_scores)
        )
        
        self.combat_metrics['firing_efficiency'] = (
            (1 - alpha) * self.combat_metrics['firing_efficiency'] + 
            alpha * np.mean(firing_scores)
        )