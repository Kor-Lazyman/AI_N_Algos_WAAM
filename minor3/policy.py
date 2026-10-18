"""PPO discrete avoidance policy; masks apply during inference and updates."""
import torch
from stable_baselines3.common.policies import ActorCriticPolicy

class AvoidancePolicy(ActorCriticPolicy):
    def _distribution(self,obs,latent):
        mask=obs[...,-self.action_space.n:]>.5
        if not torch.all(mask.any(dim=-1)):raise ValueError('Empty action mask')
        return self.action_dist.proba_distribution(action_logits=self.action_net(latent).masked_fill(~mask,-1e9))
    def forward(self,obs,deterministic=False):
        pi,vf=self.mlp_extractor(self.extract_features(obs));d=self._distribution(obs,pi)
        a=d.get_actions(deterministic=deterministic)
        return a.reshape((-1,*self.action_space.shape)),self.value_net(vf),d.log_prob(a)
    def evaluate_actions(self,obs,actions):
        pi,vf=self.mlp_extractor(self.extract_features(obs));d=self._distribution(obs,pi)
        return self.value_net(vf),d.log_prob(actions),d.entropy()
    def get_distribution(self,obs):
        return self._distribution(obs,self.mlp_extractor.forward_actor(super().extract_features(obs,self.pi_features_extractor)))
