# WAAM 알고리즘 결과 자료

## 실험 폴더

- [main: 기본 1.0.2](main/REPORT.md)
- [Minor: 위치 정책과 스케줄러 개선](Minor/REPORT.md)
- [minor_2: 보상 변경](minor_2/REPORT.md)
- [scheduler: 충돌 국소 대피 PPO](scheduler/REPORT.md)
- [Beta: 영역 지정·직접 경로 prototype](Beta/REPORT.md)
- [minor3: 경로·대피 공동 PPO](minor3/REPORT.md)
- [공통 제출 양식](submission_template.md)
- [계산 병렬 처리 검토](parallel_execution_plan.md)

모델 ID 01–06은 제출 요청에 적힌 Honeycomb, Spiral, Triangular truss, Motor inner, Twisted shell, Angle frame 순서로 `train/01`–`train/06`에 대응시켰다. 저장 결과에는 파일 ID와 STL hash를 남겼다. 사람이 붙인 별칭과 실제 STL 외형의 최종 대조는 제출 전에 해 둔다.

측정되지 않은 조합은 `미측정`으로 남겼다. 서로 다른 six-compact validation shapes의 결과를 여섯 제출 STL 결과로 치환하지 않았다. Makespan은 시뮬레이션 schedule time; 계산시간은 그 결과 파일이 기록한 wall-clock evaluation time이다. 별도 실행의 계산시간은 동시 자원 부하 때문에 엄밀한 벤치마크가 아니다.

각 experiment report는 reward/purpose, architecture, pseudocode-style flow, PPO setup, pros/cons, source logs, Validator reports and Gantt links를 모은다. UI screenshot이 저장돼 있지 않은 run은 official `summary.json`과 `validation_report.md`를 제시한다. 실험 출력이 아닌 illustrative UI 이미지로 대체하지 않는다.
