"""One path action generates one full layer, evaluated with the current avoider."""
import json
from pathlib import Path
import numpy as np
import gymnasium as gym
from source import ACTION_NVECS
from avoidance import resolve

def dump(path,value):
    def convert(x):
        if isinstance(x,np.ndarray):return x.tolist()
        if isinstance(x,np.generic):return x.item()
        if isinstance(x,Path):return str(x)
        raise TypeError(type(x).__name__)
    Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2,default=convert),encoding='utf-8')

class PathEnv(gym.Env):
    def __init__(self,pool,avoid_model=None):
        super().__init__();self.pool=pool;self.avoid_model=avoid_model;self.cycle=[]
        self.action_space=gym.spaces.MultiDiscrete(ACTION_NVECS)
        self.observation_space=gym.spaces.Box(-np.inf,np.inf,shape=pool[0][0].observe(pool[0][1]).shape,dtype=np.float32)
    def reset(self,*,seed=None,options=None):
        super().reset(seed=seed)
        if seed is not None:self.cycle=[]
        if not self.cycle:self.cycle=list(self.np_random.permutation(len(self.pool)))
        self.source,self.index=self.pool[int(self.cycle.pop())]
        return self.source.observe(self.index),{}
    def step(self,action):
        env=resolve(self.source,self.index,action,self.avoid_model)
        info=env.info();reward=-info['objective_time_s']/info['reference_s']
        return self.source.observe(self.index),float(reward),True,False,info

