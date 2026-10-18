# WAAM 레이어 경로 생성 · AInalgos2 1.0.2

**PPO의 1 step이 한 레이어의 적층 경로 생성과 세 로봇의 작업 분담입니다.** STL을 높이별로 슬라이싱한 뒤, 정책이 레이어마다 채움 방향·간격·경로 순서·로봇 분담을 결정합니다. 경로 생성기가 그 행동을 실제 좌표와 시간표로 바꾸고, 해당 레이어를 검증해 보상을 계산합니다.

프로젝트 버전은 `1.0.2`, 환경 스키마는 `layer_path_v1`입니다. 내장 공식 Validator 버전은 기존 `1.0.1`을 유지합니다. 이 폴더는 `version 1.0.2/AInalgos2-main`으로 분리되어 독립 실행됩니다. 기존 선분 학습 코드는 형제 폴더 `version 1.0.1/AInalgos2-main`에 남아 있습니다. 기존 Conda `waam` 환경을 그대로 사용하며 `environment/`, STL 입력, 모델 및 결과를 함께 보존했습니다.

```text
stl_files의 config.yaml + target.stl
  → STL 슬라이싱: 레이어별 목표 단면 준비
  → PPO 행동: 현재 레이어의 경로 생성 설정 + 세 로봇 분담
  → 윤곽·채움 경로 생성 → 이동·적층·귀환 일정 생성
  → 해당 레이어의 도달·궤적·충돌 검사 + 형상·시간 보상
  → 세 로봇 모두 귀환 후 다음 레이어로 진행
  → 마지막 레이어 완료: 전체 궤적을 공식 Validator로 검증
```

학습 입력은 `stl_files/01..06`이고 검증 입력은 [validation_stl](validation_stl)의 6개 독립 형상입니다. 검증 세트에는 기존 sample 1개와 새 STL 5개가 포함됩니다. 사전 생성한 `tasks.json`을 사용하지 않습니다. STL 단면만 미리 준비하며, 적층 선분은 매 step의 행동으로 생성합니다.

## 실행

명령은 이 README가 있는 `AInalgos2-main` 디렉터리에서 실행합니다. 로컬 설치된 `waam` 환경을 사용할 수 있습니다.

```powershell
conda activate waam

# STL 6개로 학습, 별도 검증 STL 6개로 주기적 검증
python train_layers.py --device cuda

# 저장 모델을 검증 세트 전체에서 테스트
python benchmark_validation_stls.py --device cuda

# 가장 최근 완료된 1.0.2 모델을 example에서 평가
python evaluate_layers.py --device cuda

# 동일 모델을 학습 STL 6개에서 평가
python evaluate_layers.py --eval-source stl --device cuda
```

기존 진입점도 기본적으로 새 레이어 환경에 연결됩니다.

```powershell
python train.py
python train_stl.py
python evaluate_latest.py
python evaluate_stl.py
```

`train.py`와 `train_stl.py`는 모두 `train_layers.py`로, `evaluate_latest.py`는 example 평가로, `evaluate_stl.py`는 STL 평가로 연결됩니다. 선분 학습은 기존 1.0.1 폴더에서 실행합니다. 레이어 모델은 관측·행동 공간이 달라서 기존 선분 모델을 그대로 이어 학습하거나 평가할 수 없습니다.

짧은 실행 연결 확인 및 모델 지정 평가:

```powershell
python train_layers.py --timesteps 8 --n-steps 8 --batch-size 4 --eval-every 1 --no-export-stl --output results/training/my_layer_run
python evaluate_layers.py --model results/training/my_layer_run/ppo_model.zip
python evaluate_layers.py --model results/training/my_layer_run/ppo_model.zip --eval-source stl
```

`--output`은 새 경로여야 합니다. 기존 결과를 덮어쓰지 않습니다. 전체 옵션은 각 스크립트의 `--help`로 확인할 수 있습니다. 새 Python 환경에서는 `python -m pip install -r requirements.txt`로 의존성을 설치합니다.

## 검증용 STL 데이터셋

