"""Real STL checks, plus exact interrupted-stroke resume conservation."""
import argparse
from pathlib import Path
import numpy as np
import torch
import bootstrap
from stable_baselines3 import PPO
from source import Source
from avoidance import resolve
from motion import collision,deposition_preserved,insert_detour,span

def main():
    p=argparse.ArgumentParser();p.add_argument('--folder',type=Path,required=True)
    p.add_argument('--model',type=Path,required=True);a=p.parse_args();torch.set_num_threads(2)
    import layer_assignment_env as legacy
    def forbidden(*args,**kwargs):raise AssertionError('IoU/full Validator must not run in minor3')
    for name in ('compute_shape_metrics','build_deposited_layers','run_validation','validate_trajectory_set'):
        setattr(legacy,name,forbidden)
    s=Source(a.folder,a.folder.name);m=PPO.load(a.model,device='cpu')
    action,_=m.predict(s.observe(0),deterministic=True)
    print('Source ready',s.name,'layers',len(s.layers),'action',action.tolist(),flush=True)
    env=resolve(s,0,action)
    print(env.info(),flush=True)
    assert not env.failed,env.info()
    assert collision(env.rows,s.config) is None
    assert deposition_preserved(env.original,env.rows)
    # A D interruption inserts T, W, T and resumes at exactly the same point.
    original=[[[0.,0.,0.,2.,'D'],[10.,80.,0.,2.,'W']]]
    changed,_,_=insert_detour(original[0],3.,[24.,300.,2.],2.,150.)
    assert deposition_preserved(original,[changed])
    broken=[list(p) for p in changed];broken[-1][1]=79.
    assert not deposition_preserved(original,[broken])
    total=sum(b[0]-a[0] for a,b in zip(changed,changed[1:]) if a[4]=='D')
    assert abs(total-10)<1e-6
    print('PASS: sampled collision-free, ordered D conserved, mid-stroke resume, missing D rejected',flush=True)

if __name__=='__main__':main()
