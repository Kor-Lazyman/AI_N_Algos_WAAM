# 레이어 계산 병렬 처리 검토

## 결론

가능하지만, **동시에 여러 레이어를 계산**하는 것과 **여러 레이어를 동시에 적층**하는 것은 다르다. 한 STL의 실제 적층은 이전 레이어 형상·높이와 같은 로봇/충돌 일정에 의존하므로 레이어 순서를 유지한다. 보고 계산에서 가장 안전한 병렬 단위는 독립 STL/job의 evaluation이다.

## 권장 병렬 단위

1. **서로 다른 STL 평가:** process worker마다 PPO 모델을 한 번 로드하고 STL/config를 독립 초기화한다. worker별 출력 폴더와 seed를 분리한다. 여러 job의 makespan/Validator·trajectory/Gantt를 병렬 계산한다. Python geometry·slice·Validator 처리는 CPU 비중이 커서 thread보다 process pool이 유리하다.
2. **학습 rollout:** 독립 STL episode 여러 개를 `SubprocVecEnv` 등으로 표본화하고 한 PPO optimizer에서 동기식으로 batch update할 수 있다. 1 worker부터 2/4 worker까지 CPU·RAM·GPU peak 및 Validator contention을 재서 늘린다. 각 worker는 env/scenario를 따로 만들고 저장 모델은 read-only로 쓴다.
3. **같은 STL의 다음 레이어:** trajectory 생성·geometry 사전계산은 미리 준비할 수 있지만, PPO episode state와 실제 적층 완료 순서는 유지한다. 아직 결정되지 않은 이전 레이어 정책 선택·collision 상태를 공유하는 live trajectory까지 무작정 thread화하지 않는다.

## 현재 병목과 주의점

- Root/Minor/Beta PPO 코드는 기본적으로 single-env PPO rollout이다. 학습 vectorization은 코드 변경이 필요하다.
- 같은 `gym.Env`, `VecEnv`, PPO optimizer, Validator output directory를 여러 thread가 공유하지 않는다. 환경 mutable state와 생성 파일을 덮어쓸 수 있다.
- CUDA는 policy forward/backward만 맡고 STL slicing·collision geometry·Validator는 CPU다. worker 수를 높이면 GPU를 더 쓰기보다 CPU/RAM 또는 Validator가 병목일 수 있다.
- 6개의 큰 STL을 동시에 process하면 STL mesh와 geometry cache가 worker마다 복제돼 메모리 급증 가능성이 있다. 우선 2 workers, task별 output 경로, 성능/메모리 기록으로 시작한다.
- GPU tensor inference를 worker마다 따로 실행하는 것보다 parent process가 policy를 공유·배치 inference하고 CPU geometry workers에 action을 보내는 구조가 GPU memory 측면에서 효율적이다. 단, 편의성과 격리를 우선하면 worker별 read-only model copy도 가능하다.

## 다음 구현 권고안

먼저 `evaluate_layers.py`/scheduler evaluator에 `--workers 1|2|4`를 넣어 서로 다른 STL job 단위 process pool을 제공한다. 기존 single-worker 경로와 JSON schema를 그대로 유지하고, worker별 run output을 합쳐 결과 순서를 입력 순서대로 정렬한다. 계산속도를 실제 측정한 다음 학습 PPO에 `--n-envs` vector rollout을 추가한다. 이는 순수 thread 분리보다 process-based CPU parallel evaluation이다.

레이어를 한꺼번에 생성한다고 물리적 적층 간격·다른 레이어 작업과의 충돌을 없애지는 않는다. 동일 STL에서 layer 간 실제 동시 적층을 허용하려면 재료 경화, Z 높이, 도달범위, 노즐 충돌, 순서 제약을 포함한 별도 3D scheduler가 먼저 필요하다.
