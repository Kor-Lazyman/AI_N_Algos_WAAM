"""Beta: one continuous action directly generates a complete layer.

Slicing fixes nearest-reachable-base territories. The policy supplies XY
strokes for each territory; the scheduler searches alternative safe tasks
when another robot is busy. The original Validator remains the final check.
"""
from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path
import shutil
import tempfile

import gymnasium as gym
from gymnasium import spaces
import numpy as np
from shapely import LineString, box
from shapely.affinity import rotate

from validator_adapter import load_config, run_validation, parts, trajectory_from_rows
from waam_validator.collision.simulator import run_collision_analysis
from waam_validator.errors import WaamValidatorError
from waam_validator.shape.deposition import build_deposited_layers
from waam_validator.shape.metrics import compute_shape_metrics
from waam_validator.shape.polygon_utils import normalize_polygon
from waam_validator.shape.target import determine_evaluation_layers, load_target_mesh, slice_target_layers
from waam_validator.trajectory.validator import validate_trajectory_set

VERSION = "Beta"
ENVIRONMENT_SCHEMA = "territory_direct_layer_v1"
SPACING_FACTORS = (0.8, 0.9, 1.0)
from territory import (ACTION_DESCRIPTION, ACTION_SIZE, MAX_STROKES, partition_layer, direct_groups)
from scheduler import schedule_layer
from shapely.geometry import mapping



@dataclass(frozen=True)
class LayerRewardWeights:
    iou: float = 1.0
    time: float = 0.1
    invalid: float = 2.0
    completion: float = 1.0
    validation_failure: float = 1.0

    def __post_init__(self):
        if any(not math.isfinite(v) or v < 0 for v in asdict(self).values()):
            raise ValueError("Reward weights must be finite and nonnegative")


def robot_layer_utilization(rows, duration):
    """Fraction of each robot's layer makespan spent travelling or depositing.

    A row's mode applies until the next row. W intervals, including the final
    barrier wait, are idle. All three robots share the same layer makespan.
    """
    if duration <= 0:
        return [0.0 for _ in rows]
    return [min(1.0, max(0.0, sum(
        max(0.0, next_row[0] - row[0]) for row, next_row in zip(own, own[1:])
        if row[4] in ("T", "D")) / duration)) for own in rows]


def generate_layer_segments(target, beadwidth, resolution, action, max_segment_mm=80.0):
    """Reference/demo helper only; the Beta policy itself outputs XY strokes."""
    angle = int(action[0]) * 22.5
    spacing = beadwidth * SPACING_FACTORS[int(action[1])]
    origin = (0.0, 0.0)
    rotated = rotate(target, -angle, origin=origin)
    inset = rotated.buffer(-0.49 * beadwidth, quad_segs=resolution)
    if inset.is_empty:
        raise ValueError("No printable inset at the configured bead width")
    lines = []
    for polygon in parts(inset, "Polygon"):
        polygon = polygon.simplify(beadwidth * 0.01, preserve_topology=True)
        lines.extend([LineString(polygon.exterior.coords),
                      *(LineString(ring.coords) for ring in polygon.interiors)])
        xmin, ymin, xmax, ymax = polygon.bounds
        count = max(1, math.ceil((ymax-ymin) / spacing))
        for row, y in enumerate(np.linspace(ymin, ymax, count+1)):
            clipped = polygon.intersection(LineString([(xmin-beadwidth, y), (xmax+beadwidth, y)]))
            for line in parts(clipped, "LineString"):
                lines.append(LineString(list(line.coords)[::-1]) if row % 2 else line)
    segments = []
    for line in lines:
        coords = list(rotate(line, angle, origin=origin).coords)
        for start, end in zip(coords, coords[1:]):
            a, b = np.asarray(start[:2]), np.asarray(end[:2])
            distance = float(np.linalg.norm(b-a))
            if distance <= 1e-5:
                continue
            count = max(1, math.ceil(distance / max_segment_mm))
            for i in range(count):
                # Match official CSV loading precision before reach/timing checks.
                p, q = (np.asarray(a+(b-a)*t/count, dtype=np.float32).astype(float)
                        for t in (i, i+1))
                if np.linalg.norm(q-p) > 1e-5:
                    segments.append((tuple(p), tuple(q)))
    if not segments:
        raise ValueError("Layer generated no deposition segments")
    xmin, ymin, xmax, ymax = target.bounds
    corner = int(action[2])
    anchor = np.asarray((xmax if corner & 1 else xmin, ymax if corner & 2 else ymin))
    start = min(range(len(segments)), key=lambda i: (np.linalg.norm(np.asarray(segments[i][0])-anchor), i))
    segments = segments[start:] + segments[:start]
    if int(action[3]):
        segments = [(b, a) for a, b in reversed(segments)]
    return segments


