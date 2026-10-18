from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
NAMES = {
    "main": "1.0.2 Main Layer PPO",
    "minor1": "Minor1 Placement and Scheduler PPO",
    "minor2": "Minor2 Reward Only PPO",
}
PSEUDO = {
    "main": """# 1.0.2 Main Layer PPO pseudocode

1. Load STL mesh, process configuration, robot limits, and PPO checkpoint.
2. Slice the mesh into target layers.
3. For each layer, observe target geometry and current schedule state.
4. The policy chooses hatch angle, bead spacing, start corner, reversal, partition axis, quota, and robot order.
5. Generate contours and hatch segments; assign reachable segments to three robots.
6. Check candidate routes and collisions; select a feasible schedule.
7. Update layer geometry, utilization, makespan, reward, and observation.
8. Export the complete trajectory and run the official WAAM Validator.
""",
    "minor1": """# Minor1 pseudocode

1. Load STL, config, layer-path policy, and paired global-placement policy.
2. Select one XY translation for the full mesh and apply it before slicing.
3. For each layer, choose path parameters and robot partition.
4. Generate candidate routes; check concurrent and staggered starts against collision and reach constraints.
5. Compute per-layer reward; placement reward is the mean over layers of that same STL.
6. Export the full trajectory and run the official WAAM Validator.

Reward gate: when IoU > 0.9, `10 × mean deposition utilization × reference time / layer duration`; otherwise use terminal Validator status.
""",
    "minor2": """# Minor2 pseudocode

1. Load STL, config, and reward-only PPO checkpoint.
2. Slice the target mesh into layers.
3. For each layer, choose path parameters and partition routes across three robots.
4. Generate routes and check reachability, collision constraints, geometry, and schedule.
5. When IoU > 0.9, reward `10 × mean deposition utilization × reference time / layer duration`; otherwise use terminal Validator status.
6. Export the trajectory and run the official WAAM Validator.

This variant has no placement policy.
""",
}

def main():
    lines = [
        "# Report final", "",
        "INE4107 중간보고서 양식에 따라 Main 1.0.2, Minor1, Minor2 결과를 분리했습니다. 개인 정보와 서술형 코멘트 입력란은 직접 작성할 수 있도록 비워 두었습니다.", "",
        "각 `test-version.py`는 STL 하나와 옆에 있는 `config.yaml`을 사용하며, 결과를 해당 버전의 `output/<stl>_<timestamp>/`에 저장합니다.", "",
        "## 비교 결과", "",
        "| 실험 | 학습 타임스텝 | Training STL Validator | Validation STL Validator | Makespan 범위 (s) |", "|---|---:|---:|---:|---:|",
    ]
    for variant in ("main", "minor1", "minor2"):
        data = json.loads((ROOT / variant / "results.json").read_text(encoding="utf-8"))
        train = data["training"]
        train_status = [json.loads(p.read_text(encoding="utf-8")).get("status") for p in (ROOT/variant/"stl_files").rglob("validation/summary.json")]
        val_status = [json.loads(p.read_text(encoding="utf-8")).get("status") for p in (ROOT/variant/"validation_data").rglob("validation/summary.json")]
        times = [r["makespan_s"] for r in data["model_results"] if r["makespan_s"] is not None]
        span = f"{min(times):,.2f}–{max(times):,.2f}" if times else "-"
        steps = f"{train.get('actual_timesteps','-')} / {train.get('requested_timesteps','-')}"
        lines.append(f"| {NAMES[variant]} | {steps} | {sum(x=='PASS' for x in train_status)}/{len(train_status)} PASS | {sum(x=='PASS' for x in val_status)}/{len(val_status)} PASS | {span} |")
    lines += [
        "", "## 폴더 안내", "",
        "버전별 `stl_files/`와 `validation_data/`에는 입력 STL/config, 생성 trajectory CSV, layer trace, WAAM Validator summary JSON·보고서·metrics CSV, Gantt HTML을 보존했습니다. `images/`와 `gantt_images/`에는 STL 및 Gantt SVG가 있고 `pseudocode/`에는 의사코드와 알고리즘 그림이 있습니다.", "",
        "`model/`에는 best model, checkpoint, training metadata가 있습니다. Minor1은 placement 모델 쌍과 해시 파일을 포함합니다. TensorBoard 자료는 제외했습니다.", "",
        "실행 예시는 각 버전의 README.md에 있습니다.",
    ]
    (ROOT/"README.md").write_text("\n".join(lines)+"\n", encoding="utf-8")
    for variant in ("main", "minor1", "minor2"):
        data=json.loads((ROOT/variant/"results.json").read_text(encoding="utf-8")); train=data["training"]
        (ROOT/variant/"pseudocode"/"algorithm.md").write_text(PSEUDO[variant],encoding="utf-8")
        out=[f"# {NAMES[variant]}","","## Training record","",
             f"- Status: `{train.get('status')}`",f"- Updates: {train.get('actual_timesteps','-') // train.get('ppo',{}).get('n_steps',1) if isinstance(train.get('actual_timesteps'),int) else '-'} / {train.get('requested_updates','-')}",
             f"- Timesteps: {train.get('actual_timesteps','-')} / {train.get('requested_timesteps','-')}",
             f"- Best checkpoint step: {train.get('best_step','-')}",f"- Recorded wall time: {train.get('wall_time_s','-')} s","",
             "## Training STL results","","| STL | Makespan (DD:HH:MM:SS) | Calculation (DD:HH:MM:SS) | Validator |","|---|---:|---:|---|"]
        for row in data["model_results"]:
            out.append(f"| {row['model']} | {row['makespan_DD_HH_MM_SS']} | {row['calculation_DD_HH_MM_SS']} | {row['validator']} |")
        out += ["","## Included files","","- Filled report template: this folder's DOCX file","- Single-STL runner: `test-version.py`","- Model and checkpoint: `model/`","- Training STL evaluations: `stl_files/`","- Validation dataset evaluations: `validation_data/`","- Pseudocode: `pseudocode/algorithm.md`","- New runs are written under `output/`","","## Run one STL","","```powershell",r"python test-version.py --stl C:\path\to\target.stl",r"python test-version.py --stl C:\path\to\target.stl --config C:\path\to\config.yaml --device cpu","```","","`--config` defaults to `config.yaml` beside the STL. Each run creates a new timestamped folder under `output/` with trajectory CSV, Validator reports and JSON, and Gantt HTML/SVG."]
        (ROOT/variant/"README.md").write_text("\n".join(out)+"\n",encoding="utf-8")

if __name__ == "__main__": main()
