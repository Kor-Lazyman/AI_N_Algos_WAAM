"""Predict conflicts, repair only the uncommitted schedule, then verify again.

Depositions remain frozen minor_2 segments. A completed task holds its endpoint;
only a conflicting idle robot yields. No mid-bead interruption or per-task home
tour is introduced. PPO chooses the next task, near/far yield, or event wait.
"""
from __future__ import annotations
import itertools
import json
from pathlib import Path
import numpy as np
from gymnasium import spaces
from scheduler_env import SchedulerEnv, metrics, pad
from validator_adapter import load_config, trajectory_from_rows
from waam_validator.collision.simulator import run_collision_analysis
from waam_validator.collision.geometry2d import check_arm_envelope_xy_batch
from waam_validator.trajectory.validator import validate_trajectory_set
from waam_validator.errors import WaamValidatorError


class LocalRepairEnv(SchedulerEnv):
    schema = 'local_conflict_repair_v1'

    def __init__(self, plan_paths, candidates=4):
        super().__init__(plan_paths, candidates)
        self.n = 2 + 6 * candidates
        self.action_space = spaces.Discrete(self.n)
        # 10 global, 5 per robot, 14 per task/repair proposal, action mask.
        self.observation_space = spaces.Box(-np.inf, np.inf,
            shape=(25 + 14 * 6 * candidates + self.n,), dtype=np.float32)

    def reset(self, *, seed=None, options=None):
        import gymnasium as gym
        gym.Env.reset(self, seed=seed)
        if seed is not None:
            self.cycle = []
        if options and 'plan_index' in options:
            index = int(options['plan_index'])
        else:
            if not self.cycle:
                self.cycle = list(self.np_random.permutation(len(self.paths)))
            index = int(self.cycle.pop())
        self.path = self.paths[index]
        self.plan = json.loads(self.path.read_text(encoding='utf-8'))
        self.config = load_config(self.path.parent / 'config.yaml')
        self.robots = sorted(self.config.robots, key=lambda r: r.id)
        self.homes = np.asarray([r.home_xyz_mm for r in self.robots], dtype=np.float32).astype(float)
        self.rows = [[[0., *p, 'W']] for p in self.homes]
        self.ends = [0.] * 3
        self.now = 0.; self.steps = 0; self.done = self.failed = False
        self.ref = max(1., self.plan['baseline_duration'])
        self.tasks = []
        for source in self.plan['tasks']:
            points = np.asarray(source['segments'], dtype=float)
            dep = np.linalg.norm(points[:, 1] - points[:, 0], axis=1).sum() / self.config.process.deposition_speed_mm_s
            self.tasks.append(dict(source, deposition=float(dep), start=points[0, 0],
                                   end=points[-1, 1], center=points.reshape(-1, 2).mean(axis=0)))
        self.pending = [[t['id'] for t in self.tasks if t['robot'] == r] for r in range(3)]
        self.total_dep = sum(t['deposition'] for t in self.tasks)
        self.assigned_dep = 0.; self.dispatched = []; self.trace = []
        self.waits = self.short_waits = self.reorders = self.blocked_checks = 0
        self.yield_count = self.repair_checks = self.predicted_conflicts = 0
        self.yield_distance = 0.; self.home_fallbacks = 0
        return self._observe(), self._info()

    def _window(self, robot):
        """Uncommitted start is the actual endpoint, never an implicit home."""
        own = self.rows[robot]
        if own[-1][0] <= self.now + 1e-8:
            return [[0., *own[-1][1:4], 'W']]
        i = max(0, int(np.searchsorted([p[0] for p in own], self.now, side='right') - 1))
        a, b = own[i], own[i + 1]
        point = np.asarray(a[1:4]) + (np.asarray(b[1:4]) - a[1:4]) * ((self.now-a[0])/(b[0]-a[0]))
        return [[0., *point, a[4]], *[[p[0]-self.now, *p[1:]] for p in own[i+1:]]]

    def _task_rows(self, task, delay=0.):
        own = [[0., *self._window(task['robot'])[0][1:4], 'W']]
        if delay > 1e-8:
            own.append([delay, *own[-1][1:4], 'W'])
        for a, b in task['segments']:
            self._move(own, (*a, self.plan['z']), 'T')
            self._move(own, (*b, self.plan['z']), 'D')
        return own

    @staticmethod
    def _positions(own, times):
        """Vectorized counterpart of official interpolate_robot_state."""
        stamps=np.asarray([p[0] for p in own],float)
        xyz=np.asarray([p[1:4] for p in own],np.float32).astype(float)
        idx=np.clip(np.searchsorted(stamps,times,side='right')-1,0,len(stamps)-2)
        alpha=np.clip((times-stamps[idx])/(stamps[idx+1]-stamps[idx]),0.,1.)
        return (xyz[idx]+alpha[:,None]*(xyz[idx+1]-xyz[idx])).astype(np.float32).astype(float)

    def _at_times(self, rows, times):
        xy=[self._positions(own,times)[:,:2] for own in rows]
        c = self.config.collision
        conflicts = []
        for a,b in ((0,1),(0,2),(1,2)):
            ra,rb = self.robots[a],self.robots[b]
            hit = np.zeros(len(times),dtype=bool)
            if c.check_tcp_radius:
                dist = np.linalg.norm(xy[a]-xy[b],axis=1)
                required = ra.tcp_radius_mm + rb.tcp_radius_mm
                hit |= dist <= required if c.touching_is_collision else dist < required
            if c.check_arm_envelope:
                hit |= check_arm_envelope_xy_batch(np.asarray(ra.base_xyz_mm[:2]),xy[a],ra.arm_envelope_radius_mm,
                    np.asarray(rb.base_xyz_mm[:2]),xy[b],rb.arm_envelope_radius_mm,
                    c.arm_clearance_mm,c.geometry_epsilon_mm,c.touching_is_collision).collision
            if hit.any():
                conflicts.append(dict(time_s=float(times[np.flatnonzero(hit)[0]]),robots=[a,b]))
        return min(conflicts,key=lambda x:x['time_s']) if conflicts else None

    def _check(self, rows, official=True):
        """Fast rejection, then official geometry at the same adaptive samples.

        Vectorization preserves float32 interpolation and both time/displacement
        subdivisions of iter_simulation_samples. Full official validation still
        runs on every completed layer and complete exported STL.
        """
        self.repair_checks+=1
        end=max(max(x[-1][0] for x in rows),.001);rows=pad(rows,end)
        knots=np.asarray(sorted({p[0] for own in rows for p in own}),float)
        quick=np.unique(np.r_[knots,(knots[:-1]+knots[1:])/2])
        conflict=self._at_times(rows,quick)
        if conflict:
            self.blocked_checks+=1;return conflict
        if not official:return None
        try:
            tr = trajectory_from_rows(rows)
            violations = validate_trajectory_set(tr,self.config).violations
            if violations:
                return dict(time_s=0.,robots=[],reason='trajectory_invalid')
            positions=np.stack([self._positions(own,knots) for own in rows],axis=1)
            displacements=np.linalg.norm(np.diff(positions,axis=0),axis=2).max(axis=1)
            subdivisions=np.maximum(1,np.maximum(np.ceil(np.diff(knots)/self.config.simulation.max_time_step_s),
                np.ceil(displacements/self.config.simulation.max_tcp_step_mm))).astype(int)
            times=np.concatenate([left+(right-left)*np.arange(n)/n
                for left,right,n in zip(knots[:-1],knots[1:],subdivisions)]+[knots[-1:]])
            conflict=self._at_times(rows,times)
            if conflict:self.blocked_checks+=1
            return conflict
        except WaamValidatorError:
            return dict(time_s=0.,robots=[],reason='trajectory_invalid')

    def _park_points(self, robot, extra):
        """Search outward towards own base in XY; no pretend Z-only avoidance."""
        start = np.asarray(self._window(robot)[0][1:4],float)
        direction = np.asarray(self.robots[robot].base_xyz_mm[:2]) - start[:2]
        length = np.linalg.norm(direction)
        if length < 1e-5:
            return
        direction /= length
        distances = list(np.arange(25., 425., 25.)) + [450.,500.,600.,800.,1000.]
        for d in distances:
            if d<extra:continue
            if d < length-1.:
                yield np.array([*(start[:2]+direction*d),start[2]]),False
        # Recovery only: if no local candidate is safe, still verify a home retreat.
        if np.linalg.norm(start-self.homes[robot]) > 1e-5:
            yield self.homes[robot],True

    def _proposal(self, task, far=False, near=None):
        r = task['robot']
        if self.ends[r] > self.now+1e-8:
            return None
        rows = [self._window(i) for i in range(3)]
        rows[r] = self._task_rows(task)
        conflict = self._check(rows)
        if conflict is None:
            if far: return None  # Do not duplicate a conflict-free action.
            return dict(task=task,rows={r:rows[r]},repairs=[],conflict=None,delay=0.)
        self.predicted_conflicts += 1
        initial = dict(conflict)
        repairs=[];changed={};delay=0.
        # At most two other robots can obstruct a reservation. Recheck after
        # every changed retreat. Busy reservations are immutable: wait/reorder.
        for iteration in range(3):
            blockers=[i for i in conflict['robots'] if i!=r and self.ends[i]<=self.now+1e-8 and i not in changed]
            if not blockers:
                return None
            blocker=blockers[0];found=False
            minimum=0.
            if far and near:
                minimum=max((x['distance_mm']+100. for x in near['repairs'] if x['robot']==blocker+1),default=100.)
            for point,fallback in self._park_points(blocker,minimum):
                own=self._window(blocker)
                if delay>1e-8:own.append([delay,*own[-1][1:4],'W'])
                self._move(own,point,'T')
                new_delay=own[-1][0]
                # First ensure the retreat itself is safe while the selected
                # robot waits. Then check the amended full task and future holds.
                retreat=[self._window(i) for i in range(3)]
                for i,value in changed.items():retreat[i]=value
                retreat[blocker]=own
                candidate=[self._window(i) for i in range(3)]
                for i,value in changed.items():candidate[i]=value
                candidate[blocker]=own;candidate[r]=self._task_rows(task,new_delay)
                # Reject insufficient clearance cheaply before running the
                # official dense sampler on an otherwise safe retreat.
                next_conflict=self._check(candidate,official=False)
                if next_conflict is not None and blocker in next_conflict['robots']:
                    continue
                if self._check(retreat):continue
                if next_conflict is None:
                    next_conflict=self._check(candidate)
                    if next_conflict is not None and blocker in next_conflict['robots']:
                        continue
                distance=float(np.linalg.norm(np.asarray(own[-1][1:4])-own[0][1:4]))
                repairs.append(dict(robot=blocker+1,distance_mm=distance,home_fallback=fallback,
                    from_xyz=own[0][1:4],to_xyz=own[-1][1:4],duration_s=new_delay-delay))
                changed[blocker]=own;rows=candidate;delay=new_delay;conflict=next_conflict;found=True
                break
            if not found:return None
            if conflict is None:
                changed[r]=rows[r]
                return dict(task=task,rows=changed,repairs=repairs,conflict=initial,delay=delay)
        return None

    def _observe(self):
        self.choices=[None]*self.n;mask=np.zeros(self.n,dtype=np.float32)
        active=[end for end in self.ends if end>self.now+1e-8]
        if active and not self.done:mask[:2]=1.
        features=[self.now/self.ref,self.assigned_dep/max(self.total_dep,1e-9),
            sum(map(len,self.pending))/max(len(self.tasks),1),self.total_dep/self.ref,
            self.plan['z']/2000.,self.plan['layer_iou'],self.steps/max(len(self.tasks),1),
            self.yield_count/max(len(self.tasks),1),self.yield_distance/2000.,1.]
        for r in range(3):
            pos=self._window(r)[0][1:3]
            features.extend([max(0.,self.ends[r]-self.now)/self.ref,len(self.pending[r])/max(len(self.tasks),1),
                             float(self.ends[r]>self.now+1e-8),pos[0]/2000.,pos[1]/2000.])
        for r in range(3):
            ids=self.pending[r]
            slots=np.linspace(0,len(ids)-1,min(self.k,len(ids)),dtype=int).tolist() if ids else []
            for slot in range(self.k):
                near=None
                for far in (False,True):
                    action=2+2*(r*self.k+slot)+int(far)
                    if slot>=len(slots) or self.done:
                        features.extend([0.]*14);continue
                    position=slots[slot];task=self.tasks[ids[position]]
                    if far:
                        proposal=self._proposal(task,True,near) if near and near['repairs'] else None
                    else:
                        proposal=self._proposal(task);near=proposal
                    self.choices[action]=proposal;mask[action]=float(proposal is not None)
                    repairs=proposal['repairs'] if proposal else []
                    features.extend([*list(task['start']/2000),*list(task['end']/2000),*list(task['center']/2000),
                        task['deposition']/self.ref,position/max(len(ids),1),float(far),float(proposal is not None),
                        sum(v['distance_mm'] for v in repairs)/2000.,len(repairs)/2.,
                        proposal['delay']/self.ref if proposal else 0.,
                        proposal['conflict']['time_s']/self.ref if proposal and proposal['conflict'] else 0.])
        self.deadlocked=not bool(mask.any())
        if self.deadlocked:mask[0]=1.
        self.mask=mask
        obs=np.asarray(features+mask.tolist(),dtype=np.float32)
        assert obs.shape==self.observation_space.shape
        return obs

    def _commit(self, r, relative):
        own=self.rows[r]
        assert own[-1][0]<=self.now+1e-7,'Must not replace a busy reservation'
        assert np.linalg.norm(np.asarray(own[-1][1:4])-relative[0][1:4])<1e-4
        if own[-1][0]<self.now-1e-8:own.append([self.now,*own[-1][1:4],'W'])
        own[-1][4]=relative[0][4]
        own.extend([[p[0]+self.now,*p[1:]] for p in relative[1:]])
        self.ends[r]=own[-1][0]

    def _finish(self):
        """Home only at the layer boundary; verify parallel or sequential return."""
        self.now=max(self.ends)
        rows=[self._window(r) for r in range(3)]
        for r in range(3):self._move(rows[r],self.homes[r],'T')
        if self._check(rows):
            for order in itertools.permutations(range(3)):
                rows=[self._window(r) for r in range(3)];delay=0.
                for r in order:
                    if delay>1e-8:rows[r].append([delay,*rows[r][-1][1:4],'W'])
                    self._move(rows[r],self.homes[r],'T');delay=rows[r][-1][0]
                if self._check(rows) is None:break
            else:
                self.failed=self.done=True;return
        for r in range(3):self._commit(r,rows[r])
        self.trace.append(dict(action='LAYER_END_RETURN',start=self.now,end=max(self.ends)))
        self.now=max(self.ends);self.rows=pad(self.rows,self.now);self.done=True
        tr=trajectory_from_rows(self.rows)
        if validate_trajectory_set(tr,self.config).violations or run_collision_analysis(tr,self.config).events:
            self.failed=True

    def _info(self):
        return dict(plan=self.plan['id'],elapsed_s=self.now,dispatches=len(self.dispatched),
            waits=self.waits,short_waits=self.short_waits,reordered_tasks=self.reorders,
            blocked_checks=self.blocked_checks,remaining_tasks=sum(map(len,self.pending)),failed=self.failed,
            local_yields=self.yield_count,yield_distance_mm=self.yield_distance,
            repair_checks=self.repair_checks,predicted_conflicts=self.predicted_conflicts,home_fallbacks=self.home_fallbacks)

    def step(self,action):
        if self.done:raise RuntimeError('Reset completed episode')
        action=int(action)
        if not 0<=action<self.n or not self.mask[action]:raise ValueError('Unsafe/unavailable action')
        previous=self.now;progress=0.;self.steps+=1;distance=0.
        if action<2:
            if self.deadlocked:
                self.done=self.failed=True
                return self._observe(),-10.,True,False,dict(self._info(),failure_reason='no_safe_repair')
            next_end=min(end for end in self.ends if end>self.now+1e-8)
            if action==0:self.now=next_end
            else:
                # Revisit the first future path knot, or after at most 2 s.
                knots=[p[0] for own in self.rows for p in own if p[0]>self.now+1e-7]
                self.now=min(next_end,self.now+2.,min(knots)+.001)
                self.short_waits+=1
            self.waits+=1
            self.trace.append(dict(action='RECHECK_WAIT' if action else 'WAIT_EVENT',start=previous,end=self.now))
        else:
            proposal=self.choices[action];task=proposal['task'];r=task['robot']
            position=self.pending[r].index(task['id']);self.reorders+=int(position>0)
            for i,own in proposal['rows'].items():self._commit(i,own)
            self.pending[r].remove(task['id']);self.dispatched.append(task['id'])
            self.assigned_dep+=task['deposition'];progress=task['deposition']/max(self.total_dep,1e-9)
            self.yield_count+=len(proposal['repairs'])
            distance=sum(x['distance_mm'] for x in proposal['repairs']);self.yield_distance+=distance
            self.home_fallbacks+=sum(x['home_fallback'] for x in proposal['repairs'])
            self.trace.append(dict(action='REPAIR_DISPATCH' if proposal['repairs'] else 'DIRECT_DISPATCH',
                robot=r+1,task=task['id'],start=self.now,end=self.ends[r],reordered=position>0,
                predicted_conflict=proposal['conflict'],repairs=proposal['repairs'],
                verification='official collision geometry with adaptive sampling; full official check at layer end'))
        if not any(self.pending):self._finish()
        reward=progress-(self.now-previous)/self.ref-.02*distance/1000.
        if self.done and not self.failed:
            self.result=metrics(self.rows)
            reward+=10*self.result['mean_deposition_utilization']*self.ref/max(self.now,1e-9)
        if self.steps>80*len(self.tasks)+200:self.done=self.failed=True
        if self.failed:reward=-10.
        obs=self._observe();info=self._info()
        if self.done and not self.failed:info.update(self.result)
        return obs,float(reward),self.done,False,info
