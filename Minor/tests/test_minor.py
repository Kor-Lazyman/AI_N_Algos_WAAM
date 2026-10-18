"""Check timing invariants, quality priority and the original-time upper bound."""
import unittest
from collections import Counter
from pathlib import Path
import numpy as np
import tempfile
from shapely.affinity import translate
from layer_assignment_env import LayerPathEnv, generate_layer_segments, ROBOT_ORDERS
from scheduler import activity_metrics, compose, schedule_layer
from train import validation_key
from rewards import layer_reward, LayerRewardWeights
from placement import PlacementSpec, PlacedLayerEnv, PlacementEnv

ROOT = Path(__file__).resolve().parents[2]


class MinorTests(unittest.TestCase):
    def test_reward_threshold_and_time_utilization_direction(self):
        w = LayerRewardWeights()
        self.assertEqual(layer_reward(.9,100,100,.5,'PASS',w)[0], 1.)
        self.assertEqual(layer_reward(.9,100,100,.5,'FAIL',w)[0], -1.)
        self.assertEqual(layer_reward(.9,100,100,.5,None,w)[0], 0.)
        r, info = layer_reward(.9001,100,100,.5,'PASS',w)
        self.assertEqual(r, 5.)
        self.assertEqual(info['reward_terminal'], 0.)
        self.assertGreater(layer_reward(.99,90,100,.5,None,w)[0], r)
        self.assertGreater(layer_reward(.99,100,100,.6,None,w)[0], r)

    def test_one_rigid_translation_for_all_slices_and_projection(self):
        path = ROOT / 'validation/01_rectangle'
        spec = PlacementSpec(path)
        extreme = spec.translation([1.,1.])
        self.assertLessEqual(np.linalg.norm(spec.hull+extreme-spec.center, axis=1).max(), spec.radius+1e-5)
        before = LayerPathEnv(path)
        with tempfile.TemporaryDirectory() as directory:
            meta = spec.write_job([.05,-.05], directory)
            after = LayerPathEnv(directory)
            self.assertEqual(len(before.layers), len(after.layers))
            delta = meta['translation_xyz_mm']
            self.assertEqual(delta[2], 0.)
            for (z1,p1),(z2,p2) in zip(before.layers,after.layers):
                self.assertEqual(z1,z2)
                self.assertLess(translate(p1,delta[0],delta[1]).symmetric_difference(p2).area,.01)
            after.close()
        before.close()

    def test_placement_episode_reward_is_scoped_to_one_stl(self):
        class FixedLayerPolicy:
            def predict(self, observation, deterministic=True):
                return np.array([0,2,0,0,0,0,0]), None
        env = PlacementEnv([ROOT/'validation/00_sample',ROOT/'validation/01_rectangle'])
        env.layer_policy = FixedLayerPolicy()
        names = []
        for index in range(2):
            env.reset(seed=123 if index == 0 else None)
            _, reward, done, _, info = env.step(np.zeros(2, dtype=np.float32))
            self.assertTrue(done)
            self.assertEqual(reward, sum(info['layer_rewards'])/len(info['layer_rewards']))
            self.assertEqual(info['terminal_status'], 'PASS')
            names.append(info['scenario_id'])
        self.assertEqual(len(set(names)), 2)
        env.close()

    def test_activity_does_not_reward_travel(self):
        rows = [[[0,0,0,0,'T'],[2,1,0,0,'W'],[4,1,0,0,'W']],
                [[0,0,0,0,'D'],[4,1,0,0,'W']], [[0,0,0,0,'D'],[4,1,0,0,'W']]]
        info = activity_metrics(rows, 4)
        self.assertEqual(info['deposition_2plus_s'], 4)
        self.assertEqual(info['deposition_3_s'], 0)
        self.assertEqual(info['robot_deposition_s'], [0,4,4])
        self.assertEqual(info['total_wait_s'], 2)

    def test_selection_prefers_pass_then_shorter_time(self):
        def record(passed, duration):
            return dict(success=passed, schedule_complete=True, status='PASS' if passed else 'FAIL',
                makespan_s=duration, episode_reward=0, episode_length=1, iou=.99,
                steps=[dict(time_reference_s=100, deposition_2plus_s=0)])
        self.assertGreater(validation_key([record(True,100)]), validation_key([record(True,110)]))
        self.assertGreater(validation_key([record(True,100)]), validation_key([record(False,1)]))

    def test_real_layer_preserves_material_and_upper_bound(self):
        env = LayerPathEnv(ROOT / 'train/02')
        action = np.array([0,2,0,0,0,0,0])
        layer, target = env.layers[0]
        segments = generate_layer_segments(target, env.config.process.bead_width_mm,
                                           env.config.shape_validation.polygon_buffer_resolution, action)
        groups, _ = env._partition(segments, action)
        rows, duration, selected, info = schedule_layer(env, segments, groups, env._z(layer), ROBOT_ORDERS[0])
        self.assertIsNotNone(rows)
        self.assertTrue(env._check_local(rows)[0])
        self.assertLessEqual(duration, info['baseline_duration_s']+1e-8)
        canonical = lambda items: Counter(tuple(sorted((tuple(a),tuple(b)))) for a,b in items)
        self.assertEqual(canonical(segments), canonical([s for group in selected for s in group]))
        metrics = activity_metrics(rows, duration)
        self.assertAlmostEqual(sum(metrics['robot_deposition_s'])+sum(metrics['robot_travel_s'])+metrics['total_wait_s'], 3*duration)
        env.close()


if __name__ == '__main__':
    unittest.main()
