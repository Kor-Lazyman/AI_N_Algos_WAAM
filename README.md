# AInalgos2 1.0.2

Main 1.0.2, Minor1, Minor2의 학습·검증·독립 테스트 방법과 Main의 STL layer preprocessing을 정리합니다. 세 버전은 같은 WAAM Validator와 공통 STL 입력 형식을 사용하며, 알고리즘별 체크포인트와 새 실행 결과는 각 버전의 `result/training/` 아래에 생성됩니다. 기존 테스트 결과와 사용하지 않는 실험 버전은 `backups/`에 보관합니다. `report final/`은 기존 보고 자료를 유지합니다.

## 환경 준비

현재 프로젝트는 Python 3.11과 `waam` Conda 환경을 기준으로 합니다. 기존 환경을 사용할 때는 다음과 같이 시작합니다.

```powershell
conda activate waam
```

환경을 새로 구성할 때는 프로젝트 루트에서 의존성과 로컬 Validator를 설치합니다.

```powershell
python -m pip install -r requirements.txt
python -m pip install -e environment
python -c "import torch; print('CUDA:', torch.cuda.is_available())"
```

학습 기본 장치는 CUDA입니다. CUDA를 쓸 수 없으면 학습 명령에 `--device cpu`를 지정합니다. PPO와 정책 네트워크는 지정 장치에서 실행하고, STL geometry 처리와 공식 Validator는 CPU에서 수행합니다.

## 데이터 폴더

각 작업 폴더는 `config.yaml`과 `target.stl`을 한 쌍으로 둡니다.

```text
train/
  01/config.yaml, target.stl
  ...
  06/config.yaml, target.stl
validation/
  00_sample/config.yaml, target.stl
  ...
test/
  my_part/config.yaml, target.stl
```

`train/`은 PPO 학습에 사용하고, `validation/`은 학습 도중 주기적으로 모델을 평가하는 held-out 세트입니다. 학습 코드는 학습·검증 STL 해시가 서로 겹치지 않는지 확인합니다. `test/`는 학습이 끝난 뒤 독립 평가를 위한 데이터입니다. 현재 `test/`에는 평가 작업이 없으므로, 독립 테스트를 하려면 위 형식의 하위 폴더를 먼저 추가해야 합니다.

## Main 1.0.2 실행

프로젝트 루트에서 실행합니다. 기본 설정은 1,024 layer-step, 64-step rollout, 4회 PPO 업데이트마다 validation, CUDA, TensorBoard 사용입니다. 전체 옵션은 `python train.py --help`로 확인할 수 있습니다.

```powershell
conda activate waam
python train.py --mode train --device cuda --timesteps 1024 --eval-every 4 --output result/training/main_run
```

한 번의 action은 현재 STL의 한 layer 전체 경로와 3대 로봇의 구간 배정을 결정합니다. 기본 학습 후에는 학습 STL 전체에 대한 경로 생성·Validator 평가·STL export가 추가로 실행됩니다. 이 마지막 export 평가를 생략하려면 `--no-export-stl`을 추가합니다.

학습 결과는 `result/training/<run>/`에 저장됩니다. `ppo_model.zip`은 마지막 모델, `best_model.zip`은 validation 기준 최고 모델, `checkpoint.zip`은 최근 checkpoint입니다. 새 실행마다 고유한 `--output` 경로를 지정하세요.

독립 테스트는 모델과 test 작업 폴더를 지정합니다.

```powershell
python train.py --mode test --model result/training/main_run/best_model.zip --test-dir test --device cuda
```

학습 도중 validation은 자동 수행됩니다. `--mode test`는 validation을 대신하는 용도가 아니라 독립 `test/` 입력을 평가하는 모드입니다.

## Minor1 실행

Minor1은 `Minor/`에서 실행합니다. Main의 layer 경로 PPO에 STL 전체를 XY 방향으로 옮기는 placement PPO를 추가합니다. placement action 하나의 같은 XY translation을 mesh 전체에 먼저 적용한 뒤 모든 layer를 자릅니다. 따라서 각 layer가 서로 다른 이동 거리를 받지 않습니다. placement 네트워크는 기본적으로 활성화되어 있으며, 두 네트워크의 체크포인트 쌍과 `.pair.json` 파일을 함께 보관해야 합니다.

Main 1.0.2의 PPO 가중치로 초기화해 40회 rollout 학습을 수행하는 예입니다. `--updates 40`은 기본 `n_steps=64`에서 2,560 layer-step을 뜻하며, `--no-early-stopping`은 PPO의 KL 조기 중단을 끕니다.

```powershell
cd Minor
conda activate waam
python train.py --mode train --device cuda --updates 40 --eval-every 4 --no-early-stopping --init-model ../result/training/main_run/ppo_model.zip --output result/training/minor1_40
```

placement 네트워크도 기존 Minor1 체크포인트에서 초기화할 때는 `--init-placement-model result/training/<기존-run>/placement_model.zip`을 추가합니다. placement 학습을 끄고 layer PPO만 실행하려면 `--no-placement`을 지정합니다. TensorBoard는 다음처럼 해당 버전의 로그를 엽니다.

```powershell
tensorboard --logdir result/tensorboard
```

독립 테스트:

```powershell
python train.py --mode test --model result/training/minor1_40/best_model.zip --test-dir ../test --device cuda
```

Minor1은 최종 경로 모델과 placement 모델이 짝을 이룹니다. 테스트에 쓸 때 같은 실행에서 생성된 두 모델 파일과 짝 검증용 `.pair.json`을 유지하세요.

## Minor2 실행

