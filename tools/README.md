# 보조 도구

프로젝트 루트에서 실행합니다. 학습과 최종 평가는 train.py --mode train 또는 test를 사용합니다.

python -m tools.gantt --evaluation result/layer_evaluation/RUN
python -m tools.benchmark --test-dir test --device cuda
python -m tools.generate_validation_stls --output NEW_VALIDATION

gantt.py: 저장된 평가의 궤적과 Validator 결과에서 HTML Gantt와 CSV를 생성합니다.
benchmark.py: test 평가를 실행하고 형상별 계산 시간, makespan, PASS를 CSV로 저장합니다.
generate_validation_stls.py: 새 검증 STL 세트를 만들 때 사용합니다.
