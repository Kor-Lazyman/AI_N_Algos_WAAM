# WAAM Validator Report

## Overall Result

**PASS**

- WAAM Validator version: 1.0.1

## Input Summary

- Directory: `C:\Users\lazzyman\Desktop\AINalgos2\version 1.0.2\AInalgos2-main\results\layer_evaluation\validation_stl_20261017_latest_runtime\job_01\episode_000\input`
- Trajectory rows: 173
- Target watertight: True

## Schedule

- Makespan: 586.20 s
- R1: completion 586.20 s; Deposition 227.84 s; Travel 42.84 s; Wait 315.52 s
- R2: completion 586.20 s; Deposition 111.42 s; Travel 43.28 s; Wait 431.49 s
- R3: completion 586.20 s; Deposition 116.41 s; Travel 44.40 s; Wait 425.38 s

## Robot XY Reach

- Passed: True
- R1: max XY distance 1221.81 / 2500.00 mm; XY margin 1278.19 mm; violating points 0
- R2: max XY distance 1221.81 / 2500.00 mm; XY margin 1278.19 mm; violating points 0
- R3: max XY distance 1228.98 / 2500.00 mm; XY margin 1271.02 mm; violating points 0

## Collision

- Arm Envelope events: 0
- Minimum Arm Envelope safety margin: 860.57 mm
- Arm centerline distance at worst case:
  1110.57 mm
- Arm required centerline distance at worst case:
  250.00 mm
- TCP_RADIUS events: 0
- Minimum TCP distance: 1110.57 mm

## Shape

- Target layer-integrated volume: 24000.000 mm³
- Deposited volume: 24037.169 mm³
- Intersection volume: 23988.218 mm³
- Underfill volume: 11.782 mm³
- Overfill volume: 48.951 mm³
- Coverage: 99.95%
- Underfill: 0.05%
- Overfill: 0.20%
- IoU: 99.75%
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
