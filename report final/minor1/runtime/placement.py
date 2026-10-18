"""One XY translation per STL, applied to the full mesh before slicing.

Placement PPO has a separate Box(2) policy. During its update, the layer policy
is held fixed and runs one complete STL episode. Only that episode's layer
rewards are averaged into the placement transition. Layer training uses the
current placement policy deterministically and freezes placement for all layers.
"""
from __future__ import annotations
import json
import hashlib
from pathlib import Path
import shutil
import tempfile

import gymnasium as gym
from gymnasium import spaces
import numpy as np
from shapely import MultiPoint
from stable_baselines3.common.callbacks import BaseCallback

from validator_adapter import load_config
from waam_validator.shape.target import load_target_mesh
from layer_assignment_env import LayerPathEnv
from rewards import placement_reward

PLACEMENT_SCHEMA = 'stl_global_xy_v1'


def record_model_pair(layer_path, placement_path):
    layer_path, placement_path = Path(layer_path), Path(placement_path)
    record = dict(placement_schema=PLACEMENT_SCHEMA, layer_file=layer_path.name,
                  placement_file=placement_path.name,
                  layer_sha256=hashlib.sha256(layer_path.read_bytes()).hexdigest(),
                  placement_sha256=hashlib.sha256(placement_path.read_bytes()).hexdigest())
    path = layer_path.with_suffix('.pair.json')
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(record, indent=2), encoding='utf-8')
    temporary.replace(path)


def save_model_pair(layer, placement, layer_path, placement_path):
    layer.save(layer_path)
    if placement is not None:
        placement.save(placement_path)
        record_model_pair(Path(layer_path).with_suffix('.zip'), Path(placement_path).with_suffix('.zip'))


