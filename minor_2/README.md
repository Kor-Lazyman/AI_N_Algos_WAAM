# minor_2

This branch starts from the original 1.0.2 layer-path PPO and changes only the
reward used by the environment. The original seven-field layer action,
three-robot partition and collision/schedule logic remain in place. There is
no STL placement network or scheduler search from `Minor`.

One action generates one whole layer. The observation has 309 floats and the
action space is `MultiDiscrete([8,3,4,2,2,3,6])`. The single PPO uses
SB3 `MlpPolicy` on CUDA by default. Geometry and the official Validator run on
CPU. Input jobs and the Validator are shared from the parent directory;
models/logs are saved under `minor_2/result`.

## Reward

For a valid layer with layer IoU strictly greater than 0.9:

`R = 10 * U_D * T_ref / T_layer`

Here `U_D` is the mean over the three robots of actual **deposition (D) time**
divided by the layer makespan. Travel (T) and waiting (W) do not count as
deposition. `T_ref` is computed from the target area, bead width, speeds and
robot home-to-target-centroid distances, independent of the selected action.

At layer IoU at or below 0.9, only the **official whole-STL Validator**
determines a terminal reward: +1 PASS, -1 FAIL/ERROR, or 0 before the final
layer. A path generation, reach or collision failure ends the episode at -2.
The same rule applies to the terminal layer; high IoU takes the performance
branch even when the official Validator fails. Validator PASS still determines
evaluation success.

## Run

From this directory, with the `waam` Conda environment:

```powershell
python train.py --mode train --device cuda --updates 40 --eval-every 4 --no-export-stl --init-model "../result/training/layers_1.0.2_20261017_044941_396096/ppo_model.zip"
```

`--updates 40` is 40 complete PPO rollouts of 64 layer steps, i.e. 2,560 layer
steps. The path policy is warm-started from the original 1.0.2 weights and the
optimizer resets. `target_kl=None`, so PPO optimizer epochs have no KL early
stop. Omit `--init-model` for random initialization. The six parent `train/`
STLs are used for learning and the six parent `validation/` STLs are evaluated
every four updates. `--no-export-stl` avoids the extra final pass over the six
training STLs; validation PASS episodes still contain exported trajectories
and deposited STL files. TensorBoard is enabled by default:

```powershell
tensorboard --logdir result/tensorboard
```

The run's `training.json` is authoritative for `status`, `completed_updates`,
CUDA device, reward formula and input hashes. The latest complete update is
`checkpoint.zip`; the final model after all requested updates is
`ppo_model.zip`.