`validation_stl/00_sample`은 내장 sample의 사본입니다. 추가한 `01_rectangle`(2층), `02_triangle`(1층), `03_l_shape`(2층), `04_cross`(1층), `05_ring`(구멍이 있는 1층)은 [생성 코드](generate_validation_stls.py)로 만들었습니다. 각 폴더에는 `config.yaml`과 `target.stl`이 있고 [manifest.json](validation_stl/manifest.json)에 SHA-256과 메쉬 경계를 기록했습니다. 학습 STL 6개와 검증 STL의 목표 STL 해시가 겹치지 않는지 검사합니다.

새 학습은 이 6개를 모두 입력 사본으로 고정하고, 검증 시점마다 각 형상을 한 번씩 공식 Validator로 검사합니다. best 모델의 PASS 비율도 검증 세트 전체의 평균입니다. `--validation-dir 경로`로 다른 검증 세트를 지정할 수 있습니다. 기존 학습 결과는 당시 sample 검증 기록을 유지하며, `benchmark_validation_stls.py`로 새 세트를 별도 평가할 수 있습니다. 이 세트는 모델 선택에 사용되므로 독립된 최종 test set으로 해석하면 안 됩니다.

```powershell
python benchmark_validation_stls.py --model results/training/layers_1.0.2_20261017_run01/ppo_model.zip --device cuda
python -m unittest test_layer_assignment test_layer_training test_validation_dataset -v
```

검증 실행은 형상별 `trajectory.csv`, 공식 보고서, PASS/FAIL을 `results/layer_evaluation/<시각>/`에 저장합니다. 검증을 통과한 경로의 `deposited.stl`도 저장합니다. `benchmark_validation_stls.py`는 각 입력의 **STL 로딩·슬라이싱부터 경로 생성·검증·에피소드 결과 저장까지**의 실제 계산 시간, 공식 Validator의 makespan(시뮬레이션 시간), PASS/FAIL을 화면과 `per_shape_results.csv`에 기록합니다. [실행 결과](results/layer_evaluation/validation_stl_20261017_baseline/evaluation.json)에서는 저장된 128-step 모델의 검증 형상 6개가 모두 PASS했습니다. 새 idle 보상과 검증 세트로 학습한 정책의 일반화 결과는 별도 학습 후 다시 평가해야 합니다.

현재 최신 완료 모델(1,024 step)을 2026-10-17에 다시 실행한 [형상별 계산 시간·makespan·Validator 결과 CSV](results/layer_evaluation/validation_stl_20261017_latest_runtime/per_shape_results.csv)도 있습니다. 6개 모두 PASS했습니다. 계산 시간은 모델을 메모리에 불러온 뒤 **각 형상을 처리하는 실제 벽시계 시간**이며, makespan은 로봇 궤적의 시뮬레이션 시간입니다. 이 모델 역시 idle 보상 변경 전 학습된 가중치입니다.

## 검증 후 6개 형상의 경로 및 STL 저장

기본 학습은 마지막 검증 세트 평가와 `ppo_model.zip` 저장 후, 최종 모델로 학습 STL 6개 전체의 경로를 생성하고 각각 공식 검증합니다. 결과는 학습 실행 폴더의 `final_stl_evaluation/job_00..05/episode_000/`에 저장됩니다. 검증 세트 6개는 검증 주기마다 평가하고, 학습 STL 6개는 마지막에 평가합니다. 이 시간도 전체 실행 시간에 포함됩니다. 빠른 학습 동작 확인만 필요하면 `--no-export-stl`로 마지막 학습 STL 평가를 생략할 수 있습니다.

- `input/trajectory.csv`: 로봇 1·2·3의 시간별 XYZ 경로. 열은 `robot_id,time_s,x_mm,y_mm,z_mm,mode`이며 `T`는 이동, `D`는 적층, `W`는 대기입니다.
- `deposited.stl`: 검증을 통과한 trajectory의 적층 구간을 비드 폭과 레이어 높이로 재구성한 형상입니다. 원본 `target.stl`과 구분됩니다.
- `artifacts.json`: 경로/입력/STL 해시, 레이어 수, 생성 상태입니다.
- `validation/`: 공식 검증 보고서입니다. FAIL이나 미완료 경로에는 검증 통과 STL을 생성하지 않습니다.

