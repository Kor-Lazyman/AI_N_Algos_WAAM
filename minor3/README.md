# minor3 — 레이어 경로와 충돌 지점 대피 동선을 함께 학습

두 PPO를 번갈아 학습한다. 경로 PPO는 minor_2 가중치로 초기화하지만 고정하지 않으며, 대피 PPO는 새로 학습한다. 두 정책의 목적은 **완성된 레이어의 makespan 최소화**다. 기존 minor_2 및 scheduler 파일·모델은 수정하지 않는다.

## 완료한 실행: joint_40updates

CUDA에서 early stopping 없이 40회 교대 업데이트를 완료했다. 경로 80 layer step, 대피 320 repair step이며 준비·학습·전후 평가를 포함해 2,401.21초(약 40분) 걸렸다. 저장된 두 actor를 다시 불러와 가중치가 변경됐음을 확인했다.

별도 validation STL 6개는 모두 경로를 완성하고 설정된 샘플 기반 충돌 검사를 통과했다. **합계 makespan은 학습 전 2,073.54초 → 학습 후 2,303.07초로 11.07% 증가했다.** 기존 minor_2의 2,089.44초보다도 10.22% 길다. 이번 짧은 학습으로 시간 단축이 입증되지는 않았다. IoU·전체 Validator는 실행하지 않았다.

- [상세 결과 및 로봇별 활용률](result/joint_40updates/RESULTS.md)
- [학습 전후 Gantt](result/joint_40updates/gantt_index.html)
- [최종 경로 모델](result/joint_40updates/path_final.zip), [최종 대피 모델](result/joint_40updates/avoidance_final.zip)
- [저장 모델 재검증](result/joint_40updates/verification.json)

추가로 학습 STL `05`의 layer `174`를 최종 두 정책으로 재생했다. D 선분 중간 중단은 4회 발생했으나 32회 수정 한도 안에 충돌을 해결하지 못했다. [XY 대피·복귀 그림](result/joint_40updates/mid_stroke_example/xy_detours.html)은 이 **미해결 과정의 진단용**이다. 완성 trajectory 대신 `partial_plan_UNRESOLVED.csv`로 저장했으며, 중간 계획 시간 528.32초를 완료 makespan으로 취급하지 않는다. 작은 validation 형상 6개의 완료가 큰 형상에서의 회피 성공을 보장하지 않는다.

```powershell
& $py report.py --run result\joint_40updates
& $py example.py --run result\joint_40updates --plans '..\scheduler\plans\train_compact' --shape 05 --layer 174 --output result\replay_05_layer174 --device cuda
```

이번 실행의 실시간 TensorBoard 주소는 `http://127.0.0.1:6010`이다. 서버를 다시 열 때는 아래 실행 예시의 logdir를 사용한다. 이미 존재하는 결과 폴더에는 덮어쓰지 않으므로 재학습 시 새 `--output`을 지정한다.

## 기존 방식과 달라진 동작

1. STL을 레이어로 슬라이싱한다.
2. 경로 PPO가 한 행동으로 레이어 전체의 적층 방향·간격·시작점·진행 순서·로봇 할당을 선택한다.
3. 세 로봇의 전체 경로를 동시에 시작하는 명목 스케줄을 만든다. 충돌 때문에 80/160 mm 작업 묶음으로 나누지 않는다. 원래 폴리곤·해치의 선분과 로봇별 경로 순서를 유지한다.
4. 가장 먼저 예상되는 충돌의 좌표와 시각을 찾는다.
5. 대피 PPO가 양보할 로봇, 대피 방향·거리, 대기 전략을 선택한다. 충돌 직전 안전한 시각까지 이동하고, 대피한 뒤 같은 좌표로 돌아와 그 지점에서 남은 경로를 이어간다.
6. 변경된 스케줄을 다시 검사하고 다음 예상 충돌을 수정한다. 충돌이 없어지거나 수리 횟수·시간 한계에 도달할 때까지 반복한다.

대피 시점이 D 선분 중간이면 CSV에는 중단 좌표가 새 행으로 들어간다. 이는 같은 적층선을 이어 그리기 위한 보간점이며, 다른 작업으로 재분할하거나 다른 로봇에게 넘기는 것이 아니다. 순서대로 모든 원래 적층선을 정확히 한 번씩 완성하는지 검사한다. 레이어 종료 시에는 home으로 복귀한다.

현재는 전체 미래 경로를 미리 수정하는 시뮬레이션 스케줄러다. 실제 로봇 통신·실시간 제어 코드는 포함하지 않는다. 충돌 검사는 기존 설정의 XY 팔 외피와 TCP 간격 모델을 사용한다. Z만 올리는 동작을 충돌 회피로 취급하지 않는다.

## 네트워크와 액션

경로 PPO는 기존과 같은 `MultiDiscrete([8,3,4,2,2,3,6])`이다. 1 step은 한 레이어 전체 경로 생성 및 현재 대피 정책으로 스케줄 완성이다. 입력 차원은 초기 가중치 호환을 위해 유지하고, 예전 IoU·품질 기준 입력 자리는 0으로 고정한다. IoU를 계산해서 넣지 않는다.

