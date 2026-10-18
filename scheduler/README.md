기본 scheduler는 충돌 예측 후 국소 대피·재검사를 수행하는 `local-repair` 방식입니다. 새 실행법과 제약은 [README_LOCAL_REPAIR.md](README_LOCAL_REPAIR.md)를 확인하세요. 아래 내용은 기존 `home-tours` 방식의 기록입니다.

# scheduler

학습된 minor_2는 고정하고, PPO가 작업 순서와 대기만 학습하는 두 번째 모델입니다.
`scheduler`는 `minor_2`, `environment`와 같은 부모 폴더에 둡니다. 기존 `waam` Conda 환경을 사용합니다.

현재 검증 실행은 [compact_40updates_v2](result/compact_40updates_v2/RESULTS.md)입니다. CUDA 40회/2,560 step 학습과 전체 validation 6개가 완료됐습니다. 모두 Validator를 통과했지만 전체 makespan은 원본보다 늘어, 성능 개선 모델로 확정하지 않았습니다.

## 실행 구조

1. `planner.py`가 지정한 minor_2 ZIP을 실제로 로드하고 가중치를 고정합니다.
2. 저장된 평가의 모델 SHA-256과 입력 STL/config 해시를 확인합니다. ZIP 메타데이터가 달라 모델 해시가 다르면 정책 텐서 및 관측/행동 공간의 정확한 일치를 확인합니다. 레이어마다 정책의 deterministic action을 다시 추론해 저장된 action과 일치하는지도 검사합니다.
3. 원본 적층선의 끝점과 로봇 배정은 그대로 둡니다. 연결되거나 가까운(간격 80 mm 이하) 적층선을 길이 기준 작업 묶음으로 나눕니다.
4. scheduler PPO가 현재 실행 가능한 작업 또는 WAIT를 선택합니다. 실행 중인 다른 로봇은 계속 움직입니다.
5. 완성된 전체 STL의 trajectory를 원본과 대조하고 공식 Validator로 검증합니다.

기존 평가에서 생성한 planner 관측 상태를 사용하므로, 스케줄링 결과가 minor_2의 다음 action을 바꾸지 않습니다. 이 버전은 두 정책을 분리해 스케줄링 효과를 측정합니다.

## action / observation / reward

- 1 step = 작업 묶음 1개 예약 또는 다음 로봇 완료 시점까지 WAIT.
- Discrete(14): 0=다음 작업 완료까지 WAIT, 1~4=로봇1의 후보, 5~8=로봇2의 후보, 9~12=로봇3의 후보, 13=짧은 WAIT.
- 짧은 WAIT는 다음 완료까지 남은 시간의 10%(최소 1초, 최대 10초)만큼 기다린 뒤 충돌 후보를 다시 검사합니다. 출발 구간만 겹칠 때 작업 전체가 끝날 때까지 기다리는 것을 피할 수 있습니다.
- 후보는 각 로봇의 남은 작업 목록에서 앞/중간/뒤 위치를 고르게 선택합니다. 같은 로봇의 작업 순서를 바꿀 수 있으며 로봇 배정은 바꾸지 않습니다.
- 관측: 현재 시간, 진행률, 각 로봇의 남은 실행 시간, 남은 작업 수, 후보의 시작/끝/중심 좌표, 이동 포함 소요시간, 적층 시간, 유효 action 마스크.
- Actor/Critic: 별도 128→128 MLP, PPO. 충돌로 차단된 action은 추론과 PPO 학습 양쪽에서 확률 0으로 마스킹합니다.
- 보상: `이번 예약의 적층시간 / 전체 적층시간 - 경과시간 / 원본 레이어시간`.
- 레이어 완료 시 추가: `10 × 평균 적층활용률 × 원본 레이어시간 / scheduler 레이어시간`.
- 안전한 작업도 대기도 불가능하면 실패(-10). 충돌 경로를 그대로 실행하거나 레이어 전체를 자동 직렬화하지 않습니다.

