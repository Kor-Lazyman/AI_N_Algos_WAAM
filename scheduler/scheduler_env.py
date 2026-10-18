"""Event-driven dispatch of frozen deposition tasks with collision-checked reservations.

Action 0 waits until the next robot finishes. Other actions select one of K
spatially spread pending tasks for each idle robot. Busy robots keep working.
Each task returns home, so a waiting robot remains at a checked safe position.
"""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import gymnasium as gym
from gymnasium import spaces
import bootstrap
from validator_adapter import load_config,trajectory_from_rows
from waam_validator.collision.simulator import run_collision_analysis
from waam_validator.collision.geometry2d import check_arm_envelope_xy_batch
from waam_validator.trajectory.validator import validate_trajectory_set
from waam_validator.errors import WaamValidatorError

def totals(rows,modes):
    events=[]
    for own in rows:
        for a,b in zip(own,own[1:]):
            if a[4] in modes: events.extend(((a[0],1),(b[0],-1)))
    result=[0.]*4;previous=0.;active=0
    for time,change in sorted(events):
        result[active]+=time-previous;active+=change;previous=time
    return result

def metrics(rows):
    span=max(own[-1][0] for own in rows)
    robots=[]
    for r,own in enumerate(rows):
        times={m:sum(b[0]-a[0] for a,b in zip(own,own[1:]) if a[4]==m) for m in 'TDW'}
        robots.append(dict(robot=r+1,**times,deposition_utilization=times['D']/max(span,1e-9),
                           utilization=(times['T']+times['D'])/max(span,1e-9)))
    dep=totals(rows,{'D'});busy=totals(rows,{'D','T'})
    return dict(makespan_s=span,robots=robots,deposition_2plus_s=dep[2]+dep[3],deposition_3_s=dep[3],
                simultaneous_2plus_s=busy[2]+busy[3],simultaneous_3_s=busy[3],
                mean_deposition_utilization=sum(r['deposition_utilization'] for r in robots)/3)

def pad(rows,end):
    result=[]
    for own in rows:
        x=[list(p) for p in own]
        if x[-1][0]<end: x.append([end,*x[-1][1:4],'W'])
        result.append(x)
    return result

