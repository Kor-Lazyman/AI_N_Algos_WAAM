"""Run one STL through this experiment's saved PPO model and WAAM Validator.

Usage: python test-version.py --stl path/to/target.stl [--config path/to/config.yaml]
All generated files are placed in this folder's output/<run>/ directory.
"""
from __future__ import annotations
import argparse, csv, hashlib, json, shutil, sys, time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
COMMON = HERE.parent / "common"
RUNTIME = HERE / "runtime"
sys.path.insert(0, str(COMMON))
sys.path.insert(0, str(COMMON / "environment" / "src"))
sys.path.insert(0, str(RUNTIME))
import numpy as np
import torch
from stable_baselines3 import PPO
from layer_assignment_env import LayerPathEnv

VARIANT = "minor1"

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stl", required=True, type=Path, help="Single target.stl input file")
    parser.add_argument("--config", type=Path, help="config.yaml; defaults to the STL's sibling config.yaml")
    parser.add_argument("--seed", type=int, default=10042)
    parser.add_argument("--device", choices=("cuda", "cpu"), default="cuda")
    parser.add_argument("--output", type=Path, default=HERE / "output")
    args = parser.parse_args()
    stl = args.stl.resolve(); config = (args.config or stl.parent / "config.yaml").resolve()
    if not stl.is_file() or stl.suffix.lower() != ".stl": parser.error("--stl must name an existing .stl file")
    if not config.is_file(): parser.error(f"Missing config.yaml: {config}")
    if args.device == "cuda" and not torch.cuda.is_available(): parser.error("CUDA is unavailable; pass --device cpu")
    model_path = HERE / "model" / "best_model.zip"
    model = PPO.load(model_path, device=args.device)
    placement_model = None
    if VARIANT == "minor1":
        pair_path = HERE / "model" / "best_model.pair.json"
        pair = json.loads(pair_path.read_text(encoding="utf-8"))
        model_hash = hashlib.sha256(model_path.read_bytes()).hexdigest()
        placement_path = HERE / "model" / pair["placement_file"]
        if pair["layer_sha256"] != model_hash or pair["placement_sha256"] != hashlib.sha256(placement_path.read_bytes()).hexdigest():
            parser.error("Layer/placement checkpoint pair hash mismatch")
        placement_model = PPO.load(placement_path, device=args.device)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = args.output.resolve() / f"{stl.stem}_{stamp}"
    out.mkdir(parents=True, exist_ok=False)
    scenario = out / "scenario"; scenario.mkdir()
    shutil.copy2(stl, scenario / "target.stl"); shutil.copy2(config, scenario / "config.yaml")
    if placement_model is None: env = LayerPathEnv(scenario)
    else:
        from placement import PlacedLayerEnv
        env = PlacedLayerEnv(scenario, placement_policy=placement_model)
    env.evaluate_output = out
    started = time.perf_counter()
    observation, _ = env.reset(seed=args.seed)
    total_reward = 0.0; layers = 0; final_info = {}
    try:
        while not env.done:
            action, _ = model.predict(observation, deterministic=True)
            observation, reward, terminated, truncated, final_info = env.step(np.asarray(action))
            total_reward += float(reward); layers += 1
            if layers % 25 == 0 or terminated:
                print(f"{layers}/{final_info['total_layers']} layers; elapsed={time.perf_counter()-started:.1f}s", flush=True)
    finally: env.close()
    elapsed = time.perf_counter() - started
    validated = json.loads((out / "validation" / "summary.json").read_text(encoding="utf-8"))
    shutil.copy2(out / "input" / "trajectory.csv", out / "trajectory.csv")
    summary = {"variant": VARIANT, "input_stl": str(stl), "model": str(model_path),
        "model_sha256": hashlib.sha256(model_path.read_bytes()).hexdigest(),
        "placement_model": str(HERE / "model" / "best_placement_model.zip") if placement_model else None,
        "device": str(model.device), "layers": layers, "calculation_wall_time_s": elapsed,
        "makespan_s": float(validated["schedule"]["makespan_s"]), "validator_status": validated["status"],
        "reward_sum": total_reward, "iou": validated.get("shape", {}).get("iou")}
    (out / "evaluation.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    write_gantt(out / "trajectory.csv", out / "gantt.html", out / "gantt.svg", stl.stem, summary["makespan_s"])
    print(json.dumps(summary, indent=2, ensure_ascii=False)); print(f"Output: {out}")

def write_gantt(csv_path, html_path, svg_path, title, makespan):
    import plotly.graph_objects as go
    colors = {"T": "#2878B5", "D": "#2B9348", "W": "#F4A261"}
    fig = go.Figure(); rows = {1: [], 2: [], 3: []}
    with csv_path.open(newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f): rows[int(row["robot_id"])].append(row)
    for mode, color in colors.items():
        for robot, points in rows.items():
            for a,b in zip(points, points[1:]):
                if a["mode"] == mode and float(b["time_s"]) > float(a["time_s"]):
                    start=float(a["time_s"]); duration=float(b["time_s"])-start
                    fig.add_bar(x=[duration], base=[start], y=[f"Robot {robot}"], orientation="h", name=mode,
                        marker_color=color, showlegend=robot == 1, hovertemplate=f"Robot {robot} · {mode}<br>%{{base:.2f}} s, duration %{{x:.2f}} s<extra></extra>")
    fig.update_layout(title=title, barmode="overlay", xaxis_title="Time (s)",
        yaxis=dict(categoryorder="array", categoryarray=["Robot 3","Robot 2","Robot 1"]), height=320)
    fig.write_html(html_path, include_plotlyjs=True)
    width,left,right,top,row_h=1200,110,30,65,54; scale=(width-left-right)/max(makespan,1e-9)
    parts=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="260" viewBox="0 0 {width} 260"><rect width="100%" height="100%" fill="white"/><text x="{left}" y="30" font-family="Arial" font-size="20">{title} Gantt | makespan {makespan:.2f}s</text>']
    for i,robot in enumerate((1,2,3)):
        y=top+i*row_h; parts.append(f'<text x="12" y="{y+18}" font-family="Arial" font-size="14">Robot {robot}</text>')
        for a,b in zip(rows[robot],rows[robot][1:]):
            t0=float(a['time_s']);t1=float(b['time_s']);mode=a['mode']
            if mode in colors and t1>t0: parts.append(f'<rect x="{left+t0*scale:.2f}" y="{y}" width="{(t1-t0)*scale:.2f}" height="28" fill="{colors[mode]}"/>')
    parts.append('</svg>'); svg_path.write_text(''.join(parts),encoding='utf-8')

if __name__ == "__main__": main()
