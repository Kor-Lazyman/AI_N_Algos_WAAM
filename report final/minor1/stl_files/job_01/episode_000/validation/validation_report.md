# WAAM Validator Report

## Overall Result

**PASS**

- WAAM Validator version: 1.0.1

## Input Summary

- Directory: `C:\Users\lazzyman\Desktop\AINalgos2\version 1.0.2\AInalgos2-main\Minor\result\layer_evaluation\training_stl_validator_20261018\job_01\episode_000\input`
- Trajectory rows: 8649
- Target watertight: True

## Schedule

- Makespan: 4158.50 s
- R1: completion 4158.50 s; Deposition 1310.03 s; Travel 188.73 s; Wait 2659.73 s
- R2: completion 4158.50 s; Deposition 588.58 s; Travel 170.42 s; Wait 3399.50 s
- R3: completion 4158.50 s; Deposition 2104.55 s; Travel 209.84 s; Wait 1844.11 s

## Robot XY Reach

- Passed: True
- R1: max XY distance 1394.86 / 1500.00 mm; XY margin 105.14 mm; violating points 0
- R2: max XY distance 1467.26 / 1500.00 mm; XY margin 32.74 mm; violating points 0
- R3: max XY distance 1386.61 / 1500.00 mm; XY margin 113.39 mm; violating points 0

## Collision

- Arm Envelope events: 0
- Minimum Arm Envelope safety margin: 2.50 mm
- Arm centerline distance at worst case:
  252.50 mm
- Arm required centerline distance at worst case:
  250.00 mm
- TCP_RADIUS events: 0
- Minimum TCP distance: 252.50 mm

## Shape

- Target layer-integrated volume: 254007.537 mm³
- Deposited volume: 259104.695 mm³
- Intersection volume: 254007.529 mm³
- Underfill volume: 0.008 mm³
- Overfill volume: 5097.165 mm³
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
