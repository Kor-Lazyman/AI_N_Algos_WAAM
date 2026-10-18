"""Learn a waypoint and waiting strategy at the earliest predicted conflict."""
import numpy as np
import gymnasium as gym
from gymnasium import spaces
from motion import collision,positions,cut,insert_detour,span,metrics,deposition_preserved

class AvoidanceEnv(gym.Env):
    # 2 robots in conflict x (wait-in-place + 3 directions x 2 distances) x 2 waits.
    ACTIONS=[(member,direction,distance,holdmode) for member in range(2)
             for direction,distance in [(-1,0.),(0,200.),(0,500.),(1,200.),(1,500.),(2,200.),(2,500.)]
             for holdmode in range(2)]
    def __init__(self,pool=None,path_model=None,max_repairs=32):
        super().__init__();self.pool=pool or [];self.path_model=path_model;self.max_repairs=max_repairs
        self.action_space=spaces.Discrete(len(self.ACTIONS))
        self.observation_space=spaces.Box(-np.inf,np.inf,shape=(16+10*len(self.ACTIONS)+len(self.ACTIONS),),dtype=np.float32)
        self.cycle=[]

    def reset(self,*,seed=None,options=None):
        super().reset(seed=seed)
        if seed is not None:self.cycle=[]
        if options and 'source' in options:
            source,index,action=options['source'],options['index'],options['path_action']
        else:
            if not self.cycle:self.cycle=list(self.np_random.permutation(len(self.pool)))
            source,index=self.pool[int(self.cycle.pop())]
            action,_=self.path_model.predict(source.observe(index),deterministic=True)
        self.source,self.index,self.path_action=source,index,np.asarray(action,int)
        self.config=source.config;self.reference=source.reference(index)
        self.done=self.failed=False;self.steps=0;self.trace=[];self.failure_reason=None
        try:self.rows=source.generate(index,action)
        except ValueError as exc:
            self.rows=[[[0.,*p,'W']] for p in source.homes];self.failed=True;self.failure_reason=str(exc)
        self.original=[[list(p) for p in own] for own in self.rows]
        self.initial_span=span(self.rows);self.deadline=max(20*self.reference,10*self.initial_span,1.)
        self.hit=None if self.failed else collision(self.rows,self.config)
        return self._observe(),self.info()

    def _candidate(self,member,direction,distance,holdmode):
        r=self.hit['pair'][member];other=self.hit['pair'][1-member]
        if self.rows[r][-1][0]<=self.hit['time']+1e-6:return None
        # Move as close to the predicted event as these safe leads permit.
        for lead in (0.5,2.,6.,16.):
            pause=max(0.,self.hit['time']-lead)
            prefix,tail=cut(self.rows[r],pause)
            if len(tail)<2:continue
            start=np.asarray(prefix[-1][1:4]);base=np.asarray(self.config.robots[r].base_xyz_mm[:2])
            v=base-start[:2]
            if np.linalg.norm(v)<1e-5:v=start[:2]-np.mean(self.source.bases[:,:2],axis=0)
            v=v/max(np.linalg.norm(v),1e-9)
            if direction==1:v=np.array([-v[1],v[0]])
            elif direction==2:v=np.array([v[1],-v[0]])
            point=np.array([*(start[:2]+v*distance),start[2]])
            if np.linalg.norm(point[:2]-base)>self.config.robots[r].xy_reach_radius_mm:continue
            travel=distance/self.config.process.travel_speed_mm_s
            pairs=[(min(r,i),max(r,i)) for i in range(3) if i!=r]
            # A long wait guarantees only a timing candidate, never unchecked safety.
            if holdmode:
                holds=[max(.1,max(self.rows[i][-1][0] for i in range(3) if i!=r)-pause-travel)+.1]
            else:
                holds=[0.,1.,3.,8.,20.,45.]
            for hold in holds:
                if distance==0 and hold<1e-6:continue
                amended,resume,delay=insert_detour(self.rows[r],pause,point,hold,self.config.process.travel_speed_mm_s)
                rows=list(self.rows);rows[r]=amended
                # Verify the complete retreat, hold, return and the rest of the
                # interrupted motion. Other robots' routes remain unchanged.
                end=min(amended[-1][0],resume+(tail[1][0]-pause)+.1)
                if collision(rows,self.config,pause,end,pairs,quick=True):continue
                if collision(rows,self.config,pause,end,pairs):continue
                if span(rows)>=self.deadline:continue
                return dict(robot=r,rows=rows,pause=pause,pause_xyz=start.tolist(),waypoint=point.tolist(),
                    resume=resume,hold=hold,delay=delay,distance=distance,direction=direction,holdmode=holdmode,
                    predicted_time=self.hit['time'],pair=self.hit['pair'],mode=tail[0][4])
        return None

    def _observe(self):
        self.choices=[None]*len(self.ACTIONS);mask=np.zeros(len(self.ACTIONS),np.float32)
        hit=self.hit
        features=[span(self.rows)/self.reference,self.initial_span/self.reference,self.steps/self.max_repairs,
                  hit['time']/self.reference if hit else 0.]
        for r in range(3):
            p=positions(self.rows[r],np.array([hit['time'] if hit else span(self.rows)]))[0]
            features.extend([*list(p/2000.),float(hit is not None and r in hit['pair'])])
        for i,args in enumerate(self.ACTIONS):
            candidate=self._candidate(*args) if hit and not self.done and not self.failed else None
            self.choices[i]=candidate;mask[i]=float(candidate is not None)
            if candidate:
                c=candidate;features.extend([c['robot']/2,*list(np.asarray(c['waypoint'])/2000.),
                    c['distance']/1000,c['hold']/self.reference,c['delay']/self.reference,
                    (span(c['rows'])-span(self.rows))/self.reference,c['pause']/self.reference,float(c['mode']=='D')])
            else:features.extend([0.]*10)
        self.deadlocked=bool(hit and not mask.any())
        if not mask.any():mask[0]=1.
        self.mask=mask
        return np.asarray(features+mask.tolist(),np.float32)

    def step(self,action):
        if self.done:raise RuntimeError('Reset ended episode')
        action=int(action)
        if not self.mask[action]:raise ValueError('Unsafe action masked')
        old=span(self.rows);self.steps+=1
        if self.failed or self.deadlocked:
            self.failed=self.done=True;self.failure_reason=self.failure_reason or 'no_safe_detour'
        elif self.hit is None:self.done=True
        else:
            candidate=self.choices[action];self.rows=candidate['rows']
            self.trace.append({k:v for k,v in candidate.items() if k!='rows'})
            self.hit=collision(self.rows,self.config)
            self.done=self.hit is None
            if not self.done and self.steps>=self.max_repairs:
                self.done=self.failed=True;self.failure_reason='repair_limit'
        if self.done and not self.failed and not deposition_preserved(self.original,self.rows):
            raise AssertionError('Lost/reordered deposition while repairing schedule')
        objective=self.deadline if self.failed else span(self.rows)
        # gamma=1 telescopes exactly to negative final makespan (up to initial constant).
        reward=-(objective-old)/self.reference
        return self._observe(),float(reward),self.done,False,self.info()

    def info(self):
        return dict(shape=self.source.name,layer=self.index,repairs=len(self.trace),failed=self.failed,
            failure_reason=self.failure_reason,makespan_s=span(self.rows),objective_time_s=self.deadline if self.failed else span(self.rows),
            reference_s=self.reference,collision_free=self.hit is None and not self.failed,
            detour_distance_mm=sum(2*t['distance'] for t in self.trace),
            interrupted_D=sum(t['mode']=='D' for t in self.trace),path_action=self.path_action.tolist())

def resolve(source,index,action,model=None,max_repairs=32):
    env=AvoidanceEnv(max_repairs=max_repairs)
    obs,_=env.reset(options=dict(source=source,index=index,path_action=action));done=False
    while not done:
        if model is None:
            choices=[i for i,c in enumerate(env.choices) if c is not None]
            selected=min(choices,key=lambda i:(span(env.choices[i]['rows']),env.choices[i]['delay'])) if choices else 0
        else:selected=int(model.predict(obs,deterministic=True)[0])
        obs,_,done,_,_=env.step(selected)
    return env
