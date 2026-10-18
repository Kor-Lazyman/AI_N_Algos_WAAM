"""Freeze minor_2 geometry. Cached traces are accepted only after policy replay."""
from __future__ import annotations
import argparse
import hashlib
import json
import shutil
from pathlib import Path
import numpy as np
import torch
import bootstrap
from stable_baselines3 import PPO
from layer_assignment_env import LayerPathEnv, generate_layer_segments

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def dump(path, value):
    def encode(item):
        if isinstance(item,np.ndarray):return item.tolist()
        if isinstance(item,np.generic):return item.item()
        if isinstance(item,Path):return str(item)
        raise TypeError(type(item).__name__)
    path=Path(path);temporary=path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2,default=encode), encoding='utf-8')
    temporary.replace(path)

def fresh_evaluation(model_path,stl_dir,output,device):
    """Run the frozen planner on new STL/config jobs when no rollout cache exists."""
    from evaluate_layers import discover_scenarios,evaluate_episode,input_hashes
    output=Path(output)
    output.mkdir(parents=True,exist_ok=False)
    model=PPO.load(model_path,device=device)
    model.policy.set_training_mode(False)
    for parameter in model.policy.parameters():parameter.requires_grad_(False)
    shutil.copy2(model_path,output/'model_snapshot.zip')
    report=dict(model_sha256=digest(model_path),model_timesteps=model.num_timesteps,jobs=[])
    for index,scenario in enumerate(discover_scenarios(Path(stl_dir))):
        env=LayerPathEnv(scenario)
        record=evaluate_episode(model,env,10042,output/f'job_{index:02d}/episode_000',progress_every=10)
        if record['status']!='PASS':raise ValueError(f'Frozen planner failed Validator: {scenario.name}')
        report['jobs'].append(dict(id=scenario.name,input_sha256=input_hashes(scenario),episodes=[record]))
        dump(output/'evaluation.json',report)
        env.close()
    return output

def chunks(groups, max_length=160., max_segments=16):
    """Only group existing D segments; never change their endpoints or owner."""
    tasks=[]
    for robot,segments in enumerate(groups):
        current=[]; length=0.
        for a,b in segments:
            n=float(np.linalg.norm(np.asarray(b)-a))
            # Neighboring hatch strokes can share one tour; an 8 mm hatch gap
            # must not force a ~2 metre round trip to home.
            near = not current or np.linalg.norm(np.asarray(current[-1][1])-a)<=80.
            if current and (not near or len(current)>=max_segments or length+n>max_length):
                tasks.append(dict(robot=robot, segments=current)); current=[]; length=0.
            current.append([list(a),list(b)]); length+=n
        if current:
            tasks.append(dict(robot=robot,segments=current))
    for i,task in enumerate(tasks):
        task['id']=i
    return tasks

