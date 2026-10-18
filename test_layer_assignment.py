"""Layer steps must create physical paths, preserve reach, and pass the backend.

These tests use the official sample geometry, plus a two-layer copy of it.
They deliberately do not reuse prepared tasks.json files.
"""

from copy import deepcopy
from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
from shapely.geometry import box
import trimesh
import yaml

from validator_adapter import VALIDATOR_ROOT, run_validation
from layer_assignment_env import (LayerPathEnv, MultiLayerEnv, generate_layer_segments,
                                  robot_layer_utilization)
from waam_validator import compute_reach_metrics
from waam_validator.constants import MODE_D


SAMPLE = VALIDATOR_ROOT / "examples/sample_job"
# 0 degree hatch, 0.9 bead spacing, lower-left start, forward order,
# X bands, equal quotas, identity robot order.
ACTION = np.array([0, 1, 0, 0, 0, 0, 0], dtype=np.int64)


def geometric_segments(segments):
    """Discard orientation/order when checking that only order was changed."""
    return sorted(tuple(sorted(tuple(round(float(x), 5) for x in point)
                               for point in segment)) for segment in segments)


class LayerPathTests(unittest.TestCase):
    def test_idle_factor_uses_each_robot_busy_fraction(self):
        def rows(busy_s):
            return ([[0.0, 0, 0, 0, "T"], [busy_s, 0, 0, 0, "W"],
                     [10.0, 0, 0, 0, "W"]] if busy_s else
                    [[0.0, 0, 0, 0, "W"], [10.0, 0, 0, 0, "W"]])
        for busy, expected in [((10, 0, 0), 3.0),
                               ((10, 10, 0), 2.0),
                               ((10, 10, 10), 1.0),
                               ((5, 5, 5), 2.5)]:
            with self.subTest(busy=busy):
                utilization = robot_layer_utilization([rows(value) for value in busy], 10.0)
                self.assertAlmostEqual(4.0-sum(utilization), expected)

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def scenario(self, *, layers=1, radii=None):
        destination = self.root / ("job_" + str(len(list(self.root.iterdir()))))
        destination.mkdir()
        config = yaml.safe_load((SAMPLE / "config.yaml").read_text())
        if radii is not None:
            for robot, radius in zip(config["robots"], radii, strict=True):
                robot["xy_reach_radius_mm"] = radius
        (destination / "config.yaml").write_text(yaml.safe_dump(config))
        if layers == 1:
            shutil.copy2(SAMPLE / "target.stl", destination / "target.stl")
        else:
            mesh = trimesh.load(SAMPLE / "target.stl", process=False)
            mesh.vertices[:, 2] *= layers
            mesh.export(destination / "target.stl")
        self.assertFalse((destination / "tasks.json").exists())
        return destination

    def make_env(self, scenario):
        env = LayerPathEnv(scenario)
        self.addCleanup(env.close)
        return env

    def test_two_layers_take_two_actions_and_full_export_passes(self):
        env = self.make_env(self.scenario(layers=2))
        observation, _ = env.reset(seed=7)
        self.assertTrue(env.observation_space.contains(observation))
        self.assertEqual(len(env.layers), 2)
        for layer in range(2):
            observation, reward, done, truncated, info = env.step(ACTION)
            self.assertTrue(np.isfinite(reward))
            self.assertFalse(truncated)
            self.assertEqual(env.index, layer + 1)
            self.assertEqual(done, layer == 1)
            self.assertTrue(env.observation_space.contains(observation))
            # Every accepted layer is a physical barrier at the robots' homes.
            for robot, rows in enumerate(env.rows):
                np.testing.assert_allclose(rows[-1][1:4], env.homes[robot])
                self.assertEqual(rows[-1][-1], "W")
            self.assertEqual(len({rows[-1][0] for rows in env.rows}), 1)
        self.assertIsNotNone(env.terminal_validation)
        self.assertEqual(env.terminal_validation.status, "PASS")
        job = self.root / "exported"
        env.export(job)
        result = run_validation(job, self.root / "official_validation")
        self.assertEqual(result.status, "PASS")
        self.assertEqual(len(result.collision.events), 0)

    def test_path_controls_change_geometry_and_order(self):
        target = box(-40, -25, 40, 25)
        baseline = generate_layer_segments(target, 4.0, 8, ACTION)
        rotated = ACTION.copy()
        rotated[0] = 2  # 45 degrees.
        rotated_paths = generate_layer_segments(target, 4.0, 8, rotated)
        self.assertNotEqual(geometric_segments(baseline), geometric_segments(rotated_paths))
        coarse = ACTION.copy()
        coarse[1] = 2
        fine = ACTION.copy()
        fine[1] = 0
        self.assertGreater(len(generate_layer_segments(target, 4.0, 8, fine)),
                           len(generate_layer_segments(target, 4.0, 8, coarse)))
        reversed_action = ACTION.copy()
        reversed_action[3] = 1
        reversed_paths = generate_layer_segments(target, 4.0, 8, reversed_action)
        self.assertNotEqual(baseline, reversed_paths)
        self.assertEqual(geometric_segments(baseline), geometric_segments(reversed_paths))

    def test_all_unreachable_rejects_whole_layer_without_partial_path(self):
        env = self.make_env(self.scenario(radii=[100, 100, 100]))
        original_rows = deepcopy(env.rows)
        original_observation, _ = env.reset(seed=3)
        observation, reward, done, truncated, info = env.step(ACTION)
        self.assertTrue(done)
        self.assertFalse(truncated)
        self.assertEqual(env.index, 0)
        self.assertLess(reward, 0)
        self.assertEqual(env.rows, original_rows)
        np.testing.assert_array_equal(observation, original_observation)
        self.assertEqual(info["failure_reason"], "unreachable")
        self.assertIsNone(env.terminal_validation)

    def test_one_reachable_robot_deposits_entire_layer(self):
        for available in range(3):
            with self.subTest(available=available):
                radii = [100, 100, 100]
                radii[available] = 2500
                env = self.make_env(self.scenario(radii=radii))
                _, reward, done, truncated, info = env.step(ACTION)
                self.assertTrue(done)
                self.assertFalse(truncated)
                self.assertEqual(env.index, 1)
                self.assertEqual(env.terminal_validation.status, "PASS")
                trajectory = env._trajectory(env.rows)
                self.assertTrue(compute_reach_metrics(trajectory, env.config).passed)
                depositing = [r.robot_id for r in trajectory.robots
                              if np.any(r.mode[:-1] == MODE_D)]
                self.assertEqual(depositing, [available + 1])
                self.assertAlmostEqual(info["mean_robot_utilization"], 1/3)
                self.assertAlmostEqual(info["idle_factor"], 3.0)
                self.assertAlmostEqual(info["reward_time"],
                    -env.reward_weights.time*info["layer_duration_s"]*3/info["time_reference_s"])
                self.assertAlmostEqual(reward, info["reward_iou"] + info["reward_time"]
                                       + info["reward_terminal"])

    def test_invalid_action_leaves_state_unchanged(self):
        env = self.make_env(self.scenario())
        before = deepcopy(env.rows)
        invalid = ACTION.copy()
        invalid[0] = 8
        with self.assertRaises(ValueError):
            env.step(invalid)
        self.assertEqual(env.index, 0)
        self.assertEqual(env.rows, before)

    def test_collision_on_both_schedules_rejects_layer_atomically(self):
        env = self.make_env(self.scenario())
        before = deepcopy(env.rows)
        with patch("layer_assignment_env.run_collision_analysis",
                   return_value=SimpleNamespace(events=[object()])) as collision:
            _, reward, done, truncated, info = env.step(ACTION)
        self.assertEqual(collision.call_count, 2)  # Parallel and serial both checked.
        self.assertTrue(done)
        self.assertFalse(truncated)
        self.assertEqual(info["failure_reason"], "collision")
        self.assertTrue(info["serial_fallback"])
        self.assertEqual(reward, -env.reward_weights.invalid)
        self.assertEqual(env.rows, before)
        self.assertEqual(env.index, 0)
        self.assertEqual(env.layer_history, [])

    def test_validator_failure_has_no_completion_bonus(self):
        scenario = self.scenario()
        config = yaml.safe_load((scenario / "config.yaml").read_text())
        # Deliberately stricter fixture: generated capsule is good but not exact.
        config["shape_validation"]["minimum_overall_iou"] = 0.99999
        (scenario / "config.yaml").write_text(yaml.safe_dump(config))
        env = self.make_env(scenario)
        _, reward, done, _, info = env.step(ACTION)
        self.assertTrue(done)
        self.assertTrue(info["schedule_complete"])
        self.assertEqual(env.terminal_validation.status, "FAIL")
        self.assertEqual(info["reward_terminal"], -env.reward_weights.validation_failure)
        self.assertAlmostEqual(reward, info["reward_iou"] + info["reward_time"]
                               + info["reward_terminal"])

    def test_policy_robot_order_controls_actual_partition(self):
        env = self.make_env(self.scenario())
        segments = generate_layer_segments(box(-40, -25, 40, 25), 4, 8, ACTION)
        first, _ = env._partition(segments, ACTION)
        reverse_order = ACTION.copy()
        reverse_order[6] = 5  # 3,2,1 instead of 1,2,3.
        second, _ = env._partition(segments, reverse_order)
        self.assertEqual(first[0], second[2])
        self.assertEqual(first[1], second[1])
        self.assertEqual(first[2], second[0])
        self.assertTrue(all(first))
        quota = ACTION.copy()
        quota[5] = 1  # First spatial band gets one half of deposition length.
        weighted, _ = env._partition(segments, quota)
        def length(group):
            return sum(np.linalg.norm(np.asarray(b) - a) for a, b in group)
        self.assertGreater(length(weighted[0]), length(first[0]))

    def test_multijob_cycles_share_observation_space_and_seed(self):
        scenarios = [self.scenario(), self.scenario(layers=2)]
        env = MultiLayerEnv(scenarios)
        self.addCleanup(env.close)
        sequence = []
        for index in range(4):
            observation, info = env.reset(seed=31 if index == 0 else None)
            sequence.append(info["scenario_id"])
            self.assertTrue(env.observation_space.contains(observation))
            self.assertEqual(env.environments[env.active].action_space, env.action_space)
        self.assertEqual(len(set(sequence[:2])), 2)
        self.assertEqual(len(set(sequence[2:])), 2)
        replay = [env.reset(seed=31)[1]["scenario_id"]]
        replay.extend(env.reset()[1]["scenario_id"] for _ in range(3))
        self.assertEqual(sequence, replay)


if __name__ == "__main__":
    unittest.main()
