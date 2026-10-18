"""STL slicing and original whole-layer action space, without IoU evaluation."""
import json
import hashlib
from pathlib import Path
import numpy as np
import gymnasium as gym
import bootstrap
from layer_assignment_env import (LayerPathEnv,generate_layer_segments,ACTION_NVECS,ROBOT_ORDERS,
    load_target_mesh,slice_target_layers,determine_evaluation_layers,normalize_polygon)
from validator_adapter import load_config

class Source:
    # Reuse pure path/observation helpers, not legacy reset/step/validation.
    _raster=LayerPathEnv._raster;_observation=LayerPathEnv._observation
    _partition=LayerPathEnv._partition;_move=LayerPathEnv._move
    _local_rows=LayerPathEnv._local_rows;_z=LayerPathEnv._z
    reachable_robots=LayerPathEnv.reachable_robots
    def __init__(self,folder,name):
        self.scenario=Path(folder);self.name=name;self.config=load_config(self.scenario/'config.yaml')
        self.mesh=load_target_mesh(self.scenario/'target.stl',self.config)
        raw=slice_target_layers(self.mesh,determine_evaluation_layers(self.mesh,{},self.config),self.config)
        s=self.config.shape_validation
        self.layers=[(k,normalize_polygon(v,s.polygon_snap_tolerance_mm,s.area_epsilon_mm2))
            for k,v in sorted(raw.items()) if not v.is_empty and v.area>s.area_epsilon_mm2]
        self.robots=sorted(self.config.robots,key=lambda r:r.id)
        self.homes=np.asarray([r.home_xyz_mm for r in self.robots],np.float32).astype(float)
        self.bases=np.asarray([r.base_xyz_mm for r in self.robots],float)
        self.coord_scale=max(1.,float(np.abs(self.mesh.bounds).max()),float(np.abs(self.homes).max()),float(np.abs(self.bases).max()))
        self._raster_cache={};self.current_iou=self.last_layer_iou=0.
        self.makespan=self.last_duration=0.;self.last_robot_counts=[0]*3;self.index=0
    def observe(self,index):
        self.index=index
        obs=self._observation();obs[2:4]=0.;obs[-5:]=0.
        return obs
    def generate(self,index,action):
        self.index=index;layer,target=self.layers[index]
        # Preserve natural contour/hatch strokes; no 80/160 mm task chunks.
        segments=generate_layer_segments(target,self.config.process.bead_width_mm,
            self.config.shape_validation.polygon_buffer_resolution,action,max_segment_mm=1e12)
        groups,_=self._partition(segments,action)
        if groups is None:raise ValueError('Unreachable deposition')
        rows,_=self._local_rows(groups,self._z(layer),False,ROBOT_ORDERS[int(action[6])])
        for own in rows:
            while len(own)>1 and own[-2][4]=='W':own.pop()
        return rows
    def reference(self,index):
        layer,target=self.layers[index];p=self.config.process
        center=np.array([target.centroid.x,target.centroid.y,self._z(layer)])
        return max(1.,target.area/(p.bead_width_mm*p.deposition_speed_mm_s)
                   +sum(2*np.linalg.norm(h-center)/p.travel_speed_mm_s for h in self.homes))

def dataset(manifest_path,all_layers=False):
    root=Path(manifest_path);meta=json.loads((root/'manifest.json').read_text(encoding='utf-8'));pool=[];jobs=[]
    for job in meta['jobs']:
        for name in ('target.stl','config.yaml'):
            if hashlib.sha256((root/job['folder']/name).read_bytes()).hexdigest()!=job['input_sha256'][name]:
                raise ValueError(f'Input changed: {job["id"]}/{name}')
        print(f"Slicing {job['id']} ...",flush=True)
        source=Source(root/job['folder'],job['id'])
        indices=list(range(len(source.layers))) if all_layers else [json.loads((root/job['folder']/p).read_text())['layer_index'] for p in job['plans']]
        pool.extend((source,i) for i in indices);jobs.append((source,indices,job))
    return pool,jobs,meta
