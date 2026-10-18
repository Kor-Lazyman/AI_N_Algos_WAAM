# 충돌 예측 기반 local-repair scheduler

현재 완료된 실험은 [local_repair_40updates 결과](result/local_repair_40updates/RESULTS.md)이다. CUDA 40회/2,560 step, early stopping 없이 학습했고 validation 6/6 PASS이다. makespan 합계는 이전 scheduler 3,918.94초 → 새 최종 모델 2,181.15초이며, 원래 minor_2 2,089.44초보다 아직 4.39% 느리다. [Gantt 비교](result/local_repair_40updates/gantt_index.html)와 [최종 모델](result/local_repair_40updates/scheduler_final.zip)을 저장했다.

minor_2의 적층 선분·담당 로봇은 고정하고, scheduler만 학습한다. 기본 실행은 `--mode local-repair`이다. 기존 home 왕복 방식은 `--mode home-tours`로 재현할 수 있다. 두 방식의 action/observation 크기가 다르므로 기존 scheduler 가중치를 새 정책에 그대로 넣지 않는다. minor_2는 기존 학습 모델을 계속 사용한다.

## 실행과 반복 검사

1. 각 로봇은 작업 종료 위치에서 다음 작업으로 직접 이동하는 후보 경로를 만든다. 작업마다 home으로 복귀하지 않는다.
2. 다른 로봇의 이미 예약된 움직임과 후보 경로를 함께 검사한다. 작업 종료 후의 정지 위치도 검사한다.
3. 충돌이 예상되면 상대가 유휴 상태인지 확인한다. 유휴 로봇은 자신의 base 방향 XY로 대피시키고, 선택한 로봇은 대피가 끝난 뒤 시작한다. 대피 자체와 수정된 전체 예약 구간을 다시 검사한다.
4. 첫 대피 이후 다른 충돌이 발견되면 다른 유휴 로봇에 대해서도 수정·재검사를 반복한다. 실행 중인 로봇의 예약을 바꾸거나 적층 선분 중간을 끊지 않는다. 수정할 수 없으면 기다렸다가 재검사하거나 다른 작업을 선택한다.
5. PPO는 허용된 후보 중 작업 순서와 근거리/여유거리 대피, 다음 완료 이벤트 대기, 짧은 재검사 대기를 선택한다. 충돌 검사는 규칙 기반이며 PPO가 무시할 수 없다.
6. 레이어 종료 때만 home으로 복귀한다. 완성된 레이어는 공식 Validator의 충돌 및 trajectory 검사로 다시 확인하고, 전체 STL은 형상 IoU까지 검증한다.

대피는 25 mm 간격 후보와 450/500/600/800/1000 mm 후보를 자신의 base 방향으로 검색한다. 근거리 후보는 이 후보 집합에서 먼저 안전하게 검증된 거리이며 수학적인 전역 최단거리는 아니다. 여유거리 후보는 근거리 대피보다 최소 100 mm 더 멀게 탐색한다. 로컬 후보가 없으면 home 복귀도 검증 후 최후 후보로 허용하며 횟수를 기록한다. 각 작업의 후보가 수정 가능한 다른 로봇은 최대 2대다. 조건이 충족되지 않으면 해당 액션은 마스킹한다.

현재 팔 외피 검사는 XY 기준이므로 Z만 올려서 충돌을 피했다고 처리하지 않는다. 반경 100+100 mm와 clearance 50 mm 설정에서 작은 STL은 동시 적층이 불가능할 수 있다. 이때도 연속 작업과 짧은 대피로 불필요한 이동을 줄일 수 있다. 이 구현은 작업 경계에서 앞으로의 충돌을 예측해 실행 전 수정한다. 이미 적층 중인 비드 중간을 끊고 이동하는 실시간 제어기는 아니다.

## Action, observation, reward

- Action 26개: `WAIT_EVENT`, `RECHECK_WAIT`, 로봇 3 × 작업 후보 4 × 근거리/여유거리 2.
- 충돌 없는 직결 작업은 근거리 슬롯만 사용하며 여유거리 슬롯을 중복 노출하지 않는다.
- Observation 387차원: 진행률·시간·로봇 현재 위치와 예약 시간·후보 적층량·예상 충돌 시각·대피 거리·대피 지연·action mask.
- PPO actor/critic 각각 128×128 MLP, CUDA. minor_2는 별도 고정 모델이다.
- Step reward: `완료 예약 D / 전체 D - 경과시간 / 기준시간 - 0.02 × 대피거리(m)`.
- 종료 reward: `10 × 평균 적층 활용률 × 기준시간 / makespan` 추가. 실패는 -10.
- 평균 적층 활용률: `전체 로봇 D 시간 합 / (3 × makespan)`.

후보 검사에서는 공식 충돌 geometry를 호출하며, 공식 adaptive sampler와 같은 시간·이동 거리 분할 및 float32 보간을 벡터화한다. 중간점 빠른 검사는 거부 용도이며 허용할 때는 조밀한 샘플을 모두 검사한다. 완료 레이어 및 최종 전체 형상에는 기존 공식 Validator를 별도로 실행한다. 시간·공간 샘플 기반 충돌 검사라는 원래 Validator의 한계는 유지된다.

## 실행

PowerShell에서 `scheduler` 폴더로 이동한다.

```powershell
$py = 'C:\Users\lazzyman\anaconda3\envs\waam\python.exe'
& $py train.py --mode local-repair --train-plans plans\train_compact --validation-plans plans\validation_compact --updates 40 --n-steps 64 --device cuda --output result\local_repair_40updates
& $py -m tensorboard.main --logdir result\local_repair_40updates\tensorboard --port 6006
& $py evaluate.py --model result\local_repair_40updates\scheduler_final.zip --plans plans\validation_compact --output result\local_repair_retest --device cuda
```

early stopping은 사용하지 않는다. 출력 폴더는 기존 폴더를 덮어쓰지 않으므로 재실행할 때 새 이름을 지정한다. train_compact는 학습 STL 6개에서 3개 층씩 총 18개 층이며 validation_compact는 별도 STL 6개 전체 8개 층이다. validation에는 gradient update를 적용하지 않는다.

```powershell
& $py selfcheck_local.py --plans plans\validation_compact --all
```

모델, TensorBoard, 실행 당시 source, 학습 episode 로그, 학습 전후 validation 경로 CSV, Gantt HTML, 공식 Validator 결과 및 minor_2 비교를 저장한다. `scheduler_trace.json`의 `predicted_conflict`와 `repairs`에 충돌 예상 시각·관련 로봇·대피 전후 좌표·거리·home fallback을 기록한다. 예측 충돌 시각은 각 제안 시점 기준 상대 시간이다.
