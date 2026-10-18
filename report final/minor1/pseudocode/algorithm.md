# Minor1 pseudocode

**Algorithm 1 — Joint Global Placement and Layer Scheduling**

```text
INPUT: disjoint training STL jobs J, held-out validation jobs V,
       layer PPO pi_l, placement PPO pi_p, rollout sizes N_l and N_p, updates U
OUTPUT: best paired checkpoints, full trajectories, official WAAM Validator reports

Initialize the layer/path and placement policies (optionally load compatible weights).
Freeze disjoint training and validation jobs; reject overlap in target-STL hashes.
FOR update u = 1,...,U:
    Collect N_l layer transitions under the current placement policy.
    PPO-update the layer/path policy pi_l.
    IF u is a placement-update interval:
        FOR each of N_p full-STL placement episodes (N_p >= 2):
            Select a training STL and observe mesh, workspace, and robot/process features.
            Sample shared (dx,dy) from pi_p; clip and scale action by workspace radius.
            Project the translation so every mesh-hull vertex remains inside the workspace.
            Translate the entire STL by (dx,dy,0), then slice the translated geometry.
            FOR each target layer k:
                pi_l selects path parameters and robot partition; generate all segments.
                Build the original concurrent schedule; use serial fallback if collision requires it.
                Try nearest-base and load-balanced assignments, route ordering,
                concurrent starts, and bounded staggered offsets under two priorities.
                Reject candidates that fail reach, trajectory, or collision checks.
                Keep the feasible candidate with minimum makespan; retain every deposition segment.
                IF IoU > 0.9:
                    r_k = 10 * mean_deposition_utilization * reference_time / layer_duration
                ELSE:
                    terminal Validator PASS = +1; FAIL/ERROR = -1; unavailable = 0
            END FOR
            Placement episode reward = mean layer rewards for this STL only.
        END FOR
        PPO-update pi_p from full-STL episode rewards.
    END IF
    Evaluate held-out validation jobs; retain the best paired checkpoint by validation key.
END FOR
Export complete trajectories and run the official WAAM Validator.
```

Minor1 has two learned PPO policies: global XY placement and layer/path selection. The placement policy applies one shared XY translation to the whole STL before slicing. Candidate schedule generation and collision-aware selection use bounded heuristic search; that scheduler is not a learned policy.
