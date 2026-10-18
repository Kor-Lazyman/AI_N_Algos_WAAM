# Algorithm 2. Minor2 - reward-only layer PPO

Input: training STL/config set, held-out validation set, initial Main 1.0.2 policy.

1. Retain the original layer action and path-generation environment; initialize PPO.
2. For each rollout, observe layer geometry/raster, schedule progress, robot reach, and process parameters.
3. Select hatch angle, spacing, start corner, reversal, partition axis/quota, and robot order.
4. Generate contours/hatch and partition segments among reachable robots. Build concurrent routes and check reach/collision; retry serialized starts on collision.
5. Reject infeasible paths with invalid-action penalty -2. Otherwise compute deposited geometry, layer IoU I, duration T, and mean deposition utilization U_D.
6. If I > 0.9, reward = 10 * U_D * T_ref / T. If I <= 0.9 and the episode is not complete, reward = 0. At the final layer, use +1 for whole-STL Validator PASS and -1 for FAIL/ERROR.
7. Append the layer schedule, update PPO, evaluate held-out validation STLs every four updates, and select by Validator pass rate.
8. Return the best path policy and exported trajectories.

Minor2 changes the layer reward gate and has no global STL placement policy. U_D counts deposition-mode time only; it excludes travel and waiting.