def prepare(model_path, evaluation, output, layers_per_shape=0, chunk_mm=160., device='cuda'):
    model_path,evaluation,output=map(Path,(model_path,evaluation,output))
    if output.exists():
        raise FileExistsError(f'Use a new plan folder: {output}')
    report=json.loads((evaluation/'evaluation.json').read_text(encoding='utf-8'))
    model=PPO.load(model_path,device=device)
    snapshot_path=evaluation/'model_snapshot.zip'
    if digest(model_path)!=digest(snapshot_path):
        snapshot=PPO.load(snapshot_path,device='cpu')
        a,b=model.policy.state_dict(),snapshot.policy.state_dict()
        if (model.action_space!=snapshot.action_space or model.observation_space!=snapshot.observation_space
                or a.keys()!=b.keys() or any(not torch.equal(a[k].cpu(),b[k].cpu()) for k in a)):
            raise ValueError('Evaluation policy weights differ from requested frozen minor_2')
        del snapshot
        print('Archive metadata differ; exact policy tensor equality verified.',flush=True)
    model.policy.set_training_mode(False)
    for p in model.policy.parameters(): p.requires_grad_(False)
    output.mkdir(parents=True)
    shutil.copy2(model_path,output/'minor_2_frozen.zip')
    jobs=report.get('jobs',report.get('validation_jobs'))
    manifest=dict(schema='scheduler_plans_v1',model_sha256=digest(model_path),
                  source_model=str(model_path.resolve()),source_evaluation=str(evaluation.resolve()),
                  evaluation_snapshot_sha256=digest(snapshot_path),policy_weights_verified=True,
                  frozen_policy=True,chunk_mm=chunk_mm,max_link_gap_mm=80.,layers_per_shape=layers_per_shape,jobs=[])
    for i,job in enumerate(jobs):
        episode=evaluation/f'job_{i:02d}/episode_000'
        source=episode/'input'
        for name in ('target.stl','config.yaml'):
            if digest(source/name)!=job['input_sha256'][name]: raise ValueError('Changed input')
        trace=json.loads((episode/'layer_trace.json').read_text(encoding='utf-8'))
        env=LayerPathEnv(source)
        obs,_=env.reset(seed=10042)
        selected=set(range(len(trace))) if not layers_per_shape else set(np.linspace(0,len(trace)-1,min(layers_per_shape,len(trace)),dtype=int).tolist())
        folder=output/f'job_{i:02d}'; folder.mkdir()
        for name in ('target.stl','config.yaml'): shutil.copy2(source/name,folder/name)
        plans=[]
        for index,info in enumerate(trace):
            action,_=model.predict(obs,deterministic=True)
            if action.tolist()!=info['action']:
                raise ValueError(f'Frozen policy replay mismatch: {job["id"]} layer {index}')
            if index in selected:
                layer,target=env.layers[index]
                segments=generate_layer_segments(target,env.config.process.bead_width_mm,
                    env.config.shape_validation.polygon_buffer_resolution,action)
                groups,_=env._partition(segments,action)
                if groups is None: raise ValueError('Frozen planner produced unreachable work')
                tasklist=chunks(groups,chunk_mm)
                plan=dict(id=f'{job["id"]}_layer_{index:04d}',shape=job['id'],layer_index=index,
                          physical_layer=int(layer),z=env._z(layer),minor_action=action.tolist(),
                          baseline_duration=float(info['layer_duration_s']),layer_iou=float(info['layer_iou']),
                          tasks=tasklist)
                filename=f'layer_{index:04d}.json'; dump(folder/filename,plan); plans.append(filename)
            # Reconstruct the exact planner observation from its archived rollout.
            # Scheduling is downstream; minor_2 is never updated by scheduler PPO.
            env.index=index+1; env.current_iou=info['iou']; env.last_layer_iou=info['layer_iou']
            env.makespan=info['makespan_s']; env.last_duration=info['layer_duration_s']
            env.last_robot_counts=info['robot_segment_counts']; obs=env._observation()
        manifest['jobs'].append(dict(id=job['id'],folder=folder.name,plans=plans,
            total_layers=len(trace),complete_shape=len(plans)==len(trace),input_sha256=job['input_sha256'],
            baseline_evaluation_episode=str(episode.resolve()),baseline_makespan=float(trace[-1]['makespan_s'])))
        print(f'Planner replay {job["id"]}: {len(trace)} actions verified, {len(plans)} layers selected',flush=True)
        dump(output/'manifest.json',manifest)
    return manifest

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model',type=Path,required=True)
    source=p.add_mutually_exclusive_group(required=True)
    source.add_argument('--evaluation',type=Path);source.add_argument('--stl-dir',type=Path)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--layers-per-shape',type=int,default=0)
    p.add_argument('--chunk-mm',type=float,default=160);p.add_argument('--device',default='cuda')
    a=p.parse_args()
    if a.chunk_mm<=0 or a.layers_per_shape<0:p.error('chunk-mm >0 and layers-per-shape >=0 required')
    if a.stl_dir:
        a.evaluation=fresh_evaluation(a.model,a.stl_dir,a.output.with_name(a.output.name+'_minor2'),a.device)
    prepare(a.model,a.evaluation,a.output,a.layers_per_shape,a.chunk_mm,a.device)

