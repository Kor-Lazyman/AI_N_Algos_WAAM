"""Evaluate scheduler alone on fixed minor_2 geometry; export official validation."""
from __future__ import annotations
import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import shutil
import time
import bootstrap
from stable_baselines3 import PPO
from scheduler_env import SchedulerEnv,metrics,pad
from planner import digest,dump
from validator_adapter import run_validation
from policy import SchedulerPolicy

def deposition_signature(rows):
    return Counter((r,*[round(float(x),4) for x in a[1:4]],*[round(float(x),4) for x in b[1:4]])
        for r,own in enumerate(rows) for a,b in zip(own,own[1:]) if a[4]=='D')

def read_rows(path):
    rows=[[],[],[]]
    with Path(path).open(newline='',encoding='utf-8-sig') as f:
        for p in csv.DictReader(f):rows[int(p['robot_id'])-1].append([float(p['time_s']),float(p['x_mm']),float(p['y_mm']),float(p['z_mm']),p['mode']])
    return rows

def gantt(rows,output,title):
    import importlib.util
    spec=importlib.util.spec_from_file_location('original_gantt',bootstrap.PROJECT/'tools/gantt.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    intervals={r+1:[(a[0],b[0],a[4]) for a,b in zip(own,own[1:])] for r,own in enumerate(rows)}
    module.figure_for_job(title,intervals,max(own[-1][0] for own in rows)).write_html(output,include_plotlyjs=True)

def evaluate(model,plans,output,device='cuda'):
    plans,output=Path(plans),Path(output)
    if output.exists():raise FileExistsError(output)
    output.mkdir(parents=True)
    manifest=json.loads((plans/'manifest.json').read_text(encoding='utf-8'))
    model_sha=None
    if isinstance(model,(str,Path)):
        model_path=Path(model)
        metadata=json.loads((model_path.parent/'training.json').read_text(encoding='utf-8-sig'))
        if metadata['frozen_model_sha256']!=manifest['model_sha256']:
            raise ValueError('Scheduler and plans use different frozen minor_2 weights')
        model_sha=digest(model_path);model=PPO.load(model_path,device=device)
    report=dict(schema='scheduler_evaluation_v2',frozen_model_sha256=manifest['model_sha256'],
                scheduler_model_sha256=model_sha,jobs=[])
    for job in manifest['jobs']:
        if not job['complete_shape']:raise ValueError('Official evaluation needs every layer; prepare with --layers-per-shape 0')
        paths=[plans/job['folder']/p for p in job['plans']]
        env=SchedulerEnv(paths); combined=None; elapsed=0.; traces=[];start=time.perf_counter()
        if env.observation_space!=model.observation_space or env.action_space!=model.action_space:
            raise ValueError('Scheduler checkpoint has a different action/observation schema')
        for index,path in enumerate(paths):
            obs,_=env.reset(seed=10042,options=dict(plan_index=index))
            done=False
            while not done:
                action,_=model.predict(obs,deterministic=True)
                obs,_,done,_,info=env.step(action)
            if info['failed']:raise RuntimeError(f'Scheduler deadlock: {job["id"]} {path.name}')
            if combined is None:combined=[[[0.,*home,'W']] for home in env.homes]
            for r,own in enumerate(env.rows):
                combined[r][-1][4]=own[0][4]
                combined[r].extend([[p[0]+elapsed,*p[1:]] for p in own[1:]])
            elapsed+=env.now
            traces.append(dict(layer=env.plan['layer_index'],**info,decisions=env.trace))
        baseline=read_rows(Path(job['baseline_evaluation_episode'])/'input/trajectory.csv')
        if deposition_signature(baseline)!=deposition_signature(combined):
            raise ValueError('Scheduler changed deposition geometry or robot assignment')
        folder=output/job['folder'];inp=folder/'input';inp.mkdir(parents=True)
        for name in ('config.yaml','target.stl'):shutil.copy2(plans/job['folder']/name,inp/name)
        with (inp/'trajectory.csv').open('w',newline='',encoding='utf-8') as f:
            w=csv.writer(f);w.writerow(['robot_id','time_s','x_mm','y_mm','z_mm','mode'])
            for r,own in enumerate(combined,1):w.writerows([[r,*p] for p in own])
        validation=run_validation(inp,folder/'validation')
        value=metrics(combined)
        record=dict(id=job['id'],**value,validator=validation.status,iou=float(validation.shape.iou),
                    baseline_makespan_s=job['baseline_makespan'],
                    makespan_reduction_pct=100*(1-value['makespan_s']/job['baseline_makespan']),
                    deposition_geometry_identical=True,wall_time_s=time.perf_counter()-start,
                    waits=sum(t['waits'] for t in traces),reordered_tasks=sum(t['reordered_tasks'] for t in traces),
                    blocked_checks=sum(t['blocked_checks'] for t in traces))
        dump(folder/'scheduler_trace.json',traces)
        dump(folder/'metrics.json',record)
        gantt(combined,folder/'gantt.html',f"scheduler {job['id']}")
        report['jobs'].append(record);dump(output/'evaluation.json',report)
        print(f"{job['id']}: {validation.status}, makespan={value['makespan_s']:.2f}s, change={record['makespan_reduction_pct']:+.2f}%, concurrent D={value['deposition_2plus_s']:.2f}s",flush=True)
    with (output/'summary.csv').open('w',newline='',encoding='utf-8-sig') as f:
        keys=['id','validator','baseline_makespan_s','makespan_s','makespan_reduction_pct','deposition_2plus_s','deposition_3_s','mean_deposition_utilization','waits','reordered_tasks','blocked_checks','wall_time_s']
        writer=csv.DictWriter(f,fieldnames=keys,extrasaction='ignore');writer.writeheader();writer.writerows(report['jobs'])
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model',type=Path,required=True);p.add_argument('--plans',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--device',default='cuda')
    a=p.parse_args();evaluate(a.model,a.plans,a.output,a.device)

