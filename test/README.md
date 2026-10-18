# 최종 평가 입력

학습·검증에 사용하지 않은 STL을 아래 구조로 넣으세요. 현재 폴더에는 STL이 없습니다.

```text
test/
  01_custom/
    target.stl
    config.yaml
```

프로젝트 루트에서 `python train.py --mode test --device cuda`로 실행합니다.
`--model 경로`로 모델을 지정하고, `--test-dir 경로`로 입력 폴더를 변경할 수 있습니다.
학습·검증 세트와 동일한 STL 해시 또는 test 내부 중복은 오류로 처리합니다.
결과는 `result/layer_evaluation/`에 저장합니다. 코드 테스트는 별도 `tests/`에 있습니다.
