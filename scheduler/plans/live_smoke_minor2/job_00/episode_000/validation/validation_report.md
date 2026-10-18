# WAAM Validator Report

## Overall Result

**PASS**

- WAAM Validator version: 1.0.1

## Input Summary

- Directory: `C:\Users\lazzyman\Desktop\AINalgos2\version 1.0.2\AInalgos2-main\scheduler\plans\live_smoke_minor2\job_00\episode_000\input`
- Trajectory rows: 48
- Target watertight: True

## Schedule

- Makespan: 82.83 s
- R1: completion 82.83 s; Deposition 10.06 s; Travel 21.11 s; Wait 51.65 s
- R2: completion 82.83 s; Deposition 0.07 s; Travel 20.51 s; Wait 62.25 s
- R3: completion 82.83 s; Deposition 10.00 s; Travel 21.08 s; Wait 51.75 s

## Robot XY Reach

- Passed: True
- R1: max XY distance 1200.60 / 2500.00 mm; XY margin 1299.40 mm; violating points 0
- R2: max XY distance 1161.91 / 2500.00 mm; XY margin 1338.09 mm; violating points 0
- R3: max XY distance 1200.70 / 2500.00 mm; XY margin 1299.30 mm; violating points 0

## Collision

- Arm Envelope events: 0
- Minimum Arm Envelope safety margin: 882.05 mm
- Arm centerline distance at worst case:
  1132.05 mm
- Arm required centerline distance at worst case:
  250.00 mm
- TCP_RADIUS events: 0
- Minimum TCP distance: 1132.05 mm

## Shape

- Target layer-integrated volume: 664.971 mm³
- Deposited volume: 672.454 mm³
- Intersection volume: 664.971 mm³
- Underfill volume: 0.000 mm³
- Overfill volume: 7.482 mm³
- Coverage: 100.00%
- Underfill: 0.00%
- Overfill: 1.13%
- IoU: 98.89%
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