STL은 레이어별 명목 적층 체적을 합친 메쉬이며, 레이어 경계의 내부 면을 제거하는 CAD boolean union이나 열변형 계산은 수행하지 않습니다. 실제 로봇 경로 정보는 반드시 `trajectory.csv`를 사용합니다.

**기존 128 step 모델의 검증 통과 경로 6개와 STL:** [results/exports/stl_01_06](results/exports/stl_01_06). 하위 `01`~`06`에 각각 `trajectory.csv`, `deposited.stl`, 원본 입력 및 검증 요약이 있습니다. [manifest.json](results/exports/stl_01_06/manifest.json)에 파일과 해시를 기록했습니다.

저장된 검증 경로에서 다시 STL과 배포용 폴더를 생성하려면:

```powershell
python export_trajectories.py --evaluation results/layer_evaluation/layers_1.0.2_20261017_run01 --output results/exports/my_export
```

## 한 step의 행동과 경로

### TensorBoard 모니터링

1.0.2 학습은 TensorBoard 로그를 기본으로 저장합니다. `train.py`와 `train_stl.py`에도 동일하게 적용됩니다. 학습과 TensorBoard는 각각 별도 터미널에서 실행합니다.

```powershell
# 터미널 1: AInalgos2-main 디렉터리
conda activate waam
python train.py --device cuda --timesteps 1024 --n-steps 64 --batch-size 32 --eval-every 4

# 터미널 2: 같은 디렉터리
conda activate waam
python -m tensorboard.main --logdir results/tensorboard --host 127.0.0.1 --port 6006
```

브라우저에서 `http://localhost:6006`을 엽니다. 새 학습마다 별도 run으로 기록하며 정확한 이벤트 폴더는 `training.json`의 `tensorboard_log`에 저장합니다. `--tensorboard-log 경로`로 로그 루트를 바꾸거나 `--no-tensorboard`로 끌 수 있습니다. 새 환경에서는 `python -m pip install -r requirements.txt`를 실행합니다.

| 지표 | 의미 |
| --- | --- |
| `rollout/ep_rew_mean`, `rollout/ep_len_mean` | 최근 완료 에피소드의 총보상·레이어 step 수 평균 |
| `layer/reward`, `layer/layer_iou` | rollout 동안 시도한 레이어의 평균 보상·생성된 레이어 IoU |
| `layer/step_wall_time_s` | 정책 추론과 환경 계산을 포함한 step 처리 시간 평균 |
| `layer/reward_*`, `layer/rejected`, `layer/serial_fallback` | 보상 구성·배정 실패 비율·직렬 대체 일정 비율 |
| `train/*` | PPO policy/value loss, entropy, KL 등 optimizer 지표 |
| `performance/layers_per_s` | optimizer 계산을 포함한 업데이트 처리 속도 |
| `validation/pass_rate`, `validation/iou_mean` | 검증 STL 세트의 공식 Validator PASS 비율·IoU |

가로축 step은 누적 레이어 시도 수입니다. 레이어 지표는 rollout 종료마다, optimizer 지표는 업데이트마다, 검증 지표는 `--eval-every` 주기와 마지막 업데이트에 기록합니다. `rollout/ep_*`는 첫 에피소드가 끝난 뒤 나타나며, 과거 실행의 JSON 로그는 TensorBoard 이벤트로 자동 변환하지 않습니다.

### 경로 생성 행동

행동은 `MultiDiscrete([8, 3, 4, 2, 2, 3, 6])`인 정수 7개입니다. PPO는 자유 길이 좌표열을 직접 출력하지 않고, 다음 설정을 선택합니다.

