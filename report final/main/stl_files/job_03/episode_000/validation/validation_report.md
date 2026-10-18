# WAAM Validator Report

## Overall Result

**PASS**

- WAAM Validator version: 1.0.1

## Input Summary

- Directory: `C:\Users\lazzyman\Desktop\AINalgos2\version 1.0.2\AInalgos2-main\results\layer_evaluation\stl_files_20261017_trained_model_runtime\job_03\episode_000\input`
- Trajectory rows: 36622
- Target watertight: True

## Schedule

- Makespan: 72375.42 s
- R1: completion 72375.42 s; Deposition 26821.60 s; Travel 2139.19 s; Wait 43414.63 s
- R2: completion 72375.42 s; Deposition 16854.42 s; Travel 1988.86 s; Wait 53532.14 s
- R3: completion 72375.42 s; Deposition 22625.42 s; Travel 1945.93 s; Wait 47804.07 s

## Robot XY Reach

- Passed: True
- R1: max XY distance 1499.23 / 1500.00 mm; XY margin 0.77 mm; violating points 0
- R2: max XY distance 1499.58 / 1500.00 mm; XY margin 0.42 mm; violating points 0
- R3: max XY distance 1499.96 / 1500.00 mm; XY margin 0.04 mm; violating points 0

## Collision

- Arm Envelope events: 0
- Minimum Arm Envelope safety margin: 531.70 mm
- Arm centerline distance at worst case:
  781.70 mm
- Arm required centerline distance at worst case:
  250.00 mm
- TCP_RADIUS events: 0
- Minimum TCP distance: 781.70 mm

## Shape

- Target layer-integrated volume: 6661016.843 mm³
- Deposited volume: 6678528.562 mm³
- Intersection volume: 6661016.813 mm³
- Underfill volume: 0.029 mm³
- Overfill volume: 17511.748 mm³
- Coverage: 100.00%
- Underfill: 0.00%
- Overfill: 0.26%
- IoU: 99.74%
- Failed layers: 0 / 50

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
