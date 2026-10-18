"""Compare scheduler checkpoints on representative training layers (not full-STL validation)."""
import argparse
import json
import torch
from pathlib import Path
import bootstrap
from stable_baselines3 import PPO
from policy import SchedulerPolicy
from planner import dump
from scheduler_env import SchedulerEnv,metrics
from validator_adapter import trajectory_from_rows
from waam_validator.collision.simulator import run_collision_analysis
from waam_validator.trajectory.validator import validate_trajectory_set
from evaluate import gantt

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--plans',type=Path,required=True);p.add_argument('--run',type=Path,required=True)
    a=p.parse_args();manifest=json.loads((a.plans/'manifest.json').read_text(encoding='utf-8'))
    paths=[a.plans/j['folder']/j['plans'][0] for j in manifest['jobs']]
    torch.set_num_threads(2)
    env=SchedulerEnv(paths)
    saved=a.run/'training_layer_diagnostics.json'
    results=json.loads(saved.read_text(encoding='utf-8')) if saved.exists() else []
    completed={(r['checkpoint'],r['plan']) for r in results}
    for checkpoint in ('scheduler_initial.zip','scheduler_final.zip'):
        model=PPO.load(a.run/checkpoint,device='cpu')
        for index,path in enumerate(paths):
            plan_id=json.loads(path.read_text(encoding='utf-8'))['id']
            if (checkpoint,plan_id) in completed:continue
            obs,_=env.reset(seed=10042,options=dict(plan_index=index));done=False
            while not done:
                action,_=model.predict(obs,deterministic=True)
                obs,_,done,_,info=env.step(action)
            if info['failed']:raise RuntimeError(info)
            tr=trajectory_from_rows(env.rows)
            assert not validate_trajectory_set(tr,env.config).violations
            collisions=len(run_collision_analysis(tr,env.config).events)
            value=dict(checkpoint=checkpoint,plan=env.plan['id'],baseline_duration=env.ref,
                **metrics(env.rows),collision_events=collisions,waits=env.waits,reordered_tasks=env.reorders,
                note='Sampled training layer; full shape IoU/Validator status is not evaluated here.')
            charts=a.run/'training_layer_gantt';charts.mkdir(exist_ok=True)
            chart=charts/f'{checkpoint.removesuffix(".zip")}_{env.plan["id"]}.html'
            gantt(env.rows,chart,f'Training layer {env.plan["id"]} / {checkpoint}')
            results.append(value);dump(a.run/'training_layer_diagnostics.json',results)
            print(f"{checkpoint} {env.plan['id']}: {env.ref:.2f} -> {env.now:.2f}s; concurrent D={value['deposition_2plus_s']:.2f}s; collision_events={collisions}",flush=True)

if __name__=='__main__':main()
