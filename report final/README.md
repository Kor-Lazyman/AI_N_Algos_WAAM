# Report final

INE4107 중간보고서 양식에 따라 Main 1.0.2, Minor1, Minor2 결과를 분리했습니다. 개인 정보와 서술형 코멘트 입력란은 직접 작성할 수 있도록 비워 두었습니다.

각 `test-version.py`는 STL 하나와 옆에 있는 `config.yaml`을 사용하며, 결과를 해당 버전의 `output/<stl>_<timestamp>/`에 저장합니다.

## 비교 결과

| 실험 | 학습 타임스텝 | Training STL Validator | Validation STL Validator | Makespan 범위 (s) |
|---|---:|---:|---:|---:|
| 1.0.2 Main Layer PPO | 1024 / 1024 | 6/6 PASS | 6/6 PASS | 2,577.59–437,001.51 |
| Minor1 Placement and Scheduler PPO | 1792 / 2560 | 6/6 PASS | 6/6 PASS | 2,103.39–184,433.40 |
| Minor2 Reward Only PPO | 2560 / 2560 | 6/6 PASS | 6/6 PASS | 2,450.16–390,442.40 |

## 폴더 안내

버전별 `stl_files/`와validation_data/`에는 입력 STL/config, 생성 trajectory CSV, layer trace, WAAM Validator summary JSON·보고서·metrics CSV, Gantt HTML을 보존했습니다. `images/`와 `gantt_images/`에는 STL 및 Gantt SVG가 있고 `pseudocode/`에는 의사코드와 알고리즘 그림이 있습니다.

`model/`에는 best model, checkpoint, training metadata가 있습니다. Minor1은 placement 모델 쌍과 해시 파일을 포함합니다. TensorBoard 자료는 제외했습니다.

실행 예시는 각 버전의 README.md에 있습니다.

## Trajectory files

Each experiment's six training STL trajectories are preserved under its stl_files/job_00-job_05/episode_000/input/trajectory.csv. The six standalone 1.0.2 exports are also included under main/stl_files/exported_trajectory/01-06/trajectory.csv. Validation trajectories remain under each experiment's validation_data/ tree.