class LayerPathEnv(gym.Env):
    metadata = {"render_modes": []}

    def __init__(self, scenario, *, reward_weights=None):
        super().__init__()
        self.scenario = Path(scenario).resolve()
        self.config = load_config(self.scenario / "config.yaml")
        self.reward_weights = reward_weights or LayerRewardWeights()
        self.mesh = load_target_mesh(self.scenario / "target.stl", self.config)
        raw = slice_target_layers(self.mesh, determine_evaluation_layers(self.mesh, {}, self.config), self.config)
        s = self.config.shape_validation
        self.layers = [(k, normalize_polygon(v, s.polygon_snap_tolerance_mm, s.area_epsilon_mm2))
                       for k, v in sorted(raw.items()) if not v.is_empty and v.area > s.area_epsilon_mm2]
        if not self.layers:
            raise ValueError("STL has no printable layers")
        self.target_layers = dict(self.layers)
        self.total_target_area = sum(g.area for _, g in self.layers)
        self.robots = sorted(self.config.robots, key=lambda r: r.id)
        self.homes = np.asarray([r.home_xyz_mm if r.home_xyz_mm is not None else r.base_xyz_mm
                                 for r in self.robots], dtype=np.float32).astype(float)
        self.bases = np.asarray([r.base_xyz_mm for r in self.robots], dtype=float)
        # STL slicing is followed immediately by immutable territorial ownership.
        self.territories, self.uncovered_areas = {}, {}
        partition_cache = {}
        for layer, target in self.layers:
            if target.wkb not in partition_cache:
                partition_cache[target.wkb] = partition_layer(target, self.robots)
            self.territories[layer], self.uncovered_areas[layer] = partition_cache[target.wkb]
        self._territory_raster_cache = {}
        self.coord_scale = max(1.0, float(np.abs(self.mesh.bounds).max()), float(np.abs(self.homes).max()),
                               float(np.abs(self.bases).max()))
        self.action_space = spaces.Box(-1.0, 1.0, shape=(ACTION_SIZE,), dtype=np.float32)
        self._raster_cache = {}
        self.reset()
        self.observation_space = spaces.Box(-np.inf, np.inf, shape=self._observation().shape, dtype=np.float32)
        parked = self._trajectory([[list(row), [1e-6, *row[1:]]] for row in [s[0] for s in self.rows]])
        if validate_trajectory_set(parked, self.config).violations or run_collision_analysis(parked, self.config).events:
            raise ValueError("Initial home positions violate reach/collision constraints")

    _trajectory = staticmethod(trajectory_from_rows)

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        self.rows = [[[0.0, *home, "W"]] for home in self.homes]
        self.index = 0
        self.done = False
        self.makespan = 0.0
        self.current_iou = 0.0
        self.last_layer_iou = 0.0
        self.last_duration = 0.0
        self.last_robot_counts = [0, 0, 0]
        self.deposited_area = self.intersection_area = 0.0
        self.layer_history = []
        self.terminal_validation = None
        self.terminal_validation_artifacts = None
        return self._observation(), self._info()

    def _raster(self, target):
        key = target.wkb
        if key not in self._raster_cache:
            xmin, ymin, xmax, ymax = target.bounds
            dx, dy = (xmax-xmin)/16, (ymax-ymin)/16
            self._raster_cache[key] = [target.intersection(box(xmin+x*dx, ymin+y*dy,
                                                             xmin+(x+1)*dx, ymin+(y+1)*dy)).area/(dx*dy)
                                       for y in range(16) for x in range(16)]
        return self._raster_cache[key]

    def _observation(self):
        features = [self.index/len(self.layers), math.log1p(len(self.layers))/10,
                    self.current_iou, self.last_layer_iou, math.log1p(self.makespan)/20,
                    math.log1p(self.last_duration)/20,
                    *(math.log1p(v)/10 for v in self.last_robot_counts)]
        if self.index < len(self.layers):
            layer, target = self.layers[self.index]
            features.extend([self._z(layer)/self.coord_scale, *(v/self.coord_scale for v in target.bounds),
                             target.area/self.coord_scale**2, target.length/self.coord_scale])
            features.extend(self._raster(target))
        else:
            features.extend([0.0]*(7+256))
        for r, robot in enumerate(self.robots):
            features.extend([*(self.bases[r]/self.coord_scale), *(self.homes[r]/self.coord_scale),
                             robot.xy_reach_radius_mm/self.coord_scale,
                             robot.arm_envelope_radius_mm/self.coord_scale,
                             robot.tcp_radius_mm/self.coord_scale])
        p, s = self.config.process, self.config.shape_validation
        features.extend([p.bead_width_mm/self.coord_scale, p.layer_height_mm/self.coord_scale,
                         p.travel_speed_mm_s/self.coord_scale, p.deposition_speed_mm_s/self.coord_scale,
                         self.config.collision.arm_clearance_mm/self.coord_scale,
                         s.minimum_overall_coverage, s.maximum_overall_overfill_ratio,
                         s.minimum_overall_iou, s.minimum_layer_iou, s.maximum_failed_layer_ratio])
        # All ownership masks use the SAME layer bounds, so the network sees
        # where its three sets of coordinate outputs are allowed to deposit.
        if self.index < len(self.layers):
            layer, target = self.layers[self.index]
            if target.wkb not in self._territory_raster_cache:
                xmin, ymin, xmax, ymax = target.bounds
                dx, dy = (xmax-xmin)/16, (ymax-ymin)/16
                masks = [region.intersection(box(xmin+x*dx, ymin+y*dy,
                         xmin+(x+1)*dx, ymin+(y+1)*dy)).area/(dx*dy)
                         for region in self.territories[layer] for y in range(16) for x in range(16)]
                self._territory_raster_cache[target.wkb] = masks + [g.area/target.area for g in self.territories[layer]]
            features.extend(self._territory_raster_cache[target.wkb])
        else:
            features.extend([0.0] * (3*256+3))
        return np.asarray(features, dtype=np.float32)

    def _z(self, layer):
        p = self.config.process
        return float(np.float32(p.build_plane_z_mm+(layer+(1 if p.tcp_z_reference == "top" else 0.5))*p.layer_height_mm))

    def _info(self, **extra):
        return dict(version=VERSION, environment=ENVIRONMENT_SCHEMA, completed_layers=self.index,
                    total_layers=len(self.layers), schedule_complete=self.index == len(self.layers),
                    makespan_s=self.makespan, iou=self.current_iou, **extra)

    def _move(self, rows, point, mode):
        point = np.asarray(point, dtype=np.float32).astype(float)
        distance = float(np.linalg.norm(point-np.asarray(rows[-1][1:4])))
        if distance <= 1e-6:
            return
        speed = self.config.process.deposition_speed_mm_s if mode == "D" else self.config.process.travel_speed_mm_s
        rows[-1][4] = mode
        rows.append([rows[-1][0]+distance/speed, *point, "W"])

    def _local_rows(self, groups, z, serial, robot_order):
        rows = [[[0.0, *home, "W"]] for home in self.homes]
        barrier = 0.0
        for robot in robot_order:
            own = rows[robot]
            if not groups[robot]:
                continue
            if serial and barrier > 0:
                own.append([barrier, *self.homes[robot], "W"])
            for start, end in groups[robot]:
                self._move(own, (*start, z), "T")
                self._move(own, (*end, z), "D")
            self._move(own, self.homes[robot], "T")
            barrier = max(barrier, own[-1][0])
        for robot, own in enumerate(rows):
            if own[-1][0] < barrier:
                own.append([barrier, *self.homes[robot], "W"])
        return rows, barrier

    def _check_local(self, rows):
        trajectory = self._trajectory(rows)
        try:
            messages = validate_trajectory_set(trajectory, self.config)
        except WaamValidatorError as exc:
            return False, exc.code
        if messages.violations:
            return False, "trajectory_constraint"
        if run_collision_analysis(trajectory, self.config).events:
            return False, "collision"
        return True, None

    def _reject(self, reason, **extra):
        self.done = True
        return self._observation(), -self.reward_weights.invalid, True, False, self._info(
            failure_reason=reason, reward_iou=0.0, reward_time=0.0,
            reward_invalid=-self.reward_weights.invalid, reward_terminal=0.0, **extra)

    def step(self, action):
        if self.done:
            raise RuntimeError("Episode ended; call reset()")
        action = np.asarray(action, dtype=np.float32)
        if not self.action_space.contains(action):
            raise ValueError(f"Action must belong to {self.action_space}")
        layer, target = self.layers[self.index]
        if self.uncovered_areas[layer] > max(1e-6, target.area*1e-7):
            return self._reject("unreachable_target_area", unassigned_area_mm2=self.uncovered_areas[layer])
        groups = direct_groups(action, target, self.territories[layer], self.robots,
                              self.config.process.bead_width_mm,
                              self.config.shape_validation.polygon_buffer_resolution)
        segments = [segment for group in groups for segment in group]
        if not segments:
            return self._reject("empty_direct_path", layer_index=layer)
        # Ownership is fixed; another robot never steals a reachable boundary job.
        reassigned = 0
        rows, duration, schedule = schedule_layer(self, groups, self._z(layer))
        if rows is None:
            reason = schedule.pop("failure_reason")
            return self._reject(reason, **schedule)
        valid, reason = self._check_local(rows)
        serial_fallback = schedule["simultaneous_2plus_s"] <= 1e-9
        if not valid:
            return self._reject(reason, layer_index=layer, **schedule)
        # Compute this layer's geometry once. Never rebuild all past deposition.
        deposited = build_deposited_layers(self._trajectory(rows), self.config)
        metrics, layer_metrics = compute_shape_metrics(deposited, {layer: target}, self.config)
        lm = layer_metrics[0]
        self.deposited_area += lm.deposited_area_mm2
        self.intersection_area += lm.intersection_area_mm2
        self.current_iou = self.intersection_area/(self.total_target_area+self.deposited_area-self.intersection_area)
        offset = self.makespan
        for r, own in enumerate(rows):
            self.rows[r][-1][4] = own[0][4]
            self.rows[r].extend([[float(row[0]+offset), *row[1:]] for row in own[1:]])
        self.makespan += duration
        self.index += 1
        self.done = self.index == len(self.layers)
        self.last_layer_iou = float(metrics.iou)
        self.last_duration = duration
        self.last_robot_counts = [len(group) for group in groups]
        # Geometry-derived reference, independent of the chosen hatch/action.
        p = self.config.process
        center = np.asarray([target.centroid.x, target.centroid.y, self._z(layer)])
        reference = max(1.0, target.area/(p.bead_width_mm*p.deposition_speed_mm_s)
                        + sum(2*np.linalg.norm(home-center)/p.travel_speed_mm_s for home in self.homes))
        riou = self.reward_weights.iou*float(metrics.iou)
        utilizations = robot_layer_utilization(rows, duration)
        mean_utilization = sum(utilizations)/len(utilizations)
        idle_times = [duration*(1.0-utilization) for utilization in utilizations]
        # Three robots: one fully busy -> 3x, three fully busy -> 1x.
        # Partial work and serial schedules are charged for their actual W time.
        idle_factor = 1.0 + sum(idle_times)/duration
        rtime = -self.reward_weights.time*duration*idle_factor/reference
        rterminal = 0.0
        terminal_status = None
        terminal_error = None
        if self.done:
            # Final authority: full original inputs + whole generated trajectory.
            def validate_final(directory, persist_reports):
                job = self.export(Path(directory) / "input")
                try:
                    self.terminal_validation = run_validation(
                        job, Path(directory) / "validation" if persist_reports else None)
                    self.current_iou = float(self.terminal_validation.shape.iou)
                    return self.terminal_validation.status, None
                except WaamValidatorError as exc:
                    return "ERROR", f"{exc.code}: {exc.message}"
                finally:
                    if persist_reports:
                        self.terminal_validation_artifacts = dict(
                            output=str(Path(directory).resolve()),
                            input_sha256={name: hashlib.sha256((job/name).read_bytes()).hexdigest()
                                          for name in ("config.yaml", "target.stl", "trajectory.csv")})

            evaluation_output = getattr(self, "evaluate_output", None)
            if evaluation_output is not None:
                terminal_status, terminal_error = validate_final(Path(evaluation_output), True)
            else:
                with tempfile.TemporaryDirectory(prefix="waam_layer_") as directory:
                    terminal_status, terminal_error = validate_final(Path(directory), False)
            rterminal = (self.reward_weights.completion if terminal_status == "PASS"
                         else -self.reward_weights.validation_failure)
        info = self._info(layer_index=layer, layer_iou=float(metrics.iou), layer_shape_passed=bool(metrics.passed),
                          layer_duration_s=duration, time_reference_s=float(reference),
                          robot_utilization=utilizations, mean_robot_utilization=mean_utilization,
                          robot_idle_s=idle_times, idle_factor=idle_factor,
                          weighted_layer_duration_s=duration*idle_factor,
                          generated_segments=len(segments), robot_segment_counts=self.last_robot_counts,
                          reassigned_segments=reassigned, serial_fallback=serial_fallback,
                          reward_iou=riou, reward_time=rtime, reward_invalid=0.0, reward_terminal=rterminal,
                          terminal_status=terminal_status, terminal_error=terminal_error,
                          path_parameters=self.decode_action(action),
                          territory_area_mm2=[g.area for g in self.territories[layer]], **schedule)
        self.layer_history.append(dict(action=action.tolist(), **info))
        return self._observation(), float(riou+rtime+rterminal), self.done, False, info

    @staticmethod
    def decode_action(action):
        values = np.asarray(action).reshape(3, MAX_STROKES, 5)
        return dict(type="direct_xy_strokes", slots_per_robot=MAX_STROKES,
                    active_strokes=[int(np.count_nonzero(own[:, 4] > 0)) for own in values])

    def export(self, output):
        if self.index != len(self.layers):
            raise RuntimeError("Cannot export an incomplete layer schedule")
        output = Path(output)
        if output.exists() and any(output.iterdir()):
            raise FileExistsError("Choose a new/empty output directory")
        output.mkdir(parents=True, exist_ok=True)
        for name in ("config.yaml", "target.stl"):
            shutil.copy2(self.scenario/name, output/name)
        with (output/"trajectory.csv").open("w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream)
            writer.writerow(["robot_id", "time_s", "x_mm", "y_mm", "z_mm", "mode"])
            for r, own in enumerate(self.rows, 1):
                writer.writerows([[r, *row] for row in own])
        features = [dict(type="Feature", geometry=mapping(region), properties=dict(
                    layer=int(layer), z_mm=self._z(layer), robot_id=self.robots[r].id,
                    area_mm2=region.area))
                    for layer, regions in self.territories.items() for r, region in enumerate(regions)]
        (output/"territories.geojson").write_text(json.dumps(dict(type="FeatureCollection", features=features)), encoding="utf-8")
        return output


class MultiLayerEnv(gym.Env):
    def __init__(self, scenarios, *, reward_weights=None):
        super().__init__()
        self.scenarios = [Path(p).resolve() for p in scenarios]
        if not self.scenarios:
            raise ValueError("No training scenarios")
        self.environments = []
        for scenario in self.scenarios:
            print(f"Slicing training STL {scenario.name} ...", flush=True)
            self.environments.append(LayerPathEnv(scenario, reward_weights=reward_weights))
        self.action_space = self.environments[0].action_space
        self.observation_space = self.environments[0].observation_space
        self.reward_weights = self.environments[0].reward_weights
        self.episode_counts = [0]*len(self.scenarios)
        self.step_counts = [0]*len(self.scenarios)
        self.active = None
        self._cycle = []

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        if seed is not None:
            self._cycle = []
        if not self._cycle:
            self._cycle = list(self.np_random.permutation(len(self.environments)))
        self.active = int(self._cycle.pop())
        self.episode_counts[self.active] += 1
        observation, info = self.environments[self.active].reset(seed=int(self.np_random.integers(2**32)))
        return observation, dict(info, scenario_id=self.scenarios[self.active].name)

    def step(self, action):
        if self.active is None:
            raise RuntimeError("Call reset() before step()")
        observation, reward, terminated, truncated, info = self.environments[self.active].step(action)
        self.step_counts[self.active] += 1
        return observation, reward, terminated, truncated, dict(info, scenario_id=self.scenarios[self.active].name)

    def close(self):
        for env in self.environments:
            env.close()
