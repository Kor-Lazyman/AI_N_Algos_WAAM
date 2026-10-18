# Beta 검증 결과

2026-10-18 실행. 이 결과는 `tools.plan`의 규칙 기반 좌표 행동으로 영역 배정·동시 스케줄러·공식 WAAM Validator를 검증한 결과이며, 학습된 PPO의 성능이 아닙니다.

| 입력 | 계산시간 (초) | Makespan (초) | Validator | 3대 동시 적층 (초) | 2대 이상 동시 적층 (초) |
|---|---:|---:|---|---:|---:|
| 분리된 3개 영역 데모 | 1.262 | 251.172 | PASS | 82.916 | 91.227 |
| 기존 train/01, 6개 레이어 | 92.480 | 2104.942 | PASS | 0 | 0 |

동시 적층 시간은 이동을 제외한 D 상태만 집계합니다. train/01은 현재 arm/TCP 충돌 제약 아래 동시 작업 조합을 찾지 못해 순차 경로로 압축했습니다. 따라서 영역을 나누더라도 모든 형상에서 3대 동시 적층을 보장하지 않습니다. train/01 계산시간은 CUDA 연결 시험과 병행 실행한 측정값입니다.

## 저장 결과

- 데모: [측정값](result/plans/demo_final/beta_metrics.json), [간트차트](result/plans/demo_final/gantt/index.html), [영역](result/plans/demo_final/territories.html), [trajectory](result/plans/demo_final/job_00/episode_000/input/trajectory.csv), [적층 STL](result/plans/demo_final/job_00/episode_000/deposited.stl)
- 기존 train/01: [측정값](result/plans/train_01_compacted/beta_metrics.json), [간트차트](result/plans/train_01_compacted/gantt/index.html), [trajectory](result/plans/train_01_compacted/job_00/episode_000/input/trajectory.csv), [적층 STL](result/plans/train_01_compacted/job_00/episode_000/deposited.stl)

## 코드 및 학습 연결 검증

`python -B -m unittest discover -s tests -q`: 6개 테스트 통과. 최근접 도달 가능 영역 배정, 직접 좌표 행동, 실제 Validator 통과, 좌표 정밀도, 충돌 시 다른 작업 선택, 순차 경로 압축을 확인했습니다.

`result/integration/direct_cuda_final/`에서 CUDA PPO 2-step 연결 시험을 완료했습니다. 이는 학습 완료 모델이 아닙니다. 이 시험 모델의 validation은 FAIL이며 IoU는 약 0.003445입니다. Beta의 행동·관측 공간이 기존 모델과 달라 새로 학습해야 합니다. 사용 방법과 제약은 [README](README.md)를 확인하세요.