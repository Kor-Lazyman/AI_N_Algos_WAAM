# WAAM Validator Report

## Overall Result

**PASS**

- WAAM Validator version: 1.0.1

## Input Summary

- Directory: `C:\Users\lazzyman\Desktop\AINalgos2\version 1.0.2\AInalgos2-main\minor_2\result\training\reward_only_40updates_20261018_155838\comparison\original_stl_files_after\job_03\episode_000\input`
- Trajectory rows: 32441
- Target watertight: True

## Schedule

- Makespan: 69364.06 s
- R1: completion 69364.06 s; Deposition 9325.47 s; Travel 1257.74 s; Wait 58780.85 s
- R2: completion 69364.06 s; Deposition 31809.12 s; Travel 2049.73 s; Wait 35505.22 s
- R3: completion 69364.06 s; Deposition 23354.97 s; Travel 1567.03 s; Wait 44442.06 s

## Robot XY Reach

- Passed: True
- R1: max XY distance 1499.81 / 1500.00 mm; XY margin 0.19 mm; violating points 0
- R2: max XY distance 1499.16 / 1500.00 mm; XY margin 0.84 mm; violating points 0
- R3: max XY distance 1437.16 / 1500.00 mm; XY margin 62.84 mm; violating points 0

## Collision

- Arm Envelope events: 0
- Minimum Arm Envelope safety margin: 533.41 mm
- Arm centerline distance at worst case:
  783.41 mm
- Arm required centerline distance at worst case:
  250.00 mm
- TCP_RADIUS events: 0
- Minimum TCP distance: 783.41 mm

## Shape

- Target layer-integrated volume: 6661016.843 mm³
- Deposited volume: 6678528.510 mm³
- Intersection volume: 6661016.813 mm³
- Underfill volume: 0.029 mm³
- Overfill volume: 17511.696 mm³
- Coverage: 100.00%
- Underfill: 0.00%
- Overfill: 0.26%
- IoU: 99.74%
- Failed layers: 0 / 50

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
