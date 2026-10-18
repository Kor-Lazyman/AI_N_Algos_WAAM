# WAAM Validator Report

## Overall Result

**PASS**

- WAAM Validator version: 1.0.1

## Input Summary

- Directory: `C:\Users\lazzyman\Desktop\AINalgos2\version 1.0.2\AInalgos2-main\minor_2\result\training\reward_only_40updates_20261018_155838\validation\step_00000256\job_02\episode_000\input`
- Trajectory rows: 68
- Target watertight: True

## Schedule

- Makespan: 222.35 s
- R1: completion 222.35 s; Deposition 41.50 s; Travel 21.40 s; Wait 159.45 s
- R2: completion 222.35 s; Deposition 80.02 s; Travel 21.23 s; Wait 121.10 s
- R3: completion 222.35 s; Deposition 36.69 s; Travel 21.51 s; Wait 164.14 s

## Robot XY Reach

- Passed: True
- R1: max XY distance 1188.27 / 2500.00 mm; XY margin 1311.73 mm; violating points 0
- R2: max XY distance 1190.18 / 2500.00 mm; XY margin 1309.82 mm; violating points 0
- R3: max XY distance 1233.92 / 2500.00 mm; XY margin 1266.08 mm; violating points 0

## Collision

- Arm Envelope events: 0
- Minimum Arm Envelope safety margin: 859.36 mm
- Arm centerline distance at worst case:
  1109.36 mm
- Arm required centerline distance at worst case:
  250.00 mm
- TCP_RADIUS events: 0
- Minimum TCP distance: 1109.36 mm

## Shape

- Target layer-integrated volume: 8000.000 mm³
- Deposited volume: 8006.447 mm³
- Intersection volume: 7984.876 mm³
- Underfill volume: 15.113 mm³
- Overfill volume: 21.571 mm³
- Coverage: 99.81%
- Underfill: 0.19%
- Overfill: 0.27%
- IoU: 99.54%
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
