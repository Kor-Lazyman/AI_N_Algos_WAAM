"""Check the revised reward and deposition-only utilization."""
import unittest

from layer_assignment_env import LayerRewardWeights, deposition_utilization, layer_reward


class RewardTests(unittest.TestCase):
    def test_threshold_and_time_direction(self):
        weights = LayerRewardWeights()
        self.assertEqual(layer_reward(.9, 100, 100, .5, 'PASS', weights)[0], 1.)
        self.assertEqual(layer_reward(.9, 100, 100, .5, 'FAIL', weights)[0], -1.)
        self.assertEqual(layer_reward(.9, 100, 100, .5, None, weights)[0], 0.)
        reward, parts = layer_reward(.9001, 100, 100, .5, 'PASS', weights)
        self.assertEqual(reward, 5.)
        self.assertEqual(parts['reward_terminal'], 0.)
        self.assertGreater(layer_reward(.95, 90, 100, .5, None, weights)[0], reward)
        self.assertGreater(layer_reward(.95, 100, 100, .6, None, weights)[0], reward)

    def test_only_deposition_counts(self):
        rows = [
            [[0,0,0,0,'T'],[2,1,0,0,'D'],[6,3,0,0,'W'],[10,3,0,0,'W']],
            [[0,0,0,0,'W'],[10,0,0,0,'W']],
            [[0,0,0,0,'D'],[3,2,0,0,'T'],[5,3,0,0,'W'],[10,3,0,0,'W']],
        ]
        self.assertAlmostEqual(deposition_utilization(rows, 10), (4/10+0+3/10)/3)


if __name__ == '__main__':
    unittest.main()
