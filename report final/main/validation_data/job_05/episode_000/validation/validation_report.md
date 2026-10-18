# WAAM Validator Report

## Overall Result

**PASS**

- WAAM Validator version: 1.0.1

## Input Summary

- Directory: `C:\Users\lazzyman\Desktop\AINalgos2\version 1.0.2\AInalgos2-main\results\layer_evaluation\validation_stl_20261017_latest_runtime\job_05\episode_000\input`
- Trajectory rows: 296
- Target watertight: True

## Schedule

- Makespan: 347.07 s
- R1: completion 347.07 s; Deposition 67.89 s; Travel 21.28 s; Wait 257.89 s
- R2: completion 347.07 s; Deposition 140.43 s; Travel 21.50 s; Wait 185.14 s
- R3: completion 347.07 s; Deposition 72.94 s; Travel 23.02 s; Wait 251.11 s

## Robot XY Reach

- Passed: True
- R1: max XY distance 1216.22 / 2500.00 mm; XY margin 1283.78 mm; violating points 0
- R2: max XY distance 1214.35 / 2500.00 mm; XY margin 1285.65 mm; violating points 0
- R3: max XY distance 1215.26 / 2500.00 mm; XY margin 1284.74 mm; violating points 0

## Collision

- Arm Envelope events: 0
- Minimum Arm Envelope safety margin: 866.16 mm
- Arm centerline distance at worst case:
  1116.16 mm
- Arm required centerline distance at worst case:
  250.00 mm
- TCP_RADIUS events: 0
- Minimum TCP distance: 1116.16 mm

## Shape

- Target layer-integrated volume: 14718.871 mm³
- Deposited volume: 14752.630 mm³
- Intersection volume: 14718.871 mm³
- Underfill volume: 0.000 mm³
- Overfill volume: 33.758 mm³
- Coverage: 100.00%
- Underfill: 0.00%
- Overfill: 0.23%
- IoU: 99.77%
- Failed layers: 0 / 1

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
