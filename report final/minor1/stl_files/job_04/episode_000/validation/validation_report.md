# WAAM Validator Report

## Overall Result

**PASS**

- WAAM Validator version: 1.0.1

## Input Summary

- Directory: `C:\Users\lazzyman\Desktop\AINalgos2\version 1.0.2\AInalgos2-main\Minor\result\layer_evaluation\training_stl_validator_20261018\job_04\episode_000\input`
- Trajectory rows: 262138
- Target watertight: True

## Schedule

- Makespan: 184433.40 s
- R1: completion 184433.40 s; Deposition 133248.19 s; Travel 6870.11 s; Wait 44315.10 s
- R2: completion 184433.40 s; Deposition 90300.35 s; Travel 6788.56 s; Wait 87344.49 s
- R3: completion 184433.40 s; Deposition 141581.35 s; Travel 7286.84 s; Wait 35565.20 s

## Robot XY Reach

- Passed: True
- R1: max XY distance 1499.96 / 1500.00 mm; XY margin 0.04 mm; violating points 0
- R2: max XY distance 1472.17 / 1500.00 mm; XY margin 27.83 mm; violating points 0
- R3: max XY distance 1499.71 / 1500.00 mm; XY margin 0.29 mm; violating points 0

## Collision

- Arm Envelope events: 0
- Minimum Arm Envelope safety margin: 0.01 mm
- Arm centerline distance at worst case:
  250.01 mm
- Arm required centerline distance at worst case:
  250.00 mm
- TCP_RADIUS events: 0
- Minimum TCP distance: 250.01 mm

## Shape

- Target layer-integrated volume: 31086146.308 mm³
- Deposited volume: 31301261.269 mm³
- Intersection volume: 31086142.798 mm³
- Underfill volume: 3.511 mm³
- Overfill volume: 215118.465 mm³
- Coverage: 100.00%
- Underfill: 0.00%
- Overfill: 0.69%
- IoU: 99.31%
- Failed layers: 0 / 350

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
