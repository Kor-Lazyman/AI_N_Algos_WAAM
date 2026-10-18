# WAAM Validator Report

## Overall Result

**PASS**

- WAAM Validator version: 1.0.1

## Input Summary

- Directory: `C:\Users\lazzyman\Desktop\AINalgos2\version 1.0.2\AInalgos2-main\minor_2\result\training\reward_only_40updates_20261018_155838\comparison\original_stl_files_after\job_00\episode_000\input`
- Trajectory rows: 3212
- Target watertight: True

## Schedule

- Makespan: 2450.16 s
- R1: completion 2450.16 s; Deposition 391.27 s; Travel 144.51 s; Wait 1914.38 s
- R2: completion 2450.16 s; Deposition 979.55 s; Travel 244.71 s; Wait 1225.90 s
- R3: completion 2450.16 s; Deposition 515.49 s; Travel 174.63 s; Wait 1760.04 s

## Robot XY Reach

- Passed: True
- R1: max XY distance 1495.38 / 1500.00 mm; XY margin 4.62 mm; violating points 0
- R2: max XY distance 1475.19 / 1500.00 mm; XY margin 24.81 mm; violating points 0
- R3: max XY distance 1418.42 / 1500.00 mm; XY margin 81.58 mm; violating points 0

## Collision

- Arm Envelope events: 0
- Minimum Arm Envelope safety margin: 640.82 mm
- Arm centerline distance at worst case:
  890.82 mm
- Arm required centerline distance at worst case:
  250.00 mm
- TCP_RADIUS events: 0
- Minimum TCP distance: 890.82 mm

## Shape

- Target layer-integrated volume: 116840.445 mm³
- Deposited volume: 119003.920 mm³
- Intersection volume: 116840.445 mm³
- Underfill volume: 0.000 mm³
- Overfill volume: 2163.474 mm³
- Coverage: 100.00%
- Underfill: 0.00%
- Overfill: 1.85%
- IoU: 98.18%
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
