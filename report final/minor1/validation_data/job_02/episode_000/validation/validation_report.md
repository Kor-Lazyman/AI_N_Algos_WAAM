# WAAM Validator Report

## Overall Result

**PASS**

- WAAM Validator version: 1.0.1

## Input Summary

- Directory: `C:\Users\lazzyman\Desktop\AINalgos2\version 1.0.2\AInalgos2-main\Minor\result\training\minor_40updates_20261018_152213\validation\step_00001024\job_02\episode_000\input`
- Trajectory rows: 64
- Target watertight: True

## Schedule

- Makespan: 182.07 s
- R1: completion 182.07 s; Deposition 66.60 s; Travel 20.54 s; Wait 94.93 s
- R2: completion 182.07 s; Deposition 87.95 s; Travel 20.54 s; Wait 73.58 s
- R3: completion 182.07 s; Deposition 0.00 s; Travel 0.00 s; Wait 182.07 s

## Robot XY Reach

- Passed: True
- R1: max XY distance 1176.97 / 2500.00 mm; XY margin 1323.03 mm; violating points 0
- R2: max XY distance 1181.20 / 2500.00 mm; XY margin 1318.80 mm; violating points 0
- R3: max XY distance 0.00 / 2500.00 mm; XY margin 2500.00 mm; violating points 0

## Collision

- Arm Envelope events: 0
- Minimum Arm Envelope safety margin: 442.73 mm
- Arm centerline distance at worst case:
  692.73 mm
- Arm required centerline distance at worst case:
  250.00 mm
- TCP_RADIUS events: 0
- Minimum TCP distance: 692.73 mm

## Shape

- Target layer-integrated volume: 8000.000 mm³
- Deposited volume: 8006.450 mm³
- Intersection volume: 7984.876 mm³
- Underfill volume: 15.113 mm³
- Overfill volume: 21.574 mm³
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
