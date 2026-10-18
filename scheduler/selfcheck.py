"""Real-geometry integration checks; no training data or policy files are overwritten."""
import argparse
from pathlib import Path
import tempfile
import numpy as np
import torch
import bootstrap
from stable_baselines3 import PPO
from scheduler_env import SchedulerEnv,plan_paths,metrics
from policy import SchedulerPolicy
from evaluate import deposition_signature
from validator_adapter import trajectory_from_rows
from waam_validator.collision.simulator import run_collision_analysis
from waam_validator.trajectory.validator import validate_trajectory_set
from planner import dump

def main():
    p=argparse.ArgumentParser();p.add_argument('--plans',type=Path,required=True);a=p.parse_args()
    env=SchedulerEnv(plan_paths(a.plans));obs,_=env.reset(seed=42,options={'plan_index':0})
    model=PPO(SchedulerPolicy,env,n_steps=8,batch_size=8,device='cpu',seed=42,
              policy_kwargs=dict(net_arch=dict(pi=[128,128],vf=[128,128])))
    # Verify both prediction and PPO's minibatch path use the same validity mask.
    with torch.no_grad():
        distribution=model.policy.get_distribution(torch.as_tensor(obs).unsqueeze(0))
        probabilities=distribution.distribution.probs.cpu().numpy()[0]
    assert np.all(probabilities[env.mask==0]==0)
    values,logp,entropy=model.policy.evaluate_actions(torch.as_tensor(obs).unsqueeze(0),torch.tensor([int(probabilities.argmax())]))
    assert torch.isfinite(logp).all() and torch.isfinite(entropy).all()
    with tempfile.TemporaryDirectory() as d:
        dump(Path(d)/'numpy_log.json',{'observation':obs,'value':np.float32(1)})
        model.save(Path(d)/'test.zip');loaded=PPO.load(Path(d)/'test.zip',device='cpu')
        assert int(model.predict(obs,deterministic=True)[0])==int(loaded.predict(obs,deterministic=True)[0])
    first=int(np.flatnonzero(env.mask[1:env.short_wait])[0])+1
    obs,_,_,_,_=env.step(first)
    if env.mask[env.short_wait]:
        previous=env.now;pending=sum(map(len,env.pending))
        obs,_,_,_,_=env.step(env.short_wait)
        assert 0<env.now-previous<=10. and sum(map(len,env.pending))==pending
    obs,_=env.reset(seed=42,options={'plan_index':0})
    done=False;last_time=0.
    while not done:
        action,_=model.predict(obs,deterministic=True)
        assert env.mask[int(action)]==1
        obs,reward,done,_,info=env.step(action)
        assert env.now>=last_time and np.isfinite(reward);last_time=env.now
    assert not info['failed'] and len(set(env.dispatched))==len(env.tasks)
    expected=[[],[],[]]
    for task in env.tasks:
        for a,b in zip(task['rows'],task['rows'][1:]):
            if a[4]=='D':expected[task['robot']].extend([a,b])
    # Compare D lengths and counts directly against frozen tasks.
    actual=sum(b[0]-a[0] for own in env.rows for a,b in zip(own,own[1:]) if a[4]=='D')
    assert abs(actual-env.total_dep)<1e-6
    actual_count=sum(a[4]=='D' for own in env.rows for a in own[:-1])
    assert actual_count==sum(len(t['segments']) for t in env.tasks)
    trajectory=trajectory_from_rows(env.rows)
    assert not validate_trajectory_set(trajectory,env.config).violations
    assert not run_collision_analysis(trajectory,env.config).events
    completed_metrics=metrics(env.rows)
    model.learn(total_timesteps=8)
    print('PASS: masked distribution/update, save/load, dispatch uniqueness, WAIT clock, D conservation, official collision/trajectory checks')
    print(completed_metrics)

if __name__=='__main__':main()