`minor_2/`에서 실행합니다. Main과 같은 layer action·경로 생성·로봇 분배 구조를 유지하고 reward를 바꾼 버전입니다. layer IoU가 0.9보다 크면 `10 × 평균 deposition 활용률 × 기준시간 / layer makespan`을 보상으로 사용합니다. 그렇지 않으면 마지막 layer의 공식 Validator 결과만 보상합니다(PASS `+1`, FAIL/ERROR `-1`; episode 중간에는 `0`). 경로 생성·reach·collision 실패는 음의 실패 보상을 받습니다.

```powershell
cd ../minor_2
conda activate waam
python train.py --mode train --device cuda --updates 40 --eval-every 4 --no-export-stl --init-model ../result/training/main_run/ppo_model.zip --output result/training/minor2_40
```

`--updates 40`은 기본 `n_steps=64`에서 2,560 layer-step입니다. `--no-export-stl`은 학습 종료 뒤 train STL 전체를 다시 export하는 추가 평가를 생략합니다. Validation 평가는 설정된 주기에 계속 수행됩니다. TensorBoard는 다음과 같이 엽니다.

```powershell
tensorboard --logdir result/tensorboard
```

독립 테스트:

```powershell
python train.py --mode test --model result/training/minor2_40/best_model.zip --test-dir ../test --device cuda
```

## Main 1.0.2의 layer preprocessing

전처리와 환경 구현은 루트의 `layer_assignment_env.py` 및 `environment/src/waam_validator/shape/target.py`에 있습니다. 모델에는 미리 만든 적층 경로를 넣지 않습니다. STL mesh를 검증·슬라이싱하고, 각 layer에서 policy가 경로를 생성합니다.

1. **작업 설정과 STL 읽기.** 각 job에서 `config.yaml`을 읽어 layer height, bead width, build plane, 속도, workspace, 로봇 reach/collision 설정을 가져옵니다. `target.stl`은 `trimesh`로 읽습니다. STL scene이면 triangle mesh를 하나로 합칩니다.
2. **Mesh 검사와 정리.** 빈 mesh, triangle 부재, 비유한 좌표를 거부합니다. 중복 vertex 병합, 퇴화·중복 face 제거, 참조되지 않는 vertex 삭제를 수행하고 normal 방향과 body 수를 정리합니다. 설정이 허용하면 닫히지 않은 mesh의 hole repair를 시도하고, 설정에서 watertight를 요구하면 repair 후에도 닫히지 않은 형상을 거부합니다. target이 build plane 아래로 내려가는 좌표 불일치도 검사합니다.
3. **평가 layer 산출.** target의 build-plane 기준 높이를 layer height로 나누고 올림해 대상 layer index를 정합니다. 각 layer 단면은 `build_plane_z + (layer_index + 0.5) × layer_height`의 중간 높이에서 계산합니다.
4. **2D 단면 생성·정규화.** 공식 Validator의 mesh slicing으로 단면 polygon을 구합니다. 정확한 위치의 단면이 비어 있으면 layer 높이에 기반한 작은 `+epsilon`, `-epsilon` offset을 차례로 시도합니다. 얻은 polygon은 config의 snap tolerance와 area epsilon으로 정규화하고 빈 단면·면적이 너무 작은 단면은 학습 layer에서 제외합니다. 유효한 단면이 하나도 없으면 해당 STL job은 실패합니다.
5. **Observation 구성.** 현재 진행률, 누적 makespan·IoU, 직전 layer 정보, 현재 단면의 높이·bounds·면적·둘레, 세 로봇의 base/home/reach 정보 및 공정·Validator 설정값을 구성합니다. 단면의 면적 분포는 16×16 fractional-area raster로 계산해 observation에 넣고, 같은 단면 raster는 cache에 보관합니다.
6. **학습 중 경로 생성.** PPO action은 `[hatch angle, hatch spacing, start corner, reverse, partition axis, partition quota, robot order]`의 7개 이산 값입니다. action을 바탕으로 inward contour와 polygon 내부에 clip한 hatch line을 만들고, 선분을 나누어 도달 가능한 로봇에게 배정합니다. 로봇별 경로를 시간화한 뒤 trajectory reach/geometry와 collision을 검사합니다. 충돌 시 serial fallback을 한 번 시도합니다. 한 환경 step은 이렇게 생성한 **layer 하나**이며, 적층 완료 후 전체 layer 일정은 공식 Validator에 넘겨 최종 판정합니다.

Main의 관측·행동 정의와 세부 reward는 `layer_assignment_env.py`를 기준으로 합니다. 기본 reward는 layer IoU에 양의 점수를 더하고, layer 소요시간 및 로봇 idle time을 기준시간으로 정규화해 감점하며, 마지막 공식 Validator PASS/FAIL을 추가합니다. 생성·도달·충돌 제약을 만족하지 못한 경로는 별도 실패 보상을 받습니다.

## 검증·모니터링

학습 후 전체 결과 요약과 개별 trajectory/validator 산출물은 해당 run의 결과 폴더에서 확인합니다. 평가 스크립트를 직접 실행할 수도 있습니다.

```powershell
python -m unittest discover -s tests -v
python evaluate_layers.py --model result/training/main_run/ppo_model.zip --eval-source stl --device cuda
```

TensorBoard가 활성화된 학습은 버전별 `result/tensorboard/`에 새 로그를 씁니다. 실행 중인 UI·학습 세션이 참조하는 기존 로그와 결과는 이동하지 않고 그대로 유지합니다. 과거 비교·validation·gantt·trajectory·TensorBoard 산출물 및 비활성 실험 코드는 `backups/` 아래에서 원래 경로 구조를 따라 확인할 수 있습니다.