| 위치 | 행동 | 선택 값 |
| --- | --- | --- |
| 0 | 채움 각도 | `0..7` → `0°, 22.5°, …, 157.5°` |
| 1 | 채움 간격 | `0/1/2` → 비드 폭의 `0.8/0.9/1.0`배 |
| 2 | 시작 모서리 | `0/1/2/3` → `(xmin,ymin)/(xmax,ymin)/(xmin,ymax)/(xmax,ymax)` 근처에서 시작 |
| 3 | 경로 순서 반전 | `0` 유지, `1` 선분 순서와 각 선분 방향 반전 |
| 4 | 작업 분할 축 | `0` X, `1` Y |
| 5 | 세 영역의 목표 적층 길이 비율 | `0` 균등, `1` `(0.5,0.25,0.25)`, `2` `(0.25,0.25,0.5)` |
| 6 | 영역 담당 로봇 순열 | `0..5` → `123, 132, 213, 231, 312, 321` |

경로 생성기는 선택 각도로 단면을 회전하고 비드 폭의 `0.49`배 안쪽에 윤곽과 왕복 채움 선을 만듭니다. 채움 간격은 선택값을 기준으로 단면 높이에 맞춰 조정됩니다. 긴 선분은 최대 80 mm로 분할하고, 시작 모서리와 반전 설정으로 순서를 정합니다. 비드 폭으로 출력 가능한 내부 영역이 없으면 경로 생성 실패로 종료합니다.

작업 분담은 선분 중점을 X 또는 Y축으로 정렬한 뒤 적층 길이의 누적 비율로 세 공간 영역을 나눕니다. 면적을 정확히 3등분하거나 세 로봇의 완료 시간을 같게 만드는 제약은 아닙니다. 각 로봇은 배정된 선분 사이를 이동하며 적층하고 레이어 종료 시 home으로 돌아옵니다. 선분마다 home으로 돌아오지는 않습니다.

각 선분은 **세 로봇 중 한 대라도 시작점과 끝점 모두 도달 가능하면** 배정할 수 있습니다. 요청된 담당 로봇이 도달하지 못하면 도달 가능한 로봇 중 현재 배정 적층 길이가 가장 짧은 로봇으로 재배정합니다. 어느 로봇도 두 끝점에 도달할 수 없는 선분이 있으면 해당 레이어 전체를 거부합니다. 재배정 자체의 벌점은 없습니다.

먼저 세 로봇이 동시에 시작하는 레이어 일정을 검사합니다. 충돌이 있으면 행동에서 정한 로봇 순서대로 한 대씩 작업하는 직렬 일정을 다시 검사합니다. 이 일정도 통과하지 못하면 종료합니다. 매 레이어 경계에서는 세 로봇 모두 home에서 기다리므로 다음 레이어의 검사는 그 레이어 경로만 대상으로 수행합니다. 마지막에는 누적된 전체 경로를 공식 Validator로 다시 검사합니다.

## 관측과 보상

관측은 고정 크기 `float32` **309차원**입니다.

| 관측 구성 | 크기 | 내용 |
| --- | ---: | --- |
| 진행 상태 | 9 | 층 진행률·총 층 수·누적 IoU·직전 층 IoU·누적/직전 시간·직전 로봇별 선분 수 |
| 현재 단면 | 263 | 높이·XY 경계·면적·둘레 7개 + 경계 상자 내부의 16×16 단면 점유율 |
| 세 로봇 설정 | 27 | base/home XYZ·XY 도달 반경·arm/TCP 반경 |
| 공정·형상 기준 | 10 | 비드 폭·층 높이·이동/적층 속도·clearance·Validator 형상 기준 |

좌표 등은 형상과 로봇 위치에서 구한 스케일로 정규화하며, 시간과 개수 일부는 `log1p`로 변환합니다. 이전 전체 적층 형상이나 모든 궤적을 관측에 넣지는 않습니다. 이전 상태를 요약값으로 제공하는 부분 관측 환경입니다.

보상은 [LayerRewardWeights와 LayerPathEnv.step()](layer_assignment_env.py)에 구현되어 있습니다. **유효한 한 레이어의 기본 보상**은 다음과 같습니다.

