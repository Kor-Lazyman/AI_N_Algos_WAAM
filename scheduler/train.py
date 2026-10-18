"""Train only the scheduler PPO. minor_2 stays frozen in the prepared plans."""
from __future__ import annotations
import argparse
from datetime import datetime
import json
from pathlib import Path
import time
import shutil
import bootstrap
import numpy as np
import torch
from stable_baselines3 import PPO
from stable_baselines3.common.monitor import Monitor
from stable_baselines3.common.callbacks import BaseCallback
from scheduler_env import SchedulerEnv,plan_paths
from local_repair_env import LocalRepairEnv
from policy import SchedulerPolicy
from planner import dump,digest
from evaluate import evaluate

class LogCallback(BaseCallback):
    def __init__(self,output):
        super().__init__();self.output=Path(output);self.completed=[]
    def _on_step(self):
        for info in self.locals['infos']:
            if 'episode' in info:
                self.completed.append(dict({k:v for k,v in info.items() if k!='terminal_observation'},training_step=self.num_timesteps))
                dump(self.output/'training_episodes.json',self.completed)
                for key in ('waits','short_waits','reordered_tasks','blocked_checks','failed','deposition_2plus_s','mean_deposition_utilization','local_yields','yield_distance_mm','home_fallbacks'):
                    if key in info:self.logger.record_mean('scheduler/'+key,float(info[key]))
        return True

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--train-plans',type=Path,required=True);p.add_argument('--validation-plans',type=Path,required=True)
    p.add_argument('--output',type=Path,default=None);p.add_argument('--updates',type=int,default=40)
    p.add_argument('--n-steps',type=int,default=64);p.add_argument('--device',default='cuda');p.add_argument('--seed',type=int,default=42)
    p.add_argument('--mode',choices=['local-repair','home-tours'],default='local-repair')
    a=p.parse_args()
    if a.updates<1 or a.n_steps<2:p.error('updates >=1 and n-steps >=2 required')
    if a.device.startswith('cuda') and not torch.cuda.is_available():p.error('CUDA unavailable')
    train_meta=json.loads((a.train_plans/'manifest.json').read_text(encoding='utf-8'))
    validation_meta=json.loads((a.validation_plans/'manifest.json').read_text(encoding='utf-8'))
    if train_meta['model_sha256']!=validation_meta['model_sha256']:raise ValueError('Different frozen planners')
    train_hash={j['input_sha256']['target.stl'] for j in train_meta['jobs']}
    val_hash={j['input_sha256']['target.stl'] for j in validation_meta['jobs']}
    if train_hash&val_hash:raise ValueError('Train/validation STL overlap')
    output=a.output or bootstrap.ROOT/'result'/datetime.now().strftime('scheduler_%Y%m%d_%H%M%S')
    output.mkdir(parents=True,exist_ok=False)
    source=output/'source';source.mkdir()
    for path in bootstrap.ROOT.glob('*.py'):shutil.copy2(path,source/path.name)
    torch.set_num_threads(2)
    env_class=LocalRepairEnv if a.mode=='local-repair' else SchedulerEnv
    env=Monitor(env_class(plan_paths(a.train_plans)),str(output/'monitor.csv'))
    model=PPO(SchedulerPolicy,env,device=a.device,seed=a.seed,n_steps=a.n_steps,batch_size=min(32,a.n_steps),
              learning_rate=3e-4,gamma=.995,gae_lambda=.95,n_epochs=10,ent_coef=.01,target_kl=None,
              policy_kwargs=dict(net_arch=dict(pi=[128,128],vf=[128,128])),verbose=1,tensorboard_log=str(output/'tensorboard'))
    model.save(output/'scheduler_initial.zip')
    meta=dict(status='running',schema=env_class.schema if a.mode=='local-repair' else 'scheduler_v2',mode=a.mode,frozen_model_sha256=train_meta['model_sha256'],
              train_plans=str(a.train_plans.resolve()),validation_plans=str(a.validation_plans.resolve()),
              updates=a.updates,n_steps=a.n_steps,device=str(model.device),early_stopping=False,
              policy='SchedulerPolicy (masked PPO)',action='event wait, short recheck, or robot/task with near/far conflict retreat' if a.mode=='local-repair' else 'WAIT, WAIT_SHORT, or robot/candidate task',
              reward='delta_D / total_D - delta_t / reference - 0.02 * yield_distance_m + terminal(10 * mean_D_util * reference / makespan)' if a.mode=='local-repair' else 'delta_D / total_D - delta_t / reference + terminal(10 * mean_D_util * reference / makespan)',
              minor_2_trainable=False,train_layers=len(plan_paths(a.train_plans)))
    dump(output/'training.json',meta);start=time.perf_counter()
    try:
        before=evaluate(model,a.validation_plans,output/'validation_before',a.device,a.mode)
    except Exception as exc:
        meta.update(status='failed',stage='validation_before',error=f'{type(exc).__name__}: {exc}')
        dump(output/'training.json',meta);raise
    callback=LogCallback(output)
    # One learn call: no early stopping; the initial model is saved for comparison.
    try:
        model.learn(total_timesteps=a.updates*a.n_steps,callback=callback,tb_log_name='scheduler',progress_bar=False)
    except Exception as exc:
        model.save(output/'interrupted_checkpoint.zip')
        meta.update(status='failed',error=f'{type(exc).__name__}: {exc}',actual_timesteps=model.num_timesteps)
        dump(output/'training.json',meta)
        raise
    model.save(output/'scheduler_final.zip')
    try:
        after=evaluate(model,a.validation_plans,output/'validation_after',a.device,a.mode)
    except Exception as exc:
        meta.update(status='failed',stage='validation_after',error=f'{type(exc).__name__}: {exc}',actual_timesteps=model.num_timesteps)
        dump(output/'training.json',meta);raise
    rows=[]
    for b,c in zip(before['jobs'],after['jobs']):
        rows.append(dict(id=b['id'],minor_2_s=b['baseline_makespan_s'],scheduler_before_s=b['makespan_s'],
                         scheduler_after_s=c['makespan_s'],scheduler_improvement_pct=100*(1-c['makespan_s']/b['makespan_s']),
                         before_parallel_D_s=b['deposition_2plus_s'],after_parallel_D_s=c['deposition_2plus_s'],
                         validator_before=b['validator'],validator_after=c['validator']))
    dump(output/'comparison.json',rows)
    lines=['# Scheduler pilot results','', '| STL | minor_2 (s) | Scheduler before (s) | Scheduler after (s) | Improvement | Concurrent D before/after (s) | Validator |',
           '|---|---:|---:|---:|---:|---:|---|']
    for x in rows:lines.append(f"| {x['id']} | {x['minor_2_s']:.2f} | {x['scheduler_before_s']:.2f} | {x['scheduler_after_s']:.2f} | {x['scheduler_improvement_pct']:+.2f}% | {x['before_parallel_D_s']:.2f} / {x['after_parallel_D_s']:.2f} | {x['validator_before']} / {x['validator_after']} |")
    lines+=['','The initial scheduler is an untrained policy with the same collision masks. minor_2 uses the original whole-region serial fallback.',
            'Deposition endpoints and robot assignments are unchanged. Local-repair mode holds task endpoints and retreats only for a predicted conflict. Home-tours mode returns home after each task.','']
    (output/'comparison.md').write_text('\n'.join(lines),encoding='utf-8')
    meta.update(status='completed',actual_timesteps=model.num_timesteps,completed_updates=model.num_timesteps//a.n_steps,
                wall_time_s=time.perf_counter()-start,validation_passes=sum(j['validator']=='PASS' for j in after['jobs']),
                completed_training_episodes=len(callback.completed),
                visited_layer_ids=sorted({x['plan'] for x in callback.completed}))
    dump(output/'training.json',meta);env.close()
    print(f'Finished: {output}',flush=True)

if __name__=='__main__':main()

