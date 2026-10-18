"""Whole-STL timing and collision checks. No IoU or full Validator run."""
import argparse
import csv
import importlib.util
import json
import shutil
import time
from pathlib import Path
import torch
import bootstrap
from stable_baselines3 import PPO
from source import dataset
from avoidance import resolve
from motion import span,metrics,collision,deposition_preserved
from runtime import dump
from policy import AvoidancePolicy

def evaluate(path_model,avoid_model,jobs,output):
    output=Path(output);output.mkdir(parents=True,exist_ok=False);report=[]
    for number,(source,indices,baseline) in enumerate(jobs):
        begin=time.perf_counter();combined=[[[0.,*h,'W']] for h in source.homes];elapsed=0.;traces=[];failed=False
        for index in indices:
            action,_=path_model.predict(source.observe(index),deterministic=True)
            env=resolve(source,index,action,avoid_model)
            traces.append(dict(**env.info(),decisions=env.trace))
            if env.failed:failed=True;break
            assert deposition_preserved(env.original,env.rows)
            end=span(env.rows)
            for r,own in enumerate(env.rows):
                own=[list(p) for p in own]
                if own[-1][0]<end:own.append([end,*own[-1][1:4],'W'])
                combined[r][-1][4]=own[0][4]
                combined[r].extend([[p[0]+elapsed,*p[1:]] for p in own[1:]])
            elapsed+=end
        folder=output/f'job_{number:02d}';folder.mkdir()
        dump(folder/'repair_trace.json',traces)
        record=dict(id=source.name,complete=not failed,collision_free=not failed,
            validator_run=False,iou_computed=False,baseline_minor2_s=baseline['baseline_makespan'],
            completed_layers=len(traces)-int(failed),total_layers=len(indices),wall_time_s=time.perf_counter()-begin,
            repairs=sum(t['repairs'] for t in traces),interrupted_D=sum(t['interrupted_D'] for t in traces),
            detour_distance_mm=sum(t['detour_distance_mm'] for t in traces))
        if not failed:
            assert collision(combined,source.config) is None
            record.update(metrics(combined))
            inp=folder/'input';inp.mkdir()
            for name in ('target.stl','config.yaml'):shutil.copy2(source.scenario/name,inp/name)
            with (inp/'trajectory.csv').open('w',newline='',encoding='utf-8') as f:
                writer=csv.writer(f);writer.writerow(['robot_id','time_s','x_mm','y_mm','z_mm','mode'])
                for r,own in enumerate(combined,1):writer.writerows([[r,*p] for p in own])
            spec=importlib.util.spec_from_file_location('gantt_tool',bootstrap.PROJECT/'tools/gantt.py')
            tool=importlib.util.module_from_spec(spec);spec.loader.exec_module(tool)
            intervals={r+1:[(a[0],b[0],a[4]) for a,b in zip(own,own[1:])] for r,own in enumerate(combined)}
            tool.figure_for_job('minor3 '+source.name,intervals,elapsed).write_html(folder/'gantt.html',include_plotlyjs=True)
        else:
            record.update(makespan_s=None,failure_reason=env.failure_reason)
        dump(folder/'metrics.json',record);report.append(record);dump(output/'evaluation.json',report)
        print(f"{source.name}: complete={not failed}, makespan={record['makespan_s']}, repairs={record['repairs']}",flush=True)
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--plans',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--device',default='cuda');a=p.parse_args();torch.set_num_threads(2)
    _,jobs,_=dataset(a.plans,all_layers=True)
    evaluate(PPO.load(a.run/'path_final.zip',device=a.device),PPO.load(a.run/'avoidance_final.zip',device=a.device),jobs,a.output)

