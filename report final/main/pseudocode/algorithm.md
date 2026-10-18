# Algorithm 1. Main 1.0.2 - preprocessing and PPO training

Input: training STL/config set, held-out validation set, PPO rollout settings.

1. Parse config.yaml. Load STL with Trimesh; concatenate scene meshes; merge vertices/faces; remove degenerate faces and unused vertices; repair normals and optionally fill holes.
2. Validate finite coordinates, watertight policy, build-plane bounds, process values, and robot configuration.
3. Determine evaluated layer indices and slice each horizontal section at build_plane + (k + 0.5) * layer_height.
4. Normalize each section polygon using configured snap tolerance and area epsilon; discard empty layers; cache a 16 x 16 fractional-area raster per target layer.
5. Initialize three robot states at home and the PPO policy with MultiDiscrete([8,3,4,2,2,3,6]).
6. For each layer, observe schedule progress, makespan, IoU, layer bounds/area/perimeter/raster, robot reach, process settings, and validation limits.
7. PPO chooses hatch angle, spacing, start corner, reversal, partition axis, quota, and robot order. Generate inset contours and clipped hatch, split long segments, and assign them to reachable robots.
8. Build travel/deposition/wait trajectories. Check reach, trajectory semantics, and collisions. On collision, retry the same layer with serialized starts; reject infeasible routes with reward -2.
9. Compute deposited geometry, layer IoU, duration, robot utilization, and idle_factor = 1 + sum(idle_seconds)/duration.
10. Reward = IoU - 0.1 * duration * idle_factor / reference_time. On the final layer, run the whole-schedule WAAM Validator and add +1 for PASS or -1 for FAIL/ERROR.
11. Append layer routes with time offsets, update observations and PPO rollout buffer, update the policy, and select validation checkpoints by pass rate.

Environment preprocessing follows load_target_mesh, determine_evaluation_layers, slice_target_layers, and normalize_polygon. One PPO step generates one complete layer path. The official whole-trajectory Validator is the final authority.
