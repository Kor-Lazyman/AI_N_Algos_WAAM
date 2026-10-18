# Minor — 1.0.2-minor

원본 1.0.2에서 분리한 다중 로봇 스케줄링·STL 위치 학습 버전입니다. 부모 폴더의 `train/`, `validation/`, `test/`, 공식 `environment/` 및 기존 Conda `waam`을 공유합니다. 모델과 결과는 이 폴더의 `result/`에 저장합니다.

## 보상

레이어 IoU를 `I`, 레이어 makespan을 `T`, 로봇 수를 3, 로봇별 실제 적층 시간을 `D_r`라 하면:

```text
U = (D_1 + D_2 + D_3) / (3 × T)

I > 0.9:  R_layer = 10 × U × T_ref / T
I ≤ 0.9:  R_layer = 기존 전체 Validator 보상
                    마지막 step에서 PASS이면 +1, FAIL/ERROR이면 -1
                    전체 검증 전의 중간 step은 0

경로를 만들 수 없어 episode가 중단되면 -2
```

IoU는 해당 레이어 형상 IoU입니다. 0.9를 **초과**해야 시간 보상으로 전환합니다. 시간 보상 구간에서는 PASS 보상을 더하지 않습니다. 활용률 `U`에는 D(적층)만 포함하고 T(이동)·W(대기)는 포함하지 않습니다. 시간 보상 계수 10, Validator 통과 보상 계수 1을 사용합니다. 실제 보상 크기는 시간과 활용률에도 달려 있습니다.

`T_ref = max(1, 목표 레이어 면적/(비드 폭×적층 속도) + Σ 원본 위치에서 home↔레이어 중심 왕복 이동시간)`입니다. STL을 옮겨도 같은 레이어의 기준시간은 원본 위치를 기준으로 유지합니다. 위치를 멀리 옮겨 기준시간만 커져 보상이 올라가는 것을 방지합니다.

전체 Validator PASS는 여전히 모델 선택과 결과 성공 판정의 필수 조건입니다. `best_model`은 통과율, 형상별 정규화 makespan 감소, 실제 동시 적층 비율 순서로 선택합니다. 원본처럼 통과율 동률을 모두 동일하게 취급하지 않습니다.

## 두 네트워크

1. **위치 PPO**: STL·로봇·작업 공간 정보 42개를 보고 `Box(-1,1,shape=(2,))`의 XY 이동 행동을 결정합니다. STL 전체를 한 번 평행 이동한 **뒤 슬라이싱**합니다. Z, 회전, 크기는 변경하지 않습니다. 원형 작업 공간을 넘는 요청은 전체 이동 벡터를 같은 비율로 줄입니다. 개별 정점이나 레이어를 따로 움직이지 않습니다.
2. **경로 PPO**: 한 행동으로 한 레이어의 경로 파라미터를 결정합니다. 원본과 같은 `MultiDiscrete([8,3,4,2,2,3,6])`, 309차원 관측을 사용하므로 원본 정책 가중치로 시작할 수 있습니다. 이 버전의 경로는 파라미터 기반 contour/hatch 생성입니다.
3. **교대 학습**: 경로 PPO를 기본 64 layer step 학습한 다음, 경로 정책을 고정하고 위치 PPO를 기본 2 STL episode 학습합니다. 위치 PPO의 한 step은 STL 전체 평가입니다. 경로 학습 중에는 위치 정책을 deterministic으로 사용하며 episode 도중 위치를 바꾸지 않습니다.
4. **위치 보상**: `R_placement = 해당 STL episode에서 발생한 R_layer의 평균`. 다른 STL의 레이어 보상은 섞지 않습니다. 실패하여 중단된 episode에는 발생한 실패 보상도 포함합니다. 위치 학습 로그에 해당 STL 이름, 이동량, 개별 레이어 보상, 평균을 기록합니다.

위치 학습은 STL 전체를 실행하므로 레이어 수가 많은 STL에서는 시간이 오래 걸릴 수 있습니다. 두 PPO 신경망은 CUDA에서 계산하고, 슬라이싱·경로·충돌 검사·Validator는 CPU에서 계산합니다.

## 동시 스케줄러

원본은 동시 경로가 충돌하면 레이어 전체를 순차 적층으로 바꾸었습니다. Minor는 다음 후보를 검사합니다.