대피 PPO는 actor/critic 각각 128×128 MLP이고 이산 액션 28개를 사용한다.

- 충돌에 관련된 두 로봇 중 양보할 로봇 선택.
- 제자리 대기 또는 자기 base 방향 / 그 방향에 수직인 좌우 대피.
- 대피 거리 200 mm 또는 500 mm.
- 짧은 대기 후보(0/1/3/8/20/45초) 중 안전한 첫 후보 또는 다른 로봇들이 끝날 때까지 대기.

각 액션의 실행 전, 충돌 시각보다 0.5/2/6/16초 앞선 시점 순으로 안전한 중단점을 탐색한다. 대피→대기→복귀→중단했던 움직임의 나머지 구간을 검사한다. 안전한 후보가 없는 액션은 마스킹한다. **PPO가 학습하는 것은 이 후보 집합 안에서의 대피 로봇·동선·대기 전략 선택**이며, 자유로운 곡선의 모든 점을 출력하는 네트워크는 아니다. 복귀 후 전체 스케줄에서 새로 생기는 충돌은 다음 수정 단계에서 처리한다.

## 보상

`T_ref`는 STL 레이어 면적·비드 폭·속도·home 거리에 따른 고정 기준시간이며, 선택한 액션에 따라 달라지지 않는다.

```text
경로 PPO: r = -최종 makespan / T_ref
대피 PPO: r = -(수정 후 makespan - 수정 전 makespan) / T_ref
```

두 PPO 모두 gamma=1이다. 대피 보상의 합은 초기 makespan을 제외하면 최종 makespan의 음수와 같아진다. IoU 보상, Validator 통과 보상, 활용률 보상, 대피 거리 보너스는 없다.

적층 누락은 허용하지 않으며 충돌은 해결해야 하는 제약이다. 해결 불가·32회 수리 한계·시간 한계에서는 완료로 처리하지 않는다. 미완성 경로가 빠르다는 이유로 좋은 점수를 받지 않도록 `max(20×T_ref, 10×초기 병렬 makespan)`을 실패 목적 비용으로 사용한다. 이 값은 실제 완료 makespan으로 보고하지 않는다.

**IoU 계산과 전체 WAAM Validator 실행은 학습·평가 루프에서 제외했다.** 출력은 `collision_free`, `complete`, `makespan_s`이며 Validator PASS라고 표시하지 않는다. 경로 정책도 바뀌므로 이전 모델과 출력 형상의 동일한 품질을 검증한 비교는 아니다. 해치 간격 등은 기존 액션 범위 안에서만 변경된다.

## 실행

기존 waam Conda 환경을 사용한다. `minor3` 폴더에서 실행한다.

```powershell
$py = 'C:\Users\lazzyman\anaconda3\envs\waam\python.exe'
$initial = '..\minor_2\result\training\reward_only_40updates_20261018_155838\ppo_model.zip'
& $py train.py --train-plans '..\scheduler\plans\train_compact' --validation-plans '..\scheduler\plans\validation_compact' --initial-path $initial --output result\joint_40updates --updates 40 --device cuda
```

기존 plans의 STL/config와 레이어 인덱스만 읽고, 저장된 작업 묶음·기존 action은 학습 경로로 사용하지 않는다. **STL에서 현재 경로 정책의 action으로 매번 경로를 다시 생성한다.** 학습은 6개 STL의 선택된 18개 층, 평가는 별도 6개 STL 전체 8개 층이다. 입력 해시로 학습/평가 데이터가 겹치는지 확인한다.

기본 40회 교대 업데이트는 경로 정책 40×2=80 layer step, 대피 정책 40×8=320 repair step이다. 각 PPO 업데이트는 5 epoch이며 early stopping은 없다. 이는 동작 확인용 짧은 학습 설정이다. 충분한 학습에는 `--path-steps 16 --avoid-steps 64` 등으로 늘릴 수 있다. 검증 데이터에는 gradient update를 적용하지 않는다.

```powershell
& $py -m tensorboard.main --logdir result\joint_40updates\tensorboard --port 6006
& $py evaluate.py --run result\joint_40updates --plans '..\scheduler\plans\validation_compact' --output result\retest --device cuda
```

저장 파일: `path_initial/final.zip`, `avoidance_initial/final.zip`, TensorBoard, 두 정책의 에피소드 로그, 실행 당시 source, 학습 전후 전체 경로 CSV·Gantt·충돌 수정 기록. 실패한 경로에는 완성된 trajectory 파일을 생성하지 않는다.

## 기본 동작 검사

```powershell
& $py smoke.py --folder '..\scheduler\plans\validation_compact\job_01' --model $initial
```

실제 레이어의 충돌 해소, 적층 순서·분량 보존, 적층선 중간 중단·복귀, 누락된 적층선의 거부를 검사한다. 기존 전체 Validator를 호출하는 테스트는 아니다.