class SchedulerEnv(gym.Env):
    def __init__(self,plan_paths,candidates=4):
        super().__init__()
        self.paths=[Path(p) for p in plan_paths]
        if not self.paths: raise ValueError('No layer plans')
        self.k=candidates; self.short_wait=1+3*candidates; self.n=self.short_wait+1
        self.action_space=spaces.Discrete(self.n)
        # Global 8 + per-robot 3*3 + per-candidate 10 + validity mask.
        self.observation_space=spaces.Box(-np.inf,np.inf,shape=(17+30*candidates+self.n,),dtype=np.float32)
        self.cache={}; self.cycle=[];self.active=None

    def _move(self,own,point,mode):
        point=np.asarray(point,dtype=np.float32).astype(float)
        dist=float(np.linalg.norm(point-np.asarray(own[-1][1:4])))
        if dist<=1e-6:return
        speed=self.config.process.deposition_speed_mm_s if mode=='D' else self.config.process.travel_speed_mm_s
        own[-1][4]=mode;own.append([own[-1][0]+dist/speed,*point,'W'])

    def reset(self,*,seed=None,options=None):
        super().reset(seed=seed)
        if seed is not None:self.cycle=[]
        if options and 'plan_index' in options:index=int(options['plan_index'])
        else:
            if not self.cycle:self.cycle=list(self.np_random.permutation(len(self.paths)))
            index=int(self.cycle.pop())
        self.path=self.paths[index];self.plan=json.loads(self.path.read_text(encoding='utf-8'))
        self.config=load_config(self.path.parent/'config.yaml')
        self.robots=sorted(self.config.robots,key=lambda r:r.id)
        self.homes=np.asarray([r.home_xyz_mm if r.home_xyz_mm is not None else r.base_xyz_mm for r in self.robots],dtype=np.float32).astype(float)
        self.ref=max(1.,self.plan['baseline_duration']); self.now=0.;self.steps=0
        self.rows=[[[0.,*home,'W']] for home in self.homes]
        self.ends=[0.]*3;self.done=False;self.failed=False;self.dispatched=[];self.trace=[]
        self.blocked_checks=0;self.waits=0;self.short_waits=0;self.reorders=0
        if self.path not in self.cache:
            tasks=[]
            for source in self.plan['tasks']:
                robot=source['robot'];own=[[0.,*self.homes[robot],'W']]
                for a,b in source['segments']:
                    self._move(own,(*a,self.plan['z']),'T');self._move(own,(*b,self.plan['z']),'D')
                self._move(own,self.homes[robot],'T')
                dep=sum(b[0]-a[0] for a,b in zip(own,own[1:]) if a[4]=='D')
                pts=np.asarray([p for segment in source['segments'] for p in segment])
                tasks.append(dict(source,rows=own,duration=own[-1][0],deposition=dep,
                                  center=pts.mean(axis=0),start=pts[0],end=pts[-1]))
            self.cache[self.path]=tasks
        self.tasks=self.cache[self.path]
        self.pending=[[t['id'] for t in self.tasks if t['robot']==r] for r in range(3)]
        self.total_dep=sum(t['deposition'] for t in self.tasks)
        self.assigned_dep=0.;self._safe_cache={}
        return self._observe(),self._info()

    def _window(self,robot):
        """Keep the committed future, rebased to now; past motion is already checked."""
        own=self.rows[robot]
        if self.ends[robot]<=self.now+1e-8:return [[0.,*self.homes[robot],'W']]
        i=int(np.searchsorted([p[0] for p in own],self.now,side='right')-1)
        a,b=own[i],own[i+1];frac=(self.now-a[0])/(b[0]-a[0])
        point=np.asarray(a[1:4])+(np.asarray(b[1:4])-a[1:4])*frac
        return [[0.,*point,a[4]],*[[p[0]-self.now,*p[1:]] for p in own[i+1:]]]

    def _safe(self,task):
        key=(task['id'],self.now,tuple(self.dispatched[-3:]),tuple(self.ends))
        if key in self._safe_cache:return self._safe_cache[key]
        rows=[self._window(r) for r in range(3)]
        rows[task['robot']]=task['rows']
        end=max(x[-1][0] for x in rows);rows=pad(rows,end)
        # Cheap rejection only. Acceptance always uses the official full sampler.
        knots=sorted({p[0] for own in rows for p in own})
        times=np.array(sorted(set(knots+[(a+b)/2 for a,b in zip(knots,knots[1:])])),float)
        xy=[np.column_stack([np.interp(times,[p[0] for p in own],[p[axis] for p in own]) for axis in (1,2)]) for own in rows]
        c=self.config.collision
        safe=True
        for a,b in ((0,1),(0,2),(1,2)):
            ra,rb=self.robots[a],self.robots[b]
            if c.check_tcp_radius and np.any(np.linalg.norm(xy[a]-xy[b],axis=1)<ra.tcp_radius_mm+rb.tcp_radius_mm-c.geometry_epsilon_mm):
                safe=False;break
            if c.check_arm_envelope and check_arm_envelope_xy_batch(np.asarray(ra.base_xyz_mm[:2]),xy[a],ra.arm_envelope_radius_mm,
                    np.asarray(rb.base_xyz_mm[:2]),xy[b],rb.arm_envelope_radius_mm,c.arm_clearance_mm,c.geometry_epsilon_mm,c.touching_is_collision).collision.any():
                safe=False;break
        if safe:
            try:
                tr=trajectory_from_rows(rows)
                safe=not validate_trajectory_set(tr,self.config).violations and not run_collision_analysis(tr,self.config).events
            except WaamValidatorError:safe=False
        if not safe:self.blocked_checks+=1
        self._safe_cache[key]=bool(safe)
        return bool(safe)

    def _observe(self):
        self.choices=[None]*self.n;mask=np.zeros(self.n,dtype=np.float32)
        mask[0]=float(any(end>self.now+1e-8 for end in self.ends))
        # A collision can occur only during departure. Waiting for the entire
        # other task would miss safe starts a few seconds later.
        remaining=[end-self.now for end in self.ends if end>self.now+1e-8]
        mask[self.short_wait]=float(bool(remaining) and min(remaining)>1. and
            any(self.ends[r]<=self.now+1e-8 and self.pending[r] for r in range(3)))
        features=[self.now/self.ref,self.assigned_dep/max(self.total_dep,1e-9),
            sum(map(len,self.pending))/max(len(self.tasks),1),self.total_dep/self.ref,
            self.plan['z']/2000.,self.plan['layer_iou'],self.steps/max(len(self.tasks),1),1.]
        for r in range(3):features.extend([max(0.,self.ends[r]-self.now)/self.ref,len(self.pending[r])/max(len(self.tasks),1),float(self.ends[r]>self.now+1e-8)])
        for r in range(3):
            ids=self.pending[r]
            positions=np.linspace(0,len(ids)-1,min(self.k,len(ids)),dtype=int).tolist() if ids else []
            for slot in range(self.k):
                action=1+r*self.k+slot
                if slot>=len(positions):features.extend([0.]*10);continue
                position=positions[slot];task=self.tasks[ids[position]];self.choices[action]=task['id']
                available=self.ends[r]<=self.now+1e-8
                valid=available and self._safe(task)
                mask[action]=float(valid)
                features.extend([*list(task['start']/2000),*list(task['end']/2000),*list(task['center']/2000),
                    task['duration']/self.ref,task['deposition']/self.ref,position/max(len(ids),1),float(available)])
        # A single terminal failure action avoids all-zero categorical masks.
        self.deadlocked=not bool(mask.any())
        if self.deadlocked:mask[0]=1.
        self.mask=mask
        obs=np.asarray(features+mask.tolist(),dtype=np.float32)
        assert obs.shape==self.observation_space.shape
        return obs

    def _info(self):
        return dict(plan=self.plan['id'],elapsed_s=self.now,dispatches=len(self.dispatched),
                    waits=self.waits,short_waits=self.short_waits,reordered_tasks=self.reorders,blocked_checks=self.blocked_checks,
                    remaining_tasks=sum(map(len,self.pending)),failed=self.failed)

    def step(self,action):
        if self.done:raise RuntimeError('Reset completed scheduler episode')
        action=int(action);self.steps+=1;previous=self.now;progress=0.
        if not 0<=action<self.n or not self.mask[action]:
            raise ValueError('Unsafe/unavailable action; use SchedulerPolicy masks')
        if action in (0,self.short_wait):
            if self.deadlocked:
                self.failed=self.done=True
                return self._observe(),-10.,True,False,dict(self._info(),failure_reason='no_safe_candidate')
            next_end=min(end for end in self.ends if end>self.now+1e-8)
            if action==self.short_wait:
                self.now+=min(next_end-self.now,max(1.,min(10.,.1*(next_end-self.now))))
                self.short_waits+=1
            else:self.now=next_end
            self.waits+=1
            self.trace.append(dict(action='WAIT_SHORT' if action==self.short_wait else 'WAIT',start=previous,end=self.now))
        else:
            task=self.tasks[self.choices[action]];r=task['robot']
            position=self.pending[r].index(task['id']);self.reorders+=int(position>0)
            own=self.rows[r]
            if own[-1][0]<self.now:own.append([self.now,*self.homes[r],'W'])
            own[-1][4]=task['rows'][0][4]
            own.extend([[p[0]+self.now,*p[1:]] for p in task['rows'][1:]])
            self.ends[r]=own[-1][0];self.pending[r].remove(task['id']);self.dispatched.append(task['id'])
            self.assigned_dep+=task['deposition'];progress=task['deposition']/max(self.total_dep,1e-9)
            self.trace.append(dict(action='DISPATCH',robot=r+1,task=task['id'],start=self.now,end=self.ends[r],reordered=position>0))
        if not any(self.pending):
            self.now=max(self.ends);self.rows=pad(self.rows,self.now);self.done=True
        reward=progress-(self.now-previous)/self.ref
        if self.done:
            self.result=metrics(self.rows)
            reward+=10*self.result['mean_deposition_utilization']*self.ref/max(self.now,1e-9)
        if self.steps>30*len(self.tasks)+100:
            self.done=self.failed=True;reward=-10.
        obs=self._observe();info=self._info()
        if self.done and not self.failed:info.update(self.result)
        return obs,float(reward),self.done,False,info

def plan_paths(folder):
    folder=Path(folder);manifest=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
    return [folder/job['folder']/name for job in manifest['jobs'] for name in job['plans']]

