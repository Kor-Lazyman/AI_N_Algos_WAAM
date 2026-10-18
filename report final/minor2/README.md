# Minor2 Reward Only PPO

## Training record

- Status: `completed`
- Updates: 40 / 40
- Timesteps: 2560 / 2560
- Best checkpoint step: 256
- Recorded wall time: 2494.289177400002 s

## Training STL results

| STL | Makespan (DD:HH:MM:SS) | Calculation (DD:HH:MM:SS) | Validator |
|---|---:|---:|---|
| 01 (Honeycomb) | 00:00:40:50 | 00:00:00:05 | PASS |
| 02 (Spiral) | 00:01:24:34 | 00:00:00:10 | PASS |
| 03 (Triangular truss) | 00:01:06:16 | 00:00:00:06 | PASS |
| 04 (Motor inner) | 00:19:16:04 | 00:00:01:25 | PASS |
| 05 (Twisted shell) | 04:12:27:22 | 00:00:07:14 | PASS |
| 06 (Angle frame) | 00:02:41:07 | 00:00:00:16 | PASS |

## Included files

- Filled report template: this folder's DOCX file
- Single-STL runner: `test-version.py`
- Model and checkpoint: `model/`
- Training STL evaluations and trajectories: `stl_files/job_00` to `job_05` → `episode_000/input/trajectory.csv`
- Validation dataset evaluations: `validation_data/`
- Pseudocode: `pseudocode/algorithm.md`
- Paper-style algorithm pseudocode image: `pseudocode/algorithm.png`
- New runs are written under `output/`

## Run one STL

```powershell
python test-version.py --stl C:\path\to\target.stl
python test-version.py --stl C:\path\to\target.stl --config C:\path\to\config.yaml --device cpu
```

`--config` defaults to `config.yaml` beside the STL. Each run creates a new timestamped folder under `output/` with trajectory CSV, Validator reports and JSON, and Gantt HTML/SVG.







