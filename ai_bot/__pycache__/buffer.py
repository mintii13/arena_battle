# Experience buffer
import numpy as np
from collections import deque
import random
import torch

class ExperienceBuffer:
    """Simple experience buffer for PPO"""
    
    def __init__(self, max_size=10000):
        self.max_size = max_size
        self.experiences = deque(maxlen=max_size)
    
    def add(self, obs, action, reward, next_obs, done, value, log_prob):
        """Add experience to buffer"""
        experience = {
            'obs': obs,
            'action': action, 
            'reward': reward,
            'next_obs': next_obs,
            'done': done,
            'value': value,
            'log_prob': log_prob
        }
        self.experiences.append(experience)
    
    def sample(self, batch_size):
        """Sample batch of experiences"""
        batch_size = min(batch_size, len(self.experiences))
        batch = random.sample(self.experiences, batch_size)
        
        # Convert to tensors
        obs_batch = torch.stack([exp['obs'].squeeze() for exp in batch])
        action_batch = [exp['action'] for exp in batch]
        reward_batch = torch.FloatTensor([exp['reward'] for exp in batch])
        done_batch = torch.BoolTensor([exp['done'] for exp in batch])
        value_batch = torch.stack([exp['value'] for exp in batch])
        log_prob_batch = torch.stack([exp['log_prob'] for exp in batch])
        
        return {
            'obs': obs_batch,
            'actions': action_batch,
            'rewards': reward_batch,
            'dones': done_batch,
            'values': value_batch,
            'log_probs': log_prob_batch
        }
    
    def clear(self):
        self.experiences.clear()
    
    def __len__(self):
        return len(self.experiences)