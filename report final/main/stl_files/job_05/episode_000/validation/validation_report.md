# WAAM Validator Report

## Overall Result

**PASS**

- WAAM Validator version: 1.0.1

## Input Summary

- Directory: `C:\Users\lazzyman\Desktop\AINalgos2\version 1.0.2\AInalgos2-main\results\layer_evaluation\stl_files_20261017_trained_model_runtime\job_05\episode_000\input`
- Trajectory rows: 3712
- Target watertight: True

## Schedule

- Makespan: 9619.63 s
- R1: completion 9619.63 s; Deposition 3750.99 s; Travel 1002.35 s; Wait 4866.29 s
- R2: completion 9619.63 s; Deposition 1431.36 s; Travel 963.58 s; Wait 7224.69 s
- R3: completion 9619.63 s; Deposition 1492.08 s; Travel 979.26 s; Wait 7148.29 s

## Robot XY Reach

- Passed: True
- R1: max XY distance 1461.92 / 1500.00 mm; XY margin 38.08 mm; violating points 0
- R2: max XY distance 1497.48 / 1500.00 mm; XY margin 2.52 mm; violating points 0
- R3: max XY distance 1476.60 / 1500.00 mm; XY margin 23.40 mm; violating points 0

## Collision

- Arm Envelope events: 0
- Minimum Arm Envelope safety margin: 641.60 mm
- Arm centerline distance at worst case:
  891.60 mm
- Arm required centerline distance at worst case:
  250.00 mm
- TCP_RADIUS events: 0
- Minimum TCP distance: 891.60 mm

## Shape

- Target layer-integrated volume: 636120.000 mm³
- Deposited volume: 638325.256 mm³
- Intersection volume: 634918.199 mm³
- Underfill volume: 1201.801 mm³
- Overfill volume: 3407.055 mm³
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
