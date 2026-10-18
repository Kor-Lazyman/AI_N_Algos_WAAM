# Beta: 로봇 영역 기반 레이어 경로 생성

1.0.2 프로젝트 내부의 독립 실험입니다. `../environment/`의 공식 Validator와 기존 Conda `waam`을 사용합니다. 입력 기본값은 부모의 `../train/`, `../validation/`, `../test/`이며 모델·검사 결과는 Beta의 `result/`에 저장합니다.

## 동작

1. STL을 레이어로 슬라이싱한 직후, 각 단면을 로봇별 XY 도달 원과 최근접 base 기준으로 나눕니다. 여러 로봇이 닿는 위치는 base XY 거리가 가장 가까운 로봇이 소유합니다. 동률은 작은 로봇 ID 우선입니다.
2. PPO의 한 행동은 **한 레이어 전체**입니다. 로봇마다 128개의 선분 슬롯이 있고 각 슬롯은 `[시작 X, 시작 Y, 끝 X, 끝 Y, 사용 여부]`입니다. `Box(-1,1,shape=(1920,))`이며 좌표를 레이어 경계 상자에 대응시킵니다. 사용 값이 0보다 큰 슬롯만 사용합니다.
3. PPO 좌표를 목표 단면과 해당 로봇 영역으로 잘라냅니다. 채움선이나 윤곽선을 자동 추가하지 않습니다. 목표 외곽은 비드 반폭에 가깝게 안쪽으로 제한하며, 로봇 사이 내부 경계에는 별도의 간격을 만들지 않습니다.
4. 스케줄러는 가까운 작업을 우선 고려하고, 충돌로 막힌 다른 로봇은 **자기 미완료 목록에서 다른 작업을 탐색**합니다. 동시에 안전한 작업들을 같은 배치로 실행합니다. 대체할 안전한 작업이 없을 때만 기다립니다.
5. 각 배치 후 home 복귀, 레이어 완료 후 다음 레이어로 진행합니다. 배치·레이어 궤적/충돌 검사와 마지막 전체 공식 Validator 검사를 모두 수행합니다.

최근접 거리 기준은 움직이는 TCP가 아닌 **고정 base의 XY 거리**입니다. 영역 소유권은 레이어 안에서 고정됩니다. 연결된 선분은 최대 6개씩 작업으로 묶습니다. 모든 로봇이 동시에 적층할 수 있는지는 실제 형상과 arm/TCP 간격에 따라 달라집니다. 영역 분할만으로 충돌 없는 3대 적층이나 최적 makespan을 보장하지 않습니다. home 복귀 및 배치 종료 대기는 추가 비용입니다. 동시 작업을 전혀 찾지 못한 층은 로봇별 전체 경로로 묶어 중간 home 왕복을 줄인 뒤 전체 검사를 다시 수행합니다.

## 실행

Beta 폴더에서 실행합니다.

```powershell
conda activate waam
python train.py --mode train --device cuda
python train.py --mode test --device cuda --model result/training/<실행>/ppo_model.zip
python -m tools.plan --scenario ../validation/01_rectangle
python -m tools.plan --demo
python -m tools.gantt --evaluation result/plans/<실행>
python -B -m unittest discover -s tests -v
tensorboard --logdir result/tensorboard
```

validation은 학습 중에만 모델 선택에 사용합니다. test는 부모의 독립 test STL 입력이 필요합니다. 부모의 모델과 Beta의 행동·관측 스키마가 달라 **새로 학습해야 합니다**. 학습 기본값은 1,024 레이어 step이며, 이는 수렴을 보장하는 양이 아닙니다. 새로 초기화한 정책은 경로가 비거나 품질 검사에 실패할 수 있습니다. 고차원 행동의 PPO 업데이트에는 target_kl=0.02 제한을 사용합니다.

`tools.plan`은 모델 없이 검사하기 위한 **규칙 기반 좌표 행동**을 만듭니다. 이 데모는 영역 배정·스케줄러·Validator 연결을 검증하며 PPO 학습 성능을 뜻하지 않습니다. `--demo`는 기존 train/01의 로봇 및 충돌 설정 그대로 서로 떨어진 세 적층 영역을 생성합니다.

## 보상과 산출물

한 레이어의 보상은 기존과 같은 `IoU - 0.1 × 레이어 시간 × idle_factor / 기준시간`입니다. `idle_factor=4-세 로봇 활용률 합`이고 이동·적층을 활용 시간으로 셉니다. 마지막 전체 Validator PASS는 +1, FAIL/ERROR는 -1, 유효한 경로를 만들지 못하면 -2입니다. 직접 좌표 학습에서는 형상과 시간 보상을 함께 학습합니다.

- `territory.py`: 슬라이싱 시 영역 배정, 좌표 행동 변환.
- `scheduler.py`: 동시 작업 선택 및 충돌 시 대체 작업 탐색.
- `layer_assignment_env.py`: 한 레이어 step, 1,080차원 관측, 보상·최종 검사.
- `tools/plan.py`: 미학습 검사와 데모 입력 생성.
- `input/trajectory.csv`, `input/territories.geojson`: 로봇 궤적과 레이어별 소유 영역.
- `territories.html`, `gantt/index.html`: 첫 레이어 영역과 로봇 시간표.
- `beta_metrics.json`: 계산시간, makespan, Validator 상태, 실제 동시 **적층** 시간, 작업 교체 수.
- `layer_trace.json`: 배치별 선택 작업과 로봇별 영역 면적.

도달 원은 내부 다각형으로 근사합니다. 허용오차를 넘는 미배정 면적은 실패로 처리합니다. 선분 수는 로봇당 128슬롯으로 제한되며, 클리핑으로 하나의 슬롯이 여러 선분이 될 수 있습니다. 학습 완료 후 전체 STL 재평가·내보내기는 `--export-stl`로 요청합니다. 검증에 통과한 에피소드의 적층 STL은 평가 시 자동 생성됩니다.

검사 속도를 위해 이동 꺾임점/중간점에서 명백한 arm/TCP 충돌을 먼저 제외합니다. 이 빠른 검사는 후보를 거부하는 용도로만 사용하며, 수락 후보와 최종 경로는 전체 Validator 검사도 통과해야 합니다. 데모의 기준 좌표는 비드 폭 5% 폴리곤 단순화 및 낮은 원호 분할을 사용하지만, 평가 target과 PPO 좌표의 목표 형상은 원본 STL 단면입니다.
