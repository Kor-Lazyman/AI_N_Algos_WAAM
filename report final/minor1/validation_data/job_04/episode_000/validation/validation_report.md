# WAAM Validator Report

## Overall Result

**PASS**

- WAAM Validator version: 1.0.1

## Input Summary

- Directory: `C:\Users\lazzyman\Desktop\AINalgos2\version 1.0.2\AInalgos2-main\Minor\result\training\minor_40updates_20261018_152213\validation\step_00001024\job_04\episode_000\input`
- Trajectory rows: 127
- Target watertight: True

## Schedule

- Makespan: 256.98 s
- R1: completion 256.98 s; Deposition 128.22 s; Travel 21.31 s; Wait 107.46 s
- R2: completion 256.98 s; Deposition 85.69 s; Travel 21.13 s; Wait 150.17 s
- R3: completion 256.98 s; Deposition 8.74 s; Travel 20.61 s; Wait 227.64 s

## Robot XY Reach

- Passed: True
- R1: max XY distance 1180.65 / 2500.00 mm; XY margin 1319.35 mm; violating points 0
- R2: max XY distance 1191.20 / 2500.00 mm; XY margin 1308.80 mm; violating points 0
- R3: max XY distance 1181.94 / 2500.00 mm; XY margin 1318.06 mm; violating points 0

## Collision

- Arm Envelope events: 0
- Minimum Arm Envelope safety margin: 297.24 mm
- Arm centerline distance at worst case:
  547.24 mm
- Arm required centerline distance at worst case:
  250.00 mm
- TCP_RADIUS events: 0
- Minimum TCP distance: 547.24 mm

## Shape

- Target layer-integrated volume: 11264.000 mm³
- Deposited volume: 11283.261 mm³
- Intersection volume: 11252.218 mm³
- Underfill volume: 11.782 mm³
- Overfill volume: 31.043 mm³
- Coverage: 99.90%
- Underfill: 0.10%
- Overfill: 0.28%
- IoU: 99.62%
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