충돌 감지는 규칙 기반 공식 Validator가 담당하고, PPO는 그 결과로 허용된 후보 중 실행 순서와 WAIT를 선택합니다. WAIT는 실행 중인 로봇이 끝날 때까지 home에서 대기합니다. 각 작업 묶음은 home으로 복귀하므로 이동 오버헤드가 있습니다. 첫 버전의 명시적인 제한이며, 반드시 원본 minor_2와 미학습 scheduler 양쪽을 비교합니다. 매 레이어의 종료 장벽은 유지됩니다.

## 계획 준비

PowerShell에서 scheduler 폴더로 이동한 뒤 실행합니다. 아래 `$run`은 현재 고정할 minor_2 학습 결과입니다.

```powershell
$py = 'C:\Users\lazzyman\anaconda3\envs\waam\python.exe'
$run = '..\minor_2\result\training\reward_only_40updates_20261018_155838'
& $py planner.py --model "$run\ppo_model.zip" --evaluation "$run\comparison\original_stl_files_after" --output plans\train_compact --layers-per-shape 3 --device cuda
& $py planner.py --model "$run\ppo_model.zip" --evaluation "$run\validation\step_00002560" --output plans\validation_compact --device cuda
```

pilot은 학습 STL 6개에서 처음/중간/마지막 레이어 최대 3개씩을 사용합니다. 전체 레이어 학습은 새 폴더에 `--layers-per-shape 0`으로 준비합니다. validation은 학습 데이터와 STL 해시가 겹치지 않는 전체 형상을 사용합니다. 기존 결과 폴더는 덮어쓰지 않습니다.

저장된 평가가 없는 새 입력은 `--evaluation` 대신 `--stl-dir`을 사용합니다. 각 형상 폴더에 `target.stl`, `config.yaml`을 둡니다. 이 경로는 minor_2를 직접 실행하고 공식 Validator를 통과한 원본 계획을 저장한 뒤 scheduler 계획을 생성합니다.

```powershell
& $py planner.py --model "$run\ppo_model.zip" --stl-dir '..\test' --output plans\new_test --device cuda
& $py evaluate.py --model result\compact_40updates_v2\scheduler_final.zip --plans plans\new_test --output result\new_test --device cuda
```

## 학습 및 평가

```powershell
& $py train.py --train-plans plans\train_compact --validation-plans plans\validation_compact --updates 40 --n-steps 64 --device cuda
& $py -m tensorboard.main --logdir result\compact_40updates_v2\tensorboard --port 6006
& $py evaluate.py --model result\compact_40updates_v2\scheduler_final.zip --plans plans\validation_compact --output result\separate_evaluation --device cuda
```

학습은 early stopping 없이 40 rollout update(2,560 scheduler step)를 수행합니다. minor_2는 학습하지 않으며 scheduler만 CUDA에서 업데이트합니다. 기하와 충돌 검사는 CPU입니다. 초기·최종 모델, TensorBoard, 원본 대비/학습 전후 비교, 각 STL의 전체 trajectory, 공식 Validator 결과, 간트 HTML이 저장됩니다. validation은 모델 파라미터 업데이트에 사용하지 않습니다.

## 검증

`python selfcheck.py --plans plans\validation_compact`은 실제 레이어의 시간 순서, action 마스크, 적층선 보존, 충돌 검증, 모델 저장/로드를 확인합니다. 각 전체 형상 평가에서는 원본 trajectory와 적층 구간/로봇 배정의 multiset을 비교한 뒤 공식 Validator를 실행합니다.

`python diagnose_layers.py --plans plans\train_compact --run result\compact_40updates_v2`는 학습 형상별 첫 레이어에서 scheduler 학습 전후의 makespan과 동시 적층 시간을 비교합니다. 일부 레이어만 검사하므로 전체 STL Validator 통과로 표시하지 않습니다.

