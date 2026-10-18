"""Integration checks of collision repair using real frozen STL layer plans."""
import argparse
import json
import tempfile
from pathlib import Path
import numpy as np
import torch
from stable_baselines3 import PPO
from local_repair_env import LocalRepairEnv
from scheduler_env import plan_paths,metrics
from policy import SchedulerPolicy
from evaluate import deposition_signature
from validator_adapter import trajectory_from_rows
from waam_validator.collision.simulator import run_collision_analysis
from waam_validator.trajectory.validator import validate_trajectory_set

def main():
    p=argparse.ArgumentParser();p.add_argument('--plans',type=Path,required=True)
    p.add_argument('--all',action='store_true');p.add_argument('--output',type=Path)
    a=p.parse_args();torch.set_num_threads(2)
    paths=plan_paths(a.plans);results=[]
    env=LocalRepairEnv(paths)
    model=PPO(SchedulerPolicy,env,n_steps=8,batch_size=8,device='cpu',seed=42,
              policy_kwargs=dict(net_arch=dict(pi=[128,128],vf=[128,128])))
    for index in range(len(paths) if a.all else min(2,len(paths))):
        obs,_=env.reset(seed=42,options={'plan_index':index})
        start_homes=env.homes.copy();done=False
        # Deliberately propose concurrent work without repairs. Compare the
        # vectorized conflict result against the independent official simulator.
        raw=[env._window(r) for r in range(3)]
        for r in range(3):
            if env.pending[r]:raw[r]=env._task_rows(env.tasks[env.pending[r][0]])
        from scheduler_env import pad
        raw=pad(raw,max(x[-1][0] for x in raw))
        fast=env._check(raw)
        official=run_collision_analysis(trajectory_from_rows(raw),env.config).events
        assert bool(fast)==bool(official),'Conflict sampler disagreement'
        with torch.no_grad():
            dist=model.policy.get_distribution(torch.as_tensor(obs).unsqueeze(0))
            assert np.all(dist.distribution.probs.numpy()[0][env.mask==0]==0)
        while not done:
            valid=np.flatnonzero(env.mask[2:])+2
            # Test a reproducible continuation-biased control, independent of PPO.
            if len(valid):
                action=min(valid,key=lambda v:(len(env.choices[v]['repairs']),
                    sum(x['distance_mm'] for x in env.choices[v]['repairs']),
                    env.choices[v]['rows'][env.choices[v]['task']['robot']][-1][0]))
            else:action=0
            if action>=2:
                proposal=env.choices[action]
                reserved=[env._window(r) for r in range(3)]
                for r,rows in proposal['rows'].items():reserved[r]=rows
                reserved=pad(reserved,max(x[-1][0] for x in reserved))
                assert not run_collision_analysis(trajectory_from_rows(reserved),env.config).events
            prev=[list(map(list,row)) for row in env.rows]
            prev_time=env.now
            obs,reward,done,_,info=env.step(action)
            assert np.isfinite(reward) and env.now>=prev_time
            # Already committed motion must remain intact (last row's mode may
            # change when a new interval is appended at a previous endpoint).
            for old,new in zip(prev,env.rows):
                assert old[:-1]==new[:len(old)-1]
                assert old[-1][:4]==new[len(old)-1][:4]
        assert not info['failed'],info
        expected=[[],[],[]]
        from collections import Counter
        sig=Counter((t['robot'],*[round(float(v),4) for v in (*a,env.plan['z'])],
                     *[round(float(v),4) for v in (*b,env.plan['z'])])
                    for t in env.tasks for a,b in t['segments'])
        assert sig==deposition_signature(env.rows),'Changed D geometry or robot'
        tr=trajectory_from_rows(env.rows)
        assert not validate_trajectory_set(tr,env.config).violations
        assert not run_collision_analysis(tr,env.config).events
        assert np.allclose([row[-1][1:4] for row in env.rows],start_homes)
        value=dict(**info,steps=env.steps)
        results.append(value)
        print(f"PASS {env.plan['id']}: {env.now:.2f}s; yields={env.yield_count}; fallback={env.home_fallbacks}; steps={env.steps}",flush=True)
    with tempfile.TemporaryDirectory() as tmp:
        model.save(Path(tmp)/'smoke.zip');reload=PPO.load(Path(tmp)/'smoke.zip',device='cpu')
        assert int(model.predict(obs,deterministic=True)[0])==int(reload.predict(obs,deterministic=True)[0])
    model.learn(total_timesteps=8)
    if a.output:a.output.write_text(json.dumps(results,indent=2),encoding='utf-8')
    print('PASS: masks, immutable committed prefix, D endpoints/owner conservation, official collision and trajectory checks, layer return, PPO update/save/reload',flush=True)

if __name__=='__main__':main()
