# WAAM Validator Report

## Overall Result

**PASS**

- WAAM Validator version: 1.0.1

## Input Summary

- Directory: `C:\Users\lazzyman\Desktop\AINalgos2\version 1.0.2\AInalgos2-main\Minor\result\layer_evaluation\training_stl_validator_20261018\job_05\episode_000\input`
- Trajectory rows: 3212
- Target watertight: True

## Schedule

- Makespan: 7947.65 s
- R1: completion 7947.65 s; Deposition 2995.19 s; Travel 975.28 s; Wait 3977.18 s
- R2: completion 7947.65 s; Deposition 64.08 s; Travel 132.09 s; Wait 7751.48 s
- R3: completion 7947.65 s; Deposition 3662.34 s; Travel 929.86 s; Wait 3355.45 s

## Robot XY Reach

- Passed: True
- R1: max XY distance 1411.12 / 1500.00 mm; XY margin 88.88 mm; violating points 0
- R2: max XY distance 1397.97 / 1500.00 mm; XY margin 102.03 mm; violating points 0
- R3: max XY distance 1415.93 / 1500.00 mm; XY margin 84.07 mm; violating points 0

## Collision

- Arm Envelope events: 0
- Minimum Arm Envelope safety margin: 1.26 mm
- Arm centerline distance at worst case:
  251.26 mm
- Arm required centerline distance at worst case:
  250.00 mm
- TCP_RADIUS events: 0
- Minimum TCP distance: 251.26 mm

## Shape

- Target layer-integrated volume: 636118.062 mm³
- Deposited volume: 638323.316 mm³
- Intersection volume: 634916.261 mm³
- Underfill volume: 1201.801 mm³
- Overfill volume: 3407.053 mm³
- Coverage: 99.81%
- Underfill: 0.19%
- Overfill: 0.54%
- IoU: 99.28%
- Failed layers: 0 / 51

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
