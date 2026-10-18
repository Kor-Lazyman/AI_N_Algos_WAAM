"""Compare a reconstructed untrained PPO with a saved 1.0.2 model."""
from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import shutil
from statistics import mean

import plotly.graph_objects as go
from plotly.subplots import make_subplots
from stable_baselines3 import PPO

from evaluate_layers import ROOT, discover_scenarios, evaluate_episode, input_hashes, sha256, write_json
from layer_assignment_env import LayerPathEnv, LayerRewardWeights


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--splits", nargs="+", choices=["train", "validation"], default=["validation", "train"])
    args = parser.parse_args()
    model_path = args.model.resolve()
    settings = json.loads(model_path.with_name("training.json").read_text(encoding="utf-8"))
    if settings["environment"] != "layer_path_v1":
        raise ValueError("This comparison requires the original 1.0.2 model")
    output = args.output or ROOT / "result/comparison" / datetime.now().strftime("before_after_%Y%m%d_%H%M%S")
    output.mkdir(parents=True, exist_ok=False)
    jobs = [(split, scenario) for split in args.splits for scenario in discover_scenarios(ROOT / split)]
    # Freeze exactly the same inputs for both policies; keep source hashes in the report.
    snapshots = []
    for split, source in jobs:
        scenario = output / "inputs" / split / source.name
        scenario.mkdir(parents=True)
        for name in ("config.yaml", "target.stl"):
            shutil.copy2(source / name, scenario / name)
        if input_hashes(source) != input_hashes(scenario):
            raise ValueError(f"Input changed during snapshot: {source}")
        snapshots.append((split, source, scenario))
    shutil.copy2(model_path, output / "trained_snapshot.zip")
    trained = PPO.load(output / "trained_snapshot.zip", device=args.device)
    # There is no saved step-0 checkpoint. Recreate initialization from the saved seed,
    # policy architecture and PPO settings; do not describe this as an archived checkpoint.
    weights = LayerRewardWeights(**settings["reward_weights"])
    template = LayerPathEnv(snapshots[0][2], reward_weights=weights)
    ppo = dict(settings["ppo"], device=args.device)
    initial = PPO(settings["policy"], template, policy_kwargs=trained.policy_kwargs, **ppo)
    initial.save(output / "reconstructed_untrained.zip")
    if initial.observation_space != trained.observation_space or initial.action_space != trained.action_space:
        raise ValueError("Model and current original environment spaces differ")
    report = dict(version="1.0.2", model=str(model_path), model_sha256=sha256(model_path),
                  trained_timesteps=trained.num_timesteps, baseline="reconstructed_untrained_not_archived",
                  initialization_seed=settings["ppo"]["seed"], evaluation_seed=10042,
                  deterministic=True, device=args.device, output=str(output.resolve()),
                  runtime_hashes={name: sha256(ROOT / name) for name in
                                 ("layer_assignment_env.py", "evaluate_layers.py", "validator_adapter.py")},
                  rows=[])
    for split, source, scenario in snapshots:
        row = dict(split=split, input=source.name, source=str(source), input_sha256=input_hashes(scenario))
        for label, model in (("before", initial), ("after", trained)):
            print(f"{split}/{source.name} {label}", flush=True)
            env = LayerPathEnv(scenario, reward_weights=weights)
            try:
                result = evaluate_episode(model, env, 10042, output / split / source.name / label)
            finally:
                env.close()
            row[label] = {key: result[key] for key in
                          ("makespan_s", "status", "success", "iou", "schedule_complete", "wall_time_s")}
        comparable = row["before"]["success"] and row["after"]["success"]
        row["both_pass"] = comparable
        row["reduction_s"] = row["before"]["makespan_s"] - row["after"]["makespan_s"] if comparable else None
        row["reduction_pct"] = 100 * row["reduction_s"] / row["before"]["makespan_s"] if comparable else None
        report["rows"].append(row)
        write_json(output / "comparison.json", report)
        print(json.dumps(row, ensure_ascii=False), flush=True)
    template.close()
    report["summary"] = {}
    for split in args.splits:
        rows = [row for row in report["rows"] if row["split"] == split]
        pairs = [row for row in rows if row["both_pass"]]
        b = mean(row["before"]["makespan_s"] for row in pairs) if pairs else None
        a = mean(row["after"]["makespan_s"] for row in pairs) if pairs else None
        report["summary"][split] = dict(total=len(rows), before_pass=sum(row["before"]["success"] for row in rows),
            after_pass=sum(row["after"]["success"] for row in rows), comparable_pairs=len(pairs),
            before_mean_s=b, after_mean_s=a, reduction_pct=100*(b-a)/b if pairs else None)
    write_json(output / "comparison.json", report)
    lines = ["# 원본 1.0.2 학습 전후 makespan", "",
             f"학습 후: {trained.num_timesteps:,} step. 학습 전: 저장된 seed {settings['ppo']['seed']}와 설정으로 재구성한 미학습 정책입니다. 실제 저장된 step-0 체크포인트는 없습니다.", "",
             "양쪽 모두 현재 원본 환경에서 동일 STL·설정·평가 seed 10042로 deterministic 평가했습니다. 감소율은 전후 모두 Validator PASS인 경우만 계산합니다. 양수는 단축, 음수는 증가입니다. Makespan은 적층 스케줄 시간이며 코드 실행시간이 아닙니다.", "",
             "| 데이터 | STL | 학습 전 (초) | 학습 후 (초) | 단축률 | Validator 전 → 후 | IoU 전 → 후 |",
             "|---|---|---:|---:|---:|---|---|"]
    for row in report["rows"]:
        b, a = row["before"], row["after"]
        fmt = lambda value: f"{value:.2f}" if value is not None else "N/A"
        reduction = f"{row['reduction_pct']:+.2f}%" if row["both_pass"] else "비교 제외"
        lines.append(f"| {row['split']} | {row['input']} | {fmt(b['makespan_s'])} | {fmt(a['makespan_s'])} | {reduction} | {b['status']} → {a['status']} | {b['iou']:.4f} → {a['iou']:.4f} |")
    lines += ["", "요약 (전후 모두 PASS인 동일 STL 쌍):", ""]
    for split, summary in report["summary"].items():
        lines.append(f"- {split}: {json.dumps(summary, ensure_ascii=False)}")
    lines += ["", "validation 중 00_sample은 당시 학습 중 모델 선택에 사용한 샘플이며, 나머지는 이후 추가된 검증 형상입니다. train 결과는 학습에 사용한 형상의 재평가입니다. 단일 seed 결과로 일반적인 학습 효과를 확정할 수는 없습니다.", "", "[Makespan comparison chart](makespan.html)", "", "상세 수치와 입력 해시는 [comparison.json](comparison.json), 각 경로와 공식 검증 결과는 STL별 before/after 폴더에 저장됩니다."]
    (output / "README.md").write_text("\n".join(lines), encoding="utf-8")
    fig = make_subplots(rows=len(args.splits), cols=1, subplot_titles=args.splits)
    for index, split in enumerate(args.splits, start=1):
        rows = [row for row in report["rows"] if row["split"] == split]
        for label, color in (("before", "#8b9aac"), ("after", "#2379bd")):
            fig.add_trace(go.Bar(x=[row["input"] for row in rows], y=[row[label]["makespan_s"] for row in rows],
                name="Untrained (reconstructed)" if label == "before" else f"Trained ({trained.num_timesteps} steps)",
                marker_color=color, marker_pattern_shape=["" if row[label]["success"] else "/" for row in rows],
                text=[row[label]["status"] for row in rows], legendgroup=label, showlegend=index == 1), row=index, col=1)
    fig.update_layout(barmode="group", height=420*len(args.splits), title="Original 1.0.2 makespan; hatched bars fail validation")
    fig.update_yaxes(title_text="Makespan (seconds)")
    fig.write_html(output / "makespan.html", include_plotlyjs=True)
    print(json.dumps(report["summary"], indent=2), flush=True)
    print(f"Report: {output / 'README.md'}", flush=True)


if __name__ == "__main__":
    main()
