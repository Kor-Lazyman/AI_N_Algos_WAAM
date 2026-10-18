# WAAM Validator Report

## Overall Result

**PASS**

- WAAM Validator version: 1.0.1

## Input Summary

- Directory: `C:\Users\lazzyman\Desktop\AINalgos2\version 1.0.2\AInalgos2-main\results\layer_evaluation\validation_stl_20261017_latest_runtime\job_03\episode_000\input`
- Trajectory rows: 183
- Target watertight: True

## Schedule

- Makespan: 562.92 s
- R1: completion 562.92 s; Deposition 215.01 s; Travel 44.05 s; Wait 303.87 s
- R2: completion 562.92 s; Deposition 103.00 s; Travel 42.20 s; Wait 417.72 s
- R3: completion 562.92 s; Deposition 115.60 s; Travel 43.06 s; Wait 404.26 s

## Robot XY Reach

- Passed: True
- R1: max XY distance 1203.67 / 2500.00 mm; XY margin 1296.33 mm; violating points 0
- R2: max XY distance 1191.26 / 2500.00 mm; XY margin 1308.74 mm; violating points 0
- R3: max XY distance 1244.02 / 2500.00 mm; XY margin 1255.98 mm; violating points 0

## Collision

- Arm Envelope events: 0
- Minimum Arm Envelope safety margin: 848.61 mm
- Arm centerline distance at worst case:
  1098.61 mm
- Arm required centerline distance at worst case:
  250.00 mm
- TCP_RADIUS events: 0
- Minimum TCP distance: 1098.61 mm

## Shape

- Target layer-integrated volume: 22300.000 mm³
- Deposited volume: 22348.071 mm³
- Intersection volume: 22285.272 mm³
- Underfill volume: 14.728 mm³
- Overfill volume: 62.799 mm³
- Coverage: 99.93%
- Underfill: 0.07%
- Overfill: 0.28%
- IoU: 99.65%
- Failed layers: 0 / 2

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
