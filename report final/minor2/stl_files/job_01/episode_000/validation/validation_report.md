# WAAM Validator Report

## Overall Result

**PASS**

- WAAM Validator version: 1.0.1

## Input Summary

- Directory: `C:\Users\lazzyman\Desktop\AINalgos2\version 1.0.2\AInalgos2-main\minor_2\result\training\reward_only_40updates_20261018_155838\comparison\original_stl_files_after\job_01\episode_000\input`
- Trajectory rows: 8253
- Target watertight: True

## Schedule

- Makespan: 5074.49 s
- R1: completion 5074.49 s; Deposition 716.22 s; Travel 248.45 s; Wait 4109.81 s
- R2: completion 5074.49 s; Deposition 2150.02 s; Travel 505.24 s; Wait 2419.22 s
- R3: completion 5074.49 s; Deposition 1133.05 s; Travel 321.50 s; Wait 3619.94 s

## Robot XY Reach

- Passed: True
- R1: max XY distance 1499.72 / 1500.00 mm; XY margin 0.28 mm; violating points 0
- R2: max XY distance 1499.12 / 1500.00 mm; XY margin 0.88 mm; violating points 0
- R3: max XY distance 1392.53 / 1500.00 mm; XY margin 107.47 mm; violating points 0

## Collision

- Arm Envelope events: 0
- Minimum Arm Envelope safety margin: 591.57 mm
- Arm centerline distance at worst case:
  841.57 mm
- Arm required centerline distance at worst case:
  250.00 mm
- TCP_RADIUS events: 0
- Minimum TCP distance: 841.57 mm

## Shape

- Target layer-integrated volume: 254007.549 mm³
- Deposited volume: 259105.270 mm³
- Intersection volume: 254007.549 mm³
- Underfill volume: 0.000 mm³
- Overfill volume: 5097.721 mm³
- Coverage: 100.00%
- Underfill: 0.00%
- Overfill: 2.01%
- IoU: 98.03%
- Failed layers: 0 / 8

## Failure Reasons

None

## Warnings

None

## Validation Violations

These findings contribute to a normal `FAIL`; they do not mean that the pipeline ended with
the fatal status `ERROR`.

None

## Output Files

- `summary.json`
- `validation_report.md`
- `robot_metrics.csv`
- `collision_events.csv`
- `layer_metrics.csv`
- `run.log`
- `validation_inputs.json`

## Interpretation Limitations

본 검증기는 각 로봇을 폭이 고정된 Base–TCP 2D Capsule로 단순화하고, XY 평면상 Capsule 안전 여유와 TCP 허용 원 침범만을 로봇 간 충돌로 판단한다. 검사는 adaptive sample 기반이며 연속시간 swept collision을 보증하지 않는다. 실제 로봇 링크, 관절 자세, Z 방향 분리, 지그 및 환경 충돌은 반영하지 않는다. 형상 검증은 일정한 비드 폭과 layer 높이를 가정한 명목 기하 모델이며 열변형, 비드 형상 변화, 용융풀 거동 및 공정 불안정성을 예측하지 않는다.
