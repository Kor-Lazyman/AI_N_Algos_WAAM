# Minor1 Placement and Scheduler PPO

## Training record

- Status: `started`
- Updates: 28 / 40
- Timesteps: 1792 / 2560
- Best checkpoint step: 1024
- Recorded wall time: 29952.735849399993 s

## Training STL results

| STL | Makespan (DD:HH:MM:SS) | Calculation (DD:HH:MM:SS) | Validator |
|---|---:|---:|---|
| 01 | 00:00:35:03 | 00:00:00:13 | PASS |
| 02 | 00:01:09:18 | 00:00:00:25 | PASS |
| 03 | 00:00:57:30 | 00:00:00:14 | PASS |
| 04 | 00:15:02:28 | 00:00:02:59 | PASS |
| 05 | 02:03:13:53 | 00:00:37:06 | PASS |
| 06 | 00:02:12:27 | 00:00:01:26 | PASS |

## Included files

- Filled report template: this folder's DOCX file
- Single-STL runner: `test-version.py`
- Model and checkpoint: `model/`
- Training STL evaluations and trajectories: `stl_files/job_00` to `job_05` → `episode_000/input/trajectory.csv`
- Validation dataset evaluations: `validation_data/`
- Pseudocode: `pseudocode/algorithm.md`
- Algorithm flowchart image: `pseudocode/algorithm.png`
- New runs are written under `output/`

## Run one STL

```powershell
python test-version.py --stl C:\path\to\target.stl
python test-version.py --stl C:\path\to\target.stl --config C:\path\to\config.yaml --device cpu
```

`--config` defaults to `config.yaml` beside the STL. Each run creates a new timestamped folder under `output/` with trajectory CSV, Validator reports and JSON, and Gantt HTML/SVG.



