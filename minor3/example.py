"""Export a single training layer replay to inspect pause/retreat/resume coordinates."""
import argparse
import csv
import json
from pathlib import Path
import numpy as np
import torch
import plotly.graph_objects as go
import bootstrap
from stable_baselines3 import PPO
from source import Source
from avoidance import resolve
from policy import AvoidancePolicy
from motion import deposition_preserved
from runtime import dump

def main():
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--plans',type=Path,required=True)
    p.add_argument('--shape',default='05');p.add_argument('--layer',type=int,default=174);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--device',default='cuda');a=p.parse_args();torch.set_num_threads(2)
    manifest=json.loads((a.plans/'manifest.json').read_text(encoding='utf-8'))
    job=next(j for j in manifest['jobs'] if j['id']==a.shape)
    source=Source(a.plans/job['folder'],a.shape)
    path=PPO.load(a.run/'path_final.zip',device=a.device);avoid=PPO.load(a.run/'avoidance_final.zip',device=a.device)
    action,_=path.predict(source.observe(a.layer),deterministic=True);env=resolve(source,a.layer,action,avoid)
    assert deposition_preserved(env.original,env.rows)
    a.output.mkdir(parents=True,exist_ok=False)
    dump(a.output/'details.json',dict(scope='single training layer; not a complete STL or holdout result',
        **env.info(),complete=not env.failed,completed_makespan_s=None if env.failed else env.info()['makespan_s'],
        decisions=env.trace,validator_run=False,iou_computed=False))
    # A failed repair is a diagnostic partial plan, never an executable trajectory.
    filename='partial_plan_UNRESOLVED.csv' if env.failed else 'trajectory.csv'
    with (a.output/filename).open('w',newline='',encoding='utf-8') as f:
        w=csv.writer(f);w.writerow(['robot_id','time_s','x_mm','y_mm','z_mm','mode'])
        for r,own in enumerate(env.rows,1):w.writerows([[r,*p] for p in own])
    fig=go.Figure();colors=['#2484e8','#ed7734','#1ba784']
    for r,own in enumerate(env.rows):
        for mode in ('D','T'):
            x=[];y=[];hover=[]
            for first,last in zip(own,own[1:]):
                if first[4]!=mode:continue
                x.extend([first[1],last[1],None]);y.extend([first[2],last[2],None])
                hover.extend([f'R{r+1} {mode} {first[0]:.2f}s',f'R{r+1} {mode} {last[0]:.2f}s',None])
            fig.add_trace(go.Scatter(x=x,y=y,mode='lines',name=f'R{r+1} {mode}',text=hover,hoverinfo='text',
                line=dict(color=colors[r],width=3 if mode=='D' else 1,dash='solid' if mode=='D' else 'dot')))
    for i,t in enumerate(env.trace):
        p,q=t['pause_xyz'],t['waypoint']
        fig.add_trace(go.Scatter(x=[p[0],q[0]],y=[p[1],q[1]],mode='lines+markers',
            name=f"repair {i+1}: R{t['robot']+1} ({t['mode']})",line=dict(color='#bd2165',width=4),
            marker=dict(size=11,symbol=['circle','diamond']),
            text=[f"pause {t['pause']:.2f}s; resume {t['resume']:.2f}s",f"waypoint; hold {t['hold']:.2f}s"],hoverinfo='text'))
    status='UNRESOLVED collision: diagnostic only' if env.failed else 'collision-free under sampled model'
    fig.update_layout(title=f'minor3 {a.shape} layer {a.layer}: {status}<br>pause → retreat → resume',
                      xaxis_title='X (mm)',yaxis_title='Y (mm)',yaxis=dict(scaleanchor='x',scaleratio=1),height=850)
    fig.write_html(a.output/'xy_detours.html',include_plotlyjs=True)
    print(json.dumps(env.info(),default=lambda x:x.item() if isinstance(x,np.generic) else str(x)),flush=True)

if __name__=='__main__':main()
