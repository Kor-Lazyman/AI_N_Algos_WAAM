"""Continuous ordered routes, sampled collision prediction, pause/detour/resume."""
import numpy as np
import bootstrap
from waam_validator.collision.geometry2d import check_arm_envelope_xy_batch

def span(rows):return max(own[-1][0] for own in rows)

def positions(own,times):
    stamps=np.asarray([p[0] for p in own],float)
    xyz=np.asarray([p[1:4] for p in own],np.float32).astype(float)
    if len(own)==1:return np.repeat(xyz,len(times),axis=0)
    idx=np.clip(np.searchsorted(stamps,times,side='right')-1,0,len(own)-2)
    f=np.clip((times-stamps[idx])/(stamps[idx+1]-stamps[idx]),0,1)
    return (xyz[idx]+f[:,None]*(xyz[idx+1]-xyz[idx])).astype(np.float32).astype(float)

def at_times(rows,cfg,times,pairs):
    xyz=[positions(own,times) for own in rows];hits=[]
    for a,b in pairs:
        ra,rb=cfg.robots[a],cfg.robots[b];c=cfg.collision
        hit=np.zeros(len(times),bool)
        if c.check_tcp_radius:
            d=np.linalg.norm(xyz[a][:,:2]-xyz[b][:,:2],axis=1)
            threshold=ra.tcp_radius_mm+rb.tcp_radius_mm
            hit|=d<=threshold if c.touching_is_collision else d<threshold
        if c.check_arm_envelope:
            hit|=check_arm_envelope_xy_batch(np.asarray(ra.base_xyz_mm[:2]),xyz[a][:,:2],ra.arm_envelope_radius_mm,
                np.asarray(rb.base_xyz_mm[:2]),xyz[b][:,:2],rb.arm_envelope_radius_mm,
                c.arm_clearance_mm,c.geometry_epsilon_mm,c.touching_is_collision).collision
        if hit.any():
            k=int(np.flatnonzero(hit)[0]);hits.append(dict(time=float(times[k]),pair=[a,b],
                points=[xyz[a][k].tolist(),xyz[b][k].tolist()]))
    return min(hits,key=lambda h:h['time']) if hits else None

def collision(rows,cfg,start=0.,end=None,pairs=None,quick=False):
    """Same time/displacement spacing and geometry as bundled collision model.

    No IoU, shape metrics, validator status, or full Validator invocation.
    Quick midpoint probes may reject; acceptance always uses dense samples.
    """
    pairs=pairs or [(0,1),(0,2),(1,2)]
    end=span(rows) if end is None else end
    if end<start:return None
    knots=np.asarray(sorted({start,end,*[p[0] for own in rows for p in own if start<p[0]<end]}))
    if len(knots)==1:return at_times(rows,cfg,knots,pairs)
    if quick:
        return at_times(rows,cfg,np.unique(np.r_[knots,(knots[:-1]+knots[1:])/2]),pairs)
    xyz=np.stack([positions(own,knots) for own in rows],axis=1)
    movement=np.linalg.norm(np.diff(xyz,axis=0),axis=2).max(axis=1)
    counts=np.maximum(1,np.maximum(np.ceil(np.diff(knots)/cfg.simulation.max_time_step_s),
                                  np.ceil(movement/cfg.simulation.max_tcp_step_mm))).astype(int)
    times=np.concatenate([l+(r-l)*np.arange(n)/n for l,r,n in zip(knots[:-1],knots[1:],counts)]+[knots[-1:]])
    return at_times(rows,cfg,times,pairs)

def cut(own,t):
    """Split a timestamp, NOT a task/robot assignment; resume same stroke."""
    t=float(t);point=positions(own,np.array([t]))[0].tolist()
    idx=max(0,int(np.searchsorted([p[0] for p in own],t,side='right')-1))
    mode=own[idx][4] if idx<len(own)-1 else 'W'
    prefix=[list(p) for p in own if p[0]<t-1e-8]
    prefix.append([t,*point,'W'])
    tail=[[t,*point,mode],*[list(p) for p in own if p[0]>t+1e-8]]
    return prefix,tail

def insert_detour(own,pause,point,hold,speed):
    prefix,tail=cut(own,pause);start=np.asarray(prefix[-1][1:4])
    point=np.asarray(point,np.float32).astype(float)
    travel=float(np.linalg.norm(point-start))/speed
    now=pause
    if travel>1e-8:
        prefix[-1][4]='T';now+=travel;prefix.append([now,*point,'W'])
    if hold>1e-8:
        now+=hold;prefix.append([now,*prefix[-1][1:4],'W'])
    if travel>1e-8:
        prefix[-1][4]='T';now+=travel;prefix.append([now,*start,'W'])
    prefix[-1][4]=tail[0][4]
    offset=now-pause
    prefix.extend([[p[0]+offset,*p[1:]] for p in tail[1:]])
    return prefix,now,offset

def deposition_preserved(original,actual,tol=0.001):
    """Each original stroke must be covered once, in order, after interruptions."""
    for old,new in zip(original,actual):
        expected=[(np.asarray(a[1:4]),np.asarray(b[1:4])) for a,b in zip(old,old[1:]) if a[4]=='D']
        idx=0;cursor=expected[0][0] if expected else None
        for a,b in zip(new,new[1:]):
            if a[4]!='D':continue
            if idx>=len(expected):return False
            start,end=expected[idx];p,q=np.asarray(a[1:4]),np.asarray(b[1:4])
            if np.linalg.norm(p-cursor)>tol:return False
            v=end-start;length=np.dot(v,v);u=float(np.dot(q-start,v)/length)
            if not -tol<=u<=1+tol or np.linalg.norm(q-(start+np.clip(u,0,1)*v))>tol:return False
            if np.dot(q-p,v)<-tol:return False
            if np.linalg.norm(q-end)<=tol:
                idx+=1;cursor=expected[idx][0] if idx<len(expected) else None
            else:cursor=q
        if idx!=len(expected):return False
    return True

def metrics(rows):
    end=span(rows);robots=[]
    for r,own in enumerate(rows):
        t={m:sum(b[0]-a[0] for a,b in zip(own,own[1:]) if a[4]==m) for m in 'TDW'}
        t['W']+=end-own[-1][0]
        robots.append(dict(robot=r+1,**t,D_util=t['D']/max(end,1e-9)))
    return dict(makespan_s=end,robots=robots)
