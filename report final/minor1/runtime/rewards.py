"""The same per-layer reward is used by path PPO and STL placement PPO."""
from dataclasses import dataclass, asdict
import math


@dataclass(frozen=True)
class LayerRewardWeights:
    performance: float = 10.0
    validator_pass: float = 1.0
    validation_failure: float = 1.0
    invalid: float = 2.0
    iou_threshold: float = 0.9

    def __post_init__(self):
        if any(not math.isfinite(v) or v < 0 for v in asdict(self).values()):
            raise ValueError('Reward parameters must be finite and nonnegative')
        if not 0 < self.iou_threshold < 1:
            raise ValueError('IoU threshold must be between zero and one')


def layer_reward(iou, duration, reference, utilization, terminal_status, weights):
    """Strict >0.9 gate. Existing full-Validator reward is terminal only."""
    if iou > weights.iou_threshold:
        value = weights.performance*utilization*reference/max(duration, 1e-9)
        return float(value), dict(reward_branch='performance', reward_time=float(value), reward_terminal=0.0)
    value = (weights.validator_pass if terminal_status == 'PASS' else
             -weights.validation_failure if terminal_status in ('FAIL', 'ERROR') else 0.0)
    return float(value), dict(reward_branch='validator', reward_time=0.0, reward_terminal=float(value))


def placement_reward(layer_rewards):
    """Aggregate only one STL episode; no rollout-wide or cross-STL averaging."""
    if not layer_rewards:
        raise ValueError('Placement requires at least one layer outcome')
    return float(sum(layer_rewards)/len(layer_rewards))
