# WAAM Validator Report

## Overall Result

**PASS**

- WAAM Validator version: 1.0.1

## Input Summary

- Directory: `C:\Users\lazzyman\Desktop\AINalgos2\version 1.0.2\AInalgos2-main\results\layer_evaluation\stl_files_20261017_trained_model_runtime\job_02\episode_000\input`
- Trajectory rows: 3827
- Target watertight: True

## Schedule

- Makespan: 4070.59 s
- R1: completion 4070.59 s; Deposition 1058.08 s; Travel 273.64 s; Wait 2738.87 s
- R2: completion 4070.59 s; Deposition 976.59 s; Travel 313.73 s; Wait 2780.28 s
- R3: completion 4070.59 s; Deposition 1117.89 s; Travel 330.67 s; Wait 2622.04 s

## Robot XY Reach

- Passed: True
- R1: max XY distance 1485.13 / 1500.00 mm; XY margin 14.87 mm; violating points 0
- R2: max XY distance 1499.50 / 1500.00 mm; XY margin 0.50 mm; violating points 0
- R3: max XY distance 1497.61 / 1500.00 mm; XY margin 2.39 mm; violating points 0

## Collision

- Arm Envelope events: 0
- Minimum Arm Envelope safety margin: 577.45 mm
- Arm centerline distance at worst case:
  827.45 mm
- Arm required centerline distance at worst case:
  250.00 mm
- TCP_RADIUS events: 0
- Minimum TCP distance: 827.45 mm

## Shape

- Target layer-integrated volume: 197274.975 mm³
- Deposited volume: 200714.996 mm³
- Intersection volume: 197274.956 mm³
- Underfill volume: 0.018 mm³
- Overfill volume: 3440.040 mm³
- Coverage: 100.00%
- Underfill: 0.00%
- Overfill: 1.74%
- IoU: 98.29%
- Failed layers: 0 / 6

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