```text
r_layer = 1.0 × IoU_layer − 0.1 × duration_layer × idle_factor_layer / reference_layer

utilization_robot = (이동 T 시간 + 적층 D 시간) / duration_layer
mean_utilization = (utilization_1 + utilization_2 + utilization_3) / 3
idle_factor_layer = 4 − 3 × mean_utilization
                  = 1 + (idle_1 + idle_2 + idle_3) / duration_layer

reference_layer = max(1,
    target_area / (bead_width × deposition_speed)
    + Σ_robot 2 × distance(home, layer_centroid) / travel_speed
)

마지막 레이어에서 전체 공식 Validator 결과:
    PASS → r_layer에 +1
    FAIL 또는 검증 오류 → r_layer에 −1

경로 생성 실패, 모든 로봇 도달 불가, 궤적·충돌 검사 실패:
    reward = −2, 에피소드 종료, 해당 레이어의 경로·형상은 반영하지 않음
```

`IoU_layer`는 이번 층의 목표 단면과 적층 단면의 교집합/합집합입니다. 누적 IoU 차분이 아닙니다. `duration_layer`는 이동·적층·대기·귀환을 포함하며, `reference_layer`는 행동과 독립적인 목표 단면·로봇 설정으로 계산합니다. `idle_robot`은 해당 레이어의 `W` 구간 시간입니다. 한 대만 계속 움직이거나 적층하면 평균 활용률은 1/3이고 시간 벌점이 3배, 세 대 모두 계속 작업하면 평균 활용률은 1이고 벌점이 1배입니다. 중간 활용률도 실제 대기 시간 비율에 따라 연속적으로 반영됩니다. 가중치는 유한한 음이 아닌 값이며 기본값은 `iou=1`, `time=0.1`, `invalid=2`, `completion=1`, `validation_failure=1`입니다.

이 변경 이후의 학습 결과에는 `training.json`의 `reward_formula=utilization_weighted_time_v1`을 기록합니다. 이미 저장된 128 step 모델은 변경 전 보상으로 학습된 결과이므로, 새로운 idle 보상 기준으로 정책을 최적화하려면 다시 학습해야 합니다. 기존 평가 파일의 보상 값은 당시 계산식을 따릅니다.

**별도 `IoU ≥ 0.92` 조건은 없습니다.** 전체 결과 생성과 공식 Validator의 `PASS`를 완료 성공으로 봅니다. Validator가 `config.yaml`의 형상·도달·충돌·궤적 기준을 판정합니다. 레이어 형상이 나빠도 유효한 경로이면 해당 레이어의 IoU 보상을 받고 다음 층을 진행할 수 있으며, 최종 형상 기준은 전체 Validator가 판정합니다. 행동 공간 밖의 입력은 `ValueError`, 종료 후 `step()`은 `RuntimeError`입니다.

`info`에는 `layer_iou`, `layer_duration_s`, `time_reference_s`, `robot_utilization`, `mean_robot_utilization`, `robot_idle_s`, `idle_factor`, `weighted_layer_duration_s`, `reward_iou`, `reward_time`, `reward_invalid`, `reward_terminal`, `robot_segment_counts`, `reassigned_segments`, `serial_fallback`, `path_parameters` 등이 기록됩니다. 누적 `iou`는 아직 출력하지 않은 목표 층도 포함하므로 현재 레이어의 `layer_iou`와 다를 수 있습니다. TensorBoard에는 `layer/mean_robot_utilization`, `layer/idle_factor`, `layer/weighted_layer_duration_s`가 기록됩니다.

## 학습·평가 설정과 저장 파일

기본 학습 설정은 CUDA, PPO `MlpPolicy`, **1,024 레이어 step**, `n_steps=64`, `batch_size=32`, `learning_rate=0.0003`, `gamma=0.99`, `gae_lambda=0.95`, seed 42입니다. 요청 step 수는 PPO rollout 단위로 올림됩니다. 에피소드 하나는 형상 하나이며, 학습 형상 순서를 섞어 순환합니다. 중간 실패가 없으면 에피소드 길이는 해당 STL의 레이어 수입니다.

4회 업데이트(기본 256 step)마다와 마지막 업데이트 후 검증 STL 6개를 각각 1회 평가합니다. 검증 형상은 학습 rollout이나 gradient 계산에 사용하지 않습니다. best 모델은 **전체 검증 세트의 공식 Validator PASS 비율**로 선택하며, 동점이면 기존 best를 유지합니다.

