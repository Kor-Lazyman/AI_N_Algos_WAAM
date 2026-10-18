# Minor 실행 결과

2026-10-18. 새 두 네트워크의 장기 학습 성능과 스케줄러 자체의 효과를 구분해 기록합니다.

## 동일 원본 정책 행동에 대한 전체 STL 비교

원본 1.0.2의 1,024-step 모델이 결정한 행동을 그대로 재생했습니다. STL 위치는 고정했고, 생성한 적층 선분도 모두 보존했습니다. 따라서 다음 수치는 **스케줄러 개선 효과**이며 새 위치·경로 PPO의 학습 성능은 아닙니다.

| STL | 원본 makespan (초) | Minor makespan (초) | 단축률 | IoU 전 → 후 | 공식 Validator |
|---|---:|---:|---:|---|---|
| train/01, 6 layers | 2577.59 | 2088.92 | 18.96% | 0.981820 → 0.981820 | 양쪽 PASS |
| train/02, 8 layers | 5311.78 | 4166.59 | 21.56% | 0.980331 → 0.980331 | 양쪽 PASS |

| STL | 전체 로봇 대기 합, 전 → 후 (초) | 평균 D 활용률, 전 → 후 | 2대 이상 동시 D, 전 → 후 (초) |
|---|---:|---:|---:|
| train/01 | 5155.18 → 3998.85 | 24.44% → 30.16% | 0 → 0 |
| train/02 | 10623.57 → 7911.81 | 25.08% → 31.97% | 0 → 169.52 |

두 STL 모두 로봇 세 대가 작업에 참여했습니다. 3대가 모두 동시에 적층한 시간은 두 사례에서 0초입니다. train/01의 개선은 주로 비적층 이동 감소에서 나왔으며, train/02에는 실제 2대 동시 적층 구간이 생겼습니다. 원본 arm/TCP 충돌 설정은 변경하지 않았습니다.

계산시간은 이 실행에서 원본/Minor 각각 train/01 약 4.73/12.72초, train/02 약 10.17/24.10초였습니다. 후보 탐색으로 계산시간은 늘었으며, 위 makespan은 로봇의 적층 스케줄 시간입니다. 다른 검증 작업과 병행한 실행이므로 계산시간은 정밀 성능 벤치마크가 아닙니다.

- [전체 수치](result/benchmark/full_01_02/comparison.json)
- train/01 [원본 간트](result/benchmark/full_01_02/job_00_01/before_gantt.html) · [Minor 간트](result/benchmark/full_01_02/job_00_01/after_gantt.html)
- train/02 [원본 간트](result/benchmark/full_01_02/job_01_02/before_gantt.html) · [Minor 간트](result/benchmark/full_01_02/job_01_02/after_gantt.html)
- [train/02 Minor trajectory](result/benchmark/full_01_02/job_01_02/after/input/trajectory.csv) · [적층 STL](result/benchmark/full_01_02/job_01_02/after/deposited.stl)

## 두 네트워크 CUDA 통합 실행

`result/integration/dual_cuda_verified/`에서 경로 PPO 2 layer step, 위치 PPO 2 STL episode 교대 학습을 완료했습니다. 경로 정책은 원본 모델 가중치에서 시작했고 두 네트워크 모두 CUDA를 사용했습니다. 학습 입력은 train/01, validation은 00_sample이었습니다. 전체 6+6 데이터셋을 학습한 실행은 아닙니다.

- validation: PASS, IoU 약 0.988873, makespan 약 43.1초.
- 최종/최선/체크포인트 모델을 경로·위치 쌍으로 저장했고 해시 manifest를 생성했습니다.
- [학습 설정·완료 상태](result/integration/dual_cuda_verified/training.json)
- [STL별 위치 보상 로그](result/integration/dual_cuda_verified/placement_trace.jsonl)
- [경로 모델](result/integration/dual_cuda_verified/ppo_model.zip) · [위치 모델](result/integration/dual_cuda_verified/placement_model.zip)

저장된 모델 쌍을 별도 평가 프로세스에서 다시 읽었습니다. 위치 네트워크가 train/01 전체에 **X −10.3789mm, Y +9.0424mm, Z 0mm**를 한 번 적용했고, 6개 레이어 전체가 동일하게 이동했습니다. 전체 Validator PASS, IoU 0.981804, makespan 2088.973초를 확인했습니다.

- [이동 메타데이터](result/integration/dual_reload_eval/job_00/episode_000/input/placement.json)
- [이동된 target STL](result/integration/dual_reload_eval/job_00/episode_000/input/target.stl)
- [재로딩 평가](result/integration/dual_reload_eval/evaluation.json)

이 짧은 학습은 실행 연결을 검증한 것이며 위치 최적화의 수렴이나 일반화 성능을 입증하지 않습니다.

## 핵심 검사

전용 테스트 6개 통과: D와 이동 시간 구분, IoU 0.9 보상 경계·시간/활용률 방향, 전 레이어 동일 평행 이동 및 작업 공간 제한, STL별 위치 보상 격리, 적층 선분 보존과 원본 스케줄 시간 상한, PASS 우선·짧은 makespan 모델 선택.

`result/integration/dual_cuda_smoke/`는 초기에 모델 선택 변수 충돌을 발견한 실패 실행입니다. 수정 후 완료 결과는 `dual_cuda_verified/`를 기준으로 봅니다.
