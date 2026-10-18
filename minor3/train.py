"""Alternate whole-layer path PPO and collision-detour PPO; makespan only."""
import argparse
import hashlib
import json
import shutil
import time
from pathlib import Path
import torch
import bootstrap
from stable_baselines3 import PPO
from stable_baselines3.common.monitor import Monitor
from stable_baselines3.common.callbacks import BaseCallback
from source import dataset
from avoidance import AvoidanceEnv
from runtime import PathEnv,dump
from policy import AvoidancePolicy
from evaluate import evaluate

class Episodes(BaseCallback):
    def __init__(self,path,label):super().__init__();self.path=path;self.label=label;self.records=[]
    def _on_step(self):
        for info in self.locals['infos']:
            if 'episode' in info:
                self.records.append({k:v for k,v in info.items() if k!='terminal_observation'})
                dump(self.path,self.records)
                for key in ('makespan_s','repairs','interrupted_D','detour_distance_mm','failed'):
                    self.logger.record_mean(self.label+'/'+key,float(info[key]))
        return True

def main():
    p=argparse.ArgumentParser();p.add_argument('--train-plans',type=Path,required=True)
    p.add_argument('--validation-plans',type=Path,required=True);p.add_argument('--initial-path',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--updates',type=int,default=40)
    p.add_argument('--path-steps',type=int,default=2);p.add_argument('--avoid-steps',type=int,default=8)
    p.add_argument('--device',default='cuda');p.add_argument('--seed',type=int,default=42);a=p.parse_args()
    if min(a.updates,a.path_steps,a.avoid_steps)<1 or min(a.path_steps,a.avoid_steps)<2:p.error('updates>=1, rollout steps>=2')
    if a.device=='cuda' and not torch.cuda.is_available():p.error('CUDA unavailable')
    torch.set_num_threads(2);a.output.mkdir(parents=True,exist_ok=False)
    snapshot=a.output/'source';snapshot.mkdir()
    for file in bootstrap.ROOT.glob('*.py'):shutil.copy2(file,snapshot/file.name)
    initial_hash=hashlib.sha256(a.initial_path.read_bytes()).hexdigest()
    start=time.perf_counter();meta=dict(status='preparing',version='minor3',device=a.device,updates=a.updates,
        path_steps=a.path_steps,avoid_steps=a.avoid_steps,early_stopping=False,seed=a.seed,
        initial_path_model=str(a.initial_path.resolve()),initial_path_sha256=initial_hash,
        both_policies_trainable=True,iou_computed=False,validator_run=False,reward='negative normalized makespan only',
        failure_objective='20 * reference or 10 * initial parallel span, whichever is larger; not a successful makespan')
    dump(a.output/'training.json',meta)
    try:
        pool,_,train_meta=dataset(a.train_plans)
        _,val_jobs,val_meta=dataset(a.validation_plans,all_layers=True)
        train_hash={j['input_sha256']['target.stl'] for j in train_meta['jobs']}
        val_hash={j['input_sha256']['target.stl'] for j in val_meta['jobs']}
        if train_hash&val_hash:raise ValueError('Training/validation overlap')
        dump(a.output/'dataset.json',dict(train_root=a.train_plans.resolve(),validation_root=a.validation_plans.resolve(),
                                        train=train_meta,validation=val_meta))
        path_env=PathEnv(pool);previous=PPO.load(a.initial_path,device=a.device)
        path_model=PPO('MlpPolicy',Monitor(path_env),n_steps=a.path_steps,batch_size=a.path_steps,
            n_epochs=5,gamma=1.,learning_rate=1e-4,ent_coef=.01,target_kl=None,device=a.device,seed=a.seed,
            policy_kwargs=previous.policy_kwargs,tensorboard_log=str(a.output/'tensorboard'),verbose=0)
        path_model.policy.load_state_dict(previous.policy.state_dict());del previous
        avoid_env=AvoidanceEnv(pool,path_model)
        avoid_model=PPO(AvoidancePolicy,Monitor(avoid_env),n_steps=a.avoid_steps,batch_size=a.avoid_steps,
            n_epochs=5,gamma=1.,learning_rate=3e-4,ent_coef=.01,target_kl=None,device=a.device,seed=a.seed,
            policy_kwargs=dict(net_arch=dict(pi=[128,128],vf=[128,128])),tensorboard_log=str(a.output/'tensorboard'),verbose=0)
        path_env.avoid_model=avoid_model
        path_model.save(a.output/'path_initial.zip');avoid_model.save(a.output/'avoidance_initial.zip')
        meta.update(status='validation_before',train_layers=len(pool));dump(a.output/'training.json',meta)
        before=evaluate(path_model,avoid_model,val_jobs,a.output/'validation_before')
        pcallback=Episodes(a.output/'path_episodes.json','path');acallback=Episodes(a.output/'avoidance_episodes.json','avoidance')
        for update in range(1,a.updates+1):
            # The other policy stays fixed throughout each PPO rollout/update.
            avoid_model._last_obs=None
            avoid_model.learn(a.avoid_steps,reset_num_timesteps=False,callback=acallback,tb_log_name='avoidance')
            path_model.learn(a.path_steps,reset_num_timesteps=False,callback=pcallback,tb_log_name='path')
            meta.update(status='training',completed_updates=update,path_timesteps=path_model.num_timesteps,
                        avoidance_timesteps=avoid_model.num_timesteps,wall_time_s=time.perf_counter()-start)
            dump(a.output/'training.json',meta)
            print(f"update {update}/{a.updates}: path={path_model.num_timesteps}, avoidance={avoid_model.num_timesteps}, elapsed={meta['wall_time_s']:.1f}s",flush=True)
            if update%10==0:
                path_model.save(a.output/'path_checkpoint.zip');avoid_model.save(a.output/'avoidance_checkpoint.zip')
        path_model.save(a.output/'path_final.zip');avoid_model.save(a.output/'avoidance_final.zip')
        meta.update(status='validation_after');dump(a.output/'training.json',meta)
        after=evaluate(path_model,avoid_model,val_jobs,a.output/'validation_after')
        comparison=[dict(id=b['id'],minor2_s=b['baseline_minor2_s'],before_s=b['makespan_s'],after_s=c['makespan_s'],
                         before_complete=b['complete'],after_complete=c['complete']) for b,c in zip(before,after)]
        dump(a.output/'comparison.json',comparison)
        meta.update(status='completed',wall_time_s=time.perf_counter()-start,
            complete_validation=sum(j['complete'] for j in after),path_episodes=len(pcallback.records),avoidance_episodes=len(acallback.records),
            path_weights_changed=not all(torch.equal(x.cpu(),y.cpu()) for x,y in zip(path_model.policy.parameters(),PPO.load(a.output/'path_initial.zip',device='cpu').policy.parameters())),
            avoidance_weights_changed=not all(torch.equal(x.cpu(),y.cpu()) for x,y in zip(avoid_model.policy.parameters(),PPO.load(a.output/'avoidance_initial.zip',device='cpu').policy.parameters())))
        dump(a.output/'training.json',meta)
        print('COMPLETED',a.output,flush=True)
    except Exception as exc:
        meta.update(status='failed',error=f'{type(exc).__name__}: {exc}',wall_time_s=time.perf_counter()-start)
        dump(a.output/'training.json',meta);raise

if __name__=='__main__':main()