PPO 신경망 추론과 학습은 CUDA에서 실행합니다. 슬라이싱·경로 생성·Shapely 형상 계산·공식 Validator는 CPU에서 실행합니다. CUDA가 없으면 자동으로 CPU로 바꾸지 않고 오류를 반환합니다. CPU를 사용하려면 `--device cpu`를 명시합니다. 한 step의 의미가 선분에서 레이어로 바뀌었으므로 이전 버전의 step/s나 같은 timesteps를 그대로 비교할 수 없습니다.

기본 학습 저장 위치는 `results/training/layers_1.0.2_<시각>/`입니다.

| 파일 | 내용 |
| --- | --- |
| `ppo_model.zip` | 정상 학습 완료 모델 |
| `checkpoint.zip` | 최근 완료된 PPO 업데이트의 모델, 정상 처리된 중단 시에도 저장 |
| `best_model.zip` | 검증 세트의 PASS 비율이 가장 높은 모델 |
| `training.json` | 버전·스키마·장치·PPO/보상 설정·입력 해시·실제 step 수·벽시계 시간·상태 |
| `inputs/` | 실행에 사용한 학습 STL/config와 검증 STL 6개의 사본 |
| `monitor.csv` | 학습 에피소드 보상·길이·완료 여부·IoU |
| `validation_history.json` | 검증 시점별 PASS 비율·IoU·보상·길이 |
| `validation/step_XXXXXXXX/` | 해당 검증 모델 사본, `job_XX/episode_XXX`별 추적 및 공식 보고서 |

기본 평가는 최신 **완료된 1.0.2 실행의 `ppo_model.zip`**을 선택합니다. 최신 모델은 최고 성능 모델을 뜻하지 않습니다. 학습 중인 체크포인트나 best 모델은 `--model`로 직접 지정할 수 있습니다. 평가는 기본 CUDA, 형상당 1회, `deterministic=True`이고 학습하지 않습니다.

평가 결과는 `results/layer_evaluation/<시각>/`에 저장합니다.

- `model_snapshot.zip`: 평가에 실제 사용한 모델 사본.
- `evaluation.json`: 입력·모델 해시, split, 형상별/전체 완료율·PASS 비율·보상 등.
- `job_XX/episode_XXX/layer_trace.json`: 레이어별 행동·보상·처리 시간·배정·실패 원인.
- `job_XX/episode_XXX/episode.json`: 에피소드 요약과 전체 레이어 추적.
- 완료된 에피소드의 `input/trajectory.csv` 및 `validation/`: 생성한 경로와 공식 Validator 보고서.

완료하지 못한 일정은 `INFEASIBLE`, 완료 후 공식 결과는 `PASS`/`FAIL`, 검증 오류는 `ERROR`로 기록합니다. 저장된 입력 사본의 해시를 확인하며, `--eval-source stl`은 현재 `stl_files`와 학습 당시 입력의 해시가 같은지도 확인합니다. `--eval-source validation`은 새 학습 모델에서 고정된 검증 STL 해시를 확인합니다. STL 학습 형상의 재평가를 일반화 성능으로 해석하면 안 됩니다.

로그의 `ep_len_mean`은 **에피소드당 시도한 레이어 step 수 평균**, `ep_rew_mean`은 에피소드 총보상 평균입니다. 학습 로그는 Monitor가 집계하는 최근 에피소드 기준이고, 평가 보고서는 해당 평가 전체 에피소드 기준입니다. `makespan_s`는 시뮬레이션 일정 시간이며 실제 처리 시간인 `wall_time_s`와 구분합니다.

## 코드와 한계

