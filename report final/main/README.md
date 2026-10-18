# 1.0.2 Main Layer PPO

## Training record

- Status: `completed`
- Updates: 16 / -
- Timesteps: 1024 / 1024
- Best checkpoint step: 256
- Recorded wall time: 1591.014091799996 s

## Training STL results

| STL | Makespan (DD:HH:MM:SS) | Calculation (DD:HH:MM:SS) | Validator |
|---|---:|---:|---|
| 01 | 00:00:42:57 | 00:00:00:07 | PASS |
| 02 | 00:01:28:31 | 00:00:00:12 | PASS |
| 03 | 00:01:07:50 | 00:00:00:05 | PASS |
| 04 | 00:20:06:15 | 00:00:01:07 | PASS |
| 05 | 05:01:23:21 | 00:00:08:35 | PASS |
| 06 | 00:02:40:19 | 00:00:00:23 | PASS |

## Included files

- Filled report template: this folder's DOCX file
- Single-STL runner: `test-version.py`
- Model and checkpoint: `model/`
- Training STL evaluations: `stl_files/`
- Standalone exported trajectories: `stl_files/exported_trajectory/01` to `06`
- Each training STL trajectory: `stl_files/job_00` to `job_05` → `episode_000/input/trajectory.csv`
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