class PlacementSpec:
    def __init__(self, scenario):
        self.scenario = Path(scenario).resolve()
        self.config = load_config(self.scenario / 'config.yaml')
        self.mesh = load_target_mesh(self.scenario / 'target.stl', self.config)
        self.radius = float(self.config.workspace.radius_mm)
        self.center = np.asarray(self.config.workspace.center_xy_mm, dtype=float)
        hull = MultiPoint(np.asarray(self.mesh.vertices)[:, :2]).convex_hull
        self.hull = np.asarray(hull.exterior.coords, dtype=float)
        scale = max(1., self.radius)
        features = [*(self.mesh.bounds.flatten()/scale), *(self.mesh.extents/scale),
                    *(self.mesh.bounds.mean(axis=0)/scale), self.mesh.volume/scale**3,
                    self.mesh.area/scale**2, *(self.center/scale), self.radius/scale]
        for robot in sorted(self.config.robots, key=lambda robot: robot.id):
            home = robot.home_xyz_mm if robot.home_xyz_mm is not None else robot.base_xyz_mm
            features.extend([*(np.asarray(robot.base_xyz_mm)[:2]/scale), *(np.asarray(home)[:2]/scale),
                             robot.xy_reach_radius_mm/scale, robot.arm_envelope_radius_mm/scale,
                             robot.tcp_radius_mm/scale])
        p = self.config.process
        features.extend([p.bead_width_mm/scale, p.layer_height_mm/scale,
                         p.travel_speed_mm_s/scale, p.deposition_speed_mm_s/scale])
        self.observation = np.asarray(features, dtype=np.float32)

    def translation(self, action):
        action = np.asarray(action, dtype=float)
        if action.shape != (2,) or not np.isfinite(action).all():
            raise ValueError('Placement action must be two finite XY coordinates')
        delta = np.clip(action, -1., 1.)*self.radius
        distance_sq = float(np.dot(delta, delta))
        if distance_sq < 1e-12:
            return np.zeros(2)
        # A circle is convex: checking hull vertices keeps the whole target inside.
        # Project the entire requested displacement, never individual vertices.
        p = self.hull-self.center
        b = 2*p.dot(delta)
        c = np.sum(p*p, axis=1)-self.radius**2
        roots = (-b+np.sqrt(np.maximum(0., b*b-4*distance_sq*c)))/(2*distance_sq)
        factor = max(0., min(1., float(roots.min())))
        if factor < 1.:
            factor = max(0., factor-0.002/max(np.sqrt(distance_sq), 1e-9))
        return delta*factor

    def write_job(self, action, directory):
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        delta = self.translation(action)
        mesh = self.mesh.copy()
        mesh.apply_translation([*delta, 0.])
        if np.any(delta):
            mesh.export(directory / 'target.stl')
        else:
            shutil.copyfile(self.scenario / 'target.stl', directory / 'target.stl')
        shutil.copyfile(self.scenario / 'config.yaml', directory / 'config.yaml')
        metadata = dict(schema=PLACEMENT_SCHEMA, source=str(self.scenario), action=np.asarray(action).tolist(),
                        translation_xyz_mm=[float(delta[0]), float(delta[1]), 0.],
                        application='whole_mesh_before_slicing', same_translation_for_every_layer=True)
        (directory / 'placement.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
        return metadata


class PlacedLayerEnv(gym.Env):
    """Layer environment with one frozen placement decision at each reset."""
    def __init__(self, scenario, placement_policy, *, reward_weights=None):
        super().__init__()
        self.scenario = Path(scenario).resolve()
        self.spec = PlacementSpec(scenario)
        self.placement_policy = placement_policy
        self.reward_weights = reward_weights
        self._temporary = tempfile.TemporaryDirectory(prefix='waam_minor_placed_')
        self.env = LayerPathEnv(scenario, reward_weights=reward_weights)
        self.observation_space, self.action_space = self.env.observation_space, self.env.action_space

    def __getattr__(self, name):
        env = self.__dict__.get('env')
        if env is None:
            raise AttributeError(name)
        return getattr(env, name)

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        action, _ = self.placement_policy.predict(self.spec.observation, deterministic=True)
        self.spec.write_job(action, self._temporary.name)
        self.env.close()
        self.env = LayerPathEnv(self._temporary.name, reward_weights=self.reward_weights)
        if 'evaluate_output' in vars(self):
            self.env.evaluate_output = self.evaluate_output
        return self.env.reset(seed=seed, options=options)

    def step(self, action):
        return self.env.step(action)

    def close(self):
        self.env.close()
        self._temporary.cleanup()


class PlacementEnv(gym.Env):
    """Each transition evaluates one STL with one translation and one terminal reward."""
    def __init__(self, scenarios, *, reward_weights=None):
        super().__init__()
        self.specs = [PlacementSpec(path) for path in scenarios]
        self.reward_weights = reward_weights
        self.action_space = spaces.Box(-1., 1., (2,), dtype=np.float32)
        self.observation_space = spaces.Box(-np.inf, np.inf, self.specs[0].observation.shape, dtype=np.float32)
        if any(spec.observation.shape != self.observation_space.shape for spec in self.specs):
            raise ValueError('Inconsistent placement observations')
        self.layer_policy = None
        self._cycle = []
        self.active = None
        self.done = True

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        if seed is not None:
            self._cycle = []
        if not self._cycle:
            self._cycle = list(self.np_random.permutation(len(self.specs)))
        self.active = int(self._cycle.pop())
        self.done = False
        spec = self.specs[self.active]
        return spec.observation.copy(), dict(scenario_id=spec.scenario.name)

    def step(self, action):
        if self.done or self.layer_policy is None:
            raise RuntimeError('Reset and attach the layer policy before placement learning')
        spec = self.specs[self.active]
        layer_rewards, metrics = [], []
        with tempfile.TemporaryDirectory(prefix='waam_minor_placement_') as directory:
            placement = spec.write_job(action, directory)
            env = LayerPathEnv(directory, reward_weights=self.reward_weights)
            try:
                observation, info = env.reset(seed=int(self.np_random.integers(2**31)))
                while not env.done:
                    layer_action, _ = self.layer_policy.predict(observation, deterministic=True)
                    observation, reward, _, _, info = env.step(layer_action)
                    layer_rewards.append(float(reward))
                    metrics.append(info)
            finally:
                env.close()
        reward = placement_reward(layer_rewards)
        self.done = True
        result = dict(scenario_id=spec.scenario.name, placement=placement,
                      layer_rewards=layer_rewards, reward_mean_same_stl=reward,
                      layers_evaluated=len(layer_rewards), schedule_complete=info['schedule_complete'],
                      terminal_status=info.get('terminal_status'), makespan_s=info['makespan_s'], iou=info['iou'],
                      mean_deposition_utilization=float(np.mean([item.get('mean_deposition_utilization', 0.) for item in metrics])),
                      deposition_2plus_s=sum(item.get('deposition_2plus_s', 0.) for item in metrics))
        return spec.observation.copy(), reward, True, False, result


class PlacementProgressCallback(BaseCallback):
    def __init__(self, trace):
        super().__init__()
        self.trace = Path(trace)

    def _on_step(self):
        for info in self.locals['infos']:
            record = dict(info, placement_step=self.num_timesteps)
            for key in ('reward_mean_same_stl', 'makespan_s', 'iou', 'mean_deposition_utilization', 'deposition_2plus_s'):
                self.logger.record_mean('placement/'+key, float(info[key]))
            with self.trace.open('a', encoding='utf-8') as stream:
                stream.write(json.dumps(record, ensure_ascii=False,
                    default=lambda value: value.tolist() if isinstance(value, np.ndarray) else value.item())+'\n')
            print(f"Placement step {self.num_timesteps}: {info['scenario_id']}, "
                  f"XY={info['placement']['translation_xyz_mm'][:2]}, "
                  f"reward={info['reward_mean_same_stl']:.6f}", flush=True)
        return True