| 파일 | 역할 |
| --- | --- |
| [layer_assignment_env.py](layer_assignment_env.py) | 레이어 슬라이싱·행동에 따른 경로 생성·3로봇 일정·보상·최종 공식 검사 |
| [train_layers.py](train_layers.py) | STL 학습/다중 STL 검증, CUDA PPO, 체크포인트·best·최종 모델 저장 |
| [evaluate_layers.py](evaluate_layers.py) | 최신 레이어 모델 선택, example/검증/STL 평가와 경로·보고서 저장 |
| [generate_validation_stls.py](generate_validation_stls.py) | 검증용 형상과 해시 manifest 생성 |
| [benchmark_validation_stls.py](benchmark_validation_stls.py) | 검증 STL별 계산 시간·makespan·Validator 결과 출력 및 CSV 저장 |
| [run_validation_set.py](run_validation_set.py) | 기존 명령을 위한 호환 진입점 |
| [test_layer_assignment.py](test_layer_assignment.py) | 레이어 환경·행동·도달·보상·검증 회귀 검사 |
| [test_layer_training.py](test_layer_training.py), [test_validation_dataset.py](test_validation_dataset.py) | 학습·평가 및 검증 데이터셋 검사 |
| [validator_adapter.py](validator_adapter.py) | 내장 Validator 연결과 궤적 자료 변환 |
| [export_trajectories.py](export_trajectories.py) | 검증 입력 해시 확인, trajectory로부터 적층 STL 생성 |
| [environment/src/waam_validator](environment/src/waam_validator) | 공식 Validator backend |

```powershell
python -m unittest test_layer_assignment test_layer_training test_validation_dataset -v
```

경로의 가능한 형태는 현재 윤곽·채움 생성기와 7개 행동 설정에 한정됩니다. 형상 평가는 명목 비드 단면의 합집합이며 열변형·온도·실제 재료 거동을 예측하지 않습니다. 충돌 판정은 Validator의 arm envelope/TCP 및 시간·거리 샘플링 모델을 따르며 실제 로봇의 전체 관절 운동학을 대신하지 않습니다. 직렬 대체 일정은 실행 가능성을 높이는 절차이고, 병렬 사용률이나 시간 최적성을 보장하지 않습니다.

관련 문서: [Validator 방법론](environment/docs/validation-method.md), [설정 참조](environment/docs/config-reference.md), [결과 해석](environment/docs/results-reference.md).

이전 1.0.1 선분 학습은 형제 폴더 `version 1.0.1/AInalgos2-main`에 보관합니다. 1.0.2 실행 루트의 일회성 이동 검증·과거 결과표 생성 코드는 [migration 이력](results/migration/ARCHIVE.md)으로 옮겼습니다. `environment/`의 Validator 1.0.1 코드는 현재 학습·평가에도 필요합니다.

## 2026-10-17 실행 결과

RTX 3070 Ti Laptop GPU에서 CUDA로 **128 레이어 step 학습을 106.06초에 완료**하고 모델을 저장했습니다. PPO 파라미터와 Adam 모멘트가 `cuda:0`에 있음을 확인했습니다. 별도 sample 재평가는 1/1 레이어 완료 후 공식 PASS, IoU 0.988872였습니다.

저장 모델로 STL 01~06을 각각 한 번 평가해 **6개 모두 전체 공식 Validator PASS, 충돌 0건**을 확인했습니다. 완료 레이어 수는 각각 6, 8, 6, 50, 350, 51이며, 총 471개 레이어입니다. 테스트 44개도 통과했습니다.

이 128 step은 동작 확인용이며 수렴 학습이 아닙니다. 이번 학습 rollout은 01·02·05에 각각 6·8·114 step을 사용했고, 평가는 STL 6개 전체를 수행했습니다. STL 평가 실행 중 최종 검증 중복을 제거했으므로 해당 STL 실행 시간에는 이전 중복 검증 비용이 포함됩니다. 최종 코드와 별도 sample 재평가는 저장된 공식 결과 및 입력 해시를 확인해 전체 검증을 한 번만 수행합니다.

- [실행 결과표와 경로·보고서 위치](results/layer_evaluation/layers_1.0.2_20261017_run01/RUN_RESULT.md)
- [저장 학습 모델](results/training/layers_1.0.2_20261017_run01/ppo_model.zip)
- [학습 설정·실제 CUDA 장치·소요 시간](results/training/layers_1.0.2_20261017_run01/training.json)
- [STL 전체 평가 JSON](results/layer_evaluation/layers_1.0.2_20261017_run01/evaluation.json)
- [sample 평가 JSON](results/layer_evaluation/layers_1.0.2_20261017_sample/evaluation.json)
- [테스트 결과](results/integration/layer_v102_tests.json)
