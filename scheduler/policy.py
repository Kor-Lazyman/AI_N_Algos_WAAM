"""PPO policy with stored observation masks, including PPO minibatch updates."""
import torch
from stable_baselines3.common.policies import ActorCriticPolicy

class SchedulerPolicy(ActorCriticPolicy):
    def _distribution(self,obs,latent):
        logits=self.action_net(latent)
        mask=obs[..., -self.action_space.n:] > .5
        if not torch.all(mask.any(dim=-1)):
            raise ValueError('Every scheduler state needs at least one valid action')
        return self.action_dist.proba_distribution(action_logits=logits.masked_fill(~mask,-1e9))

    def forward(self,obs,deterministic=False):
        pi,vf=self.mlp_extractor(self.extract_features(obs))
        distribution=self._distribution(obs,pi)
        actions=distribution.get_actions(deterministic=deterministic)
        return actions.reshape((-1,*self.action_space.shape)),self.value_net(vf),distribution.log_prob(actions)

    def evaluate_actions(self,obs,actions):
        pi,vf=self.mlp_extractor(self.extract_features(obs))
        distribution=self._distribution(obs,pi)
        return self.value_net(vf),distribution.log_prob(actions),distribution.entropy()

    def get_distribution(self,obs):
        features=super().extract_features(obs,self.pi_features_extractor)
        return self._distribution(obs,self.mlp_extractor.forward_actor(features))