- 정책이 지정한 공간 분할, 가장 가까운 도달 가능 base, 작업량을 함께 고려한 근접 배정.
- 선분의 시작점·끝점을 고려한 순서 조정으로 비적층 이동 단축.
- 로봇별 전체 경로의 시작 시점을 조정해 안전한 동시 작업 구간 탐색. 출발 전 대기는 home에서 수행.

생성된 모든 적층 선분을 보존합니다. 빠른 충돌 검사는 후보를 탈락시키는 용도로만 사용하며, 수락 후보에는 공식 궤적·충돌 검사를 적용합니다. 기존의 같은 행동으로 만든 스케줄도 후보로 유지하므로 유효한 원본 후보보다 긴 스케줄을 선택하지 않습니다. 이 보장은 같은 레이어·행동·STL 위치의 비교이며, 다른 학습 정책이나 위치에 대한 전역 최적 보장은 아닙니다.

작은 형상에서는 3대가 작업을 나누더라도 동시에 적층할 공간이 부족할 수 있습니다. 세 로봇이 모두 작업을 했다는 것과 실제 동시 적층 시간은 별도로 기록합니다. 원본 충돌 반경과 Validator 기준은 그대로 사용합니다.

## 실행

이 `Minor` 폴더에서 실행합니다.

```powershell
conda activate waam

# 경로 PPO + 위치 PPO 교대 학습. validation은 학습 중 모델 선택에 사용.
python train.py --mode train --device cuda --timesteps 1024

# 기존 원본 정책 가중치에서 경로 네트워크 시작; optimizer는 새로 초기화.
python train.py --mode train --device cuda --init-model "../result/training/layers_1.0.2_20261017_044941_396096/ppo_model.zip"

# 위치 갱신 빈도/샘플 수. 위치 1 step은 해당 STL의 모든 레이어 평가.
python train.py --mode train --device cuda --placement-every 4 --placement-steps 2

# 위치를 고정하고 경로만 학습하려는 경우.
python train.py --mode train --device cuda --no-placement

# 독립 test 폴더에 입력을 넣은 뒤, 저장된 네트워크 쌍으로 평가.
python train.py --mode test --device cuda --model "result/training/<run>/best_model.zip"

tensorboard --logdir result/tensorboard
python -B -m unittest discover -s tests -v
```

`--timesteps`는 경로 네트워크 layer step 수이며 위치 네트워크의 STL episode 수와 구분합니다. 위치 네트워크도 이어서 초기화하려면 `--init-placement-model`을 함께 사용합니다. 입력 STL/config는 각 실행의 `inputs/`에 복사해 고정합니다.

## 산출물

- `ppo_model.zip` + `placement_model.zip`: 최종 경로·위치 네트워크.
- `best_model.zip` + `best_placement_model.zip`: 같은 검증 시점에서 선택한 모델 쌍.
- `checkpoint.zip` + `placement_checkpoint.zip`: 최근 완료한 교대 갱신.
- `*.pair.json`: 두 모델의 해시. 평가 시 함께 저장된 쌍인지 확인합니다.
- `training_layer_trace.jsonl`: 레이어 행동, 보상, makespan, 활용률, 동시 적층 시간.
- `placement_trace.jsonl`: STL별 이동량, 해당 STL의 레이어 보상 목록과 평균.
- `input/target.stl`: 이동을 적용한 검증 대상 STL.
- `input/placement.json`: 원본 경로, 요청 행동, 전체에 적용한 XYZ 이동량.
- `input/trajectory.csv`, `deposited.stl`, `validation/summary.json`: 경로·적층 결과·공식 검사.
- TensorBoard 경로 정책 로그와 하위 `placement/` 위치 정책 로그.

동일 원본 정책 행동에 대한 스케줄러 비교는 다음처럼 실행합니다. 이 결과를 새로운 네트워크의 학습 효과로 해석하지 않습니다.

```powershell
python -m tools.benchmark --model "../result/training/layers_1.0.2_20261017_044941_396096/ppo_model.zip" --scenarios ../train/01 ../train/02
```

실제 실행 결과는 [RESULTS.md](RESULTS.md)를 참고하세요.

## Fixed update run

`--updates 40 --no-early-stopping` runs exactly 40 layer PPO rollouts (64 steps each by default), with KL early stopping disabled for both networks. Placement updates still follow `--placement-every` and `--placement-steps`. Validation does not stop training. Initial validation at step 0 is enabled by default; use `--no-initial-validation` to skip it. `--updates` overrides `--timesteps`.
