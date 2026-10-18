"""실제 reach/충돌/형상 검사를 포함하는 Beta 핵심 계약."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from shapely.geometry import box, Point
from shapely.ops import unary_union

from layer_assignment_env import LayerPathEnv
from territory import ACTION_SIZE, partition_layer, nearest_owner, reference_action, direct_groups
from scheduler import schedule_layer
from evaluate_layers import ROOT, space_schema


class TerritoryTests(unittest.TestCase):
    def test_nearest_reachable_ownership_and_tie(self):
        robots = [SimpleNamespace(id=i+1, base_xyz_mm=[x, y, 0], xy_reach_radius_mm=100)
                  for i, (x, y) in enumerate(((-10, 0), (10, 0), (0, 20)))]
        target = box(-20, -10, 20, 25)
        regions, gap = partition_layer(target, robots)
        self.assertLess(gap, 1e-7)
        self.assertAlmostEqual(unary_union(regions).area, target.area)
        for a in range(3):
            for b in range(a+1, 3):
                self.assertLess(regions[a].intersection(regions[b]).area, 1e-7)
        for p in ((-12, 0), (12, 0), (0, 22)):
            owner = nearest_owner(p, robots)
            self.assertTrue(regions[owner].covers(Point(p)))
        self.assertEqual(nearest_owner((0, 0), robots), 0)
        robots[0].xy_reach_radius_mm = 1
        self.assertEqual(nearest_owner((-8, 0), robots), 1)
        regions, gap = partition_layer(target, robots)
        self.assertTrue(regions[1].covers(Point(-8, 0)))

    def test_direct_action_no_autofill_and_box_schema(self):
        env = LayerPathEnv(ROOT.parent/'validation/00_sample')
        self.addCleanup(env.close)
        observation, _ = env.reset()
        self.assertEqual(observation.shape, (1080,))
        self.assertEqual(space_schema(env)['action']['type'], 'Box')
        action = np.zeros(ACTION_SIZE, np.float32)
        _, reward, done, _, info = env.step(action)
        self.assertTrue(done)
        self.assertEqual(info['failure_reason'], 'empty_direct_path')
        self.assertEqual(env.index, 0)

    def test_direct_reference_sample_passes(self):
        env = LayerPathEnv(ROOT.parent/'validation/00_sample')
        self.addCleanup(env.close)
        action = reference_action(env)
        self.assertTrue(env.action_space.contains(action))
        layer, target = env.layers[0]
        groups = direct_groups(action, target, env.territories[layer], env.robots,
                               env.config.process.bead_width_mm, 8)
        for r, group in enumerate(groups):
            for a, b in group:
                midpoint = (np.asarray(a)+b)/2
                self.assertEqual(nearest_owner(midpoint, env.robots), r)
        _, _, done, _, info = env.step(action)
        self.assertTrue(done)
        self.assertEqual(info['terminal_status'], 'PASS')

    def test_normalized_boundary_lines_are_not_lost(self):
        from layer_assignment_env import generate_layer_segments
        from shapely.geometry import LineString
        env = LayerPathEnv(ROOT.parent/'validation/01_rectangle')
        self.addCleanup(env.close)
        layer, target = env.layers[0]
        original = generate_layer_segments(target, 4, 8, [0, 1, 0, 0, 0, 0, 0], max_segment_mm=float('inf'))
        groups = direct_groups(reference_action(env), target, env.territories[layer], env.robots, 4, 8)
        self.assertAlmostEqual(sum(LineString(s).length for s in original),
                               sum(LineString(s).length for group in groups for s in group), places=3)

    def test_blocked_robot_runs_another_task(self):
        env = LayerPathEnv(ROOT.parent/'train/01')
        self.addCleanup(env.close)
        # Robot 2's first task conflicts with robot 1. Its farther-side task
        # can run concurrently, so it must not simply wait for the first task.
        groups = [[((-100, -100), (-100, 100))],
                  [((20, -30), (20, 30)), ((400, 300), (450, 300))], []]
        rows, duration, info = schedule_layer(env, groups, 1.0)
        self.assertIsNotNone(rows)
        self.assertGreater(info['reordered_tasks'], 0)
        self.assertGreater(info['deposition_2plus_s'], 0)
        self.assertTrue(env._check_local(rows)[0])

    def test_serial_layer_avoids_per_task_home_returns(self):
        env = LayerPathEnv(ROOT.parent/'train/01')
        self.addCleanup(env.close)
        groups = [[((-100, -40), (-100, -20)), ((-100, 20), (-100, 40))], [], []]
        rows, duration, info = schedule_layer(env, groups, 1.0)
        self.assertTrue(info['compacted_serial'])
        self.assertTrue(env._check_local(rows)[0])
        self.assertEqual(sum(a[4] == 'D' for a in rows[0][:-1]), 2)


if __name__ == '__main__':
    unittest.main()
