"""Draw the six saved validation schedules of the trained 1.0.2 model.

Run from the 1.0.2 project root with the existing ``waam`` Python environment::

    python plot_trained_model_gantt.py

The script reads the archived trajectories and Validator reports. It does not
run inference again, so the recorded calculation times remain comparable.
"""

from __future__ import annotations

import csv
import hashlib
import html
import json
from pathlib import Path

import plotly.graph_objects as go
from plotly.io import to_html


ROOT = Path(__file__).resolve().parent
EVALUATION = ROOT / "results/layer_evaluation/validation_stl_20261017_latest_runtime"
OUTPUT = EVALUATION / "gantt"
MODES = ("T", "D", "W")
COLORS = {"T": "#2563eb", "D": "#16a34a", "W": "#f59e0b"}
LABELS = {"T": "이동 T", "D": "적층 D", "W": "대기 W"}


def read_intervals(path: Path) -> dict[int, list[tuple[float, float, str]]]:
    rows: dict[int, list[tuple[float, str]]] = {1: [], 2: [], 3: []}
    with path.open(newline="", encoding="utf-8-sig") as stream:
        for row in csv.DictReader(stream):
            robot = int(row["robot_id"])
            if robot not in rows:
                raise ValueError(f"Unexpected robot {robot}: {path}")
            rows[robot].append((float(row["time_s"]), row["mode"]))
    result = {}
    for robot, points in rows.items():
        if len(points) < 2 or abs(points[0][0]) > 1e-8:
            raise ValueError(f"Incomplete robot {robot}: {path}")
        intervals = []
        for (start, mode), (end, _) in zip(points, points[1:]):
            if mode not in MODES or end < start:
                raise ValueError(f"Invalid interval for robot {robot}: {path}")
            if end > start:
                intervals.append((start, end, mode))
        result[robot] = intervals
    return result


def overlap_seconds(intervals: dict[int, list[tuple[float, float, str]]]) -> tuple[float, float]:
    events = []
    for robot_rows in intervals.values():
        for start, end, mode in robot_rows:
            if mode in ("T", "D"):
                events.extend(((start, 1), (end, -1)))
    events.sort()
    simultaneous = triple = 0.0
    busy = 0
    previous = 0.0
    for time_s, change in events:
        delta = time_s - previous
        if busy >= 2:
            simultaneous += delta
        if busy == 3:
            triple += delta
        busy += change
        previous = time_s
    return simultaneous, triple


def figure_for_job(name: str, intervals, makespan: float) -> go.Figure:
    fig = go.Figure()
    for mode in MODES:
        starts, durations, robots, hovers = [], [], [], []
        for robot, entries in intervals.items():
            for start, end, current in entries:
                if current == mode:
                    starts.append(start)
                    durations.append(end - start)
                    robots.append(f"로봇 {robot}")
                    hovers.append(f"로봇 {robot} · {LABELS[mode]}<br>{start:.3f}–{end:.3f} s<br>{end-start:.3f} s")
        fig.add_bar(x=durations, base=starts, y=robots, orientation="h",
                    name=LABELS[mode], marker_color=COLORS[mode],
                    hovertext=hovers, hoverinfo="text")
    fig.update_layout(title=name, barmode="overlay", height=260,
                      margin=dict(l=90, r=30, t=45, b=50),
                      paper_bgcolor="white", plot_bgcolor="white",
                      xaxis=dict(title="시간 (초)", range=[0, makespan * 1.02], showgrid=True),
                      yaxis=dict(categoryorder="array", categoryarray=["로봇 3", "로봇 2", "로봇 1"]),
                      legend=dict(orientation="h", y=1.16, x=0))
    return fig


def main() -> None:
    report = json.loads((EVALUATION / "evaluation.json").read_text(encoding="utf-8"))
    model = Path(report["model"])
    digest = hashlib.sha256(model.read_bytes()).hexdigest()
    if digest != report["model_sha256"]:
        raise ValueError("Saved model hash differs from the evaluation record")
    with (EVALUATION / "per_shape_results.csv").open(newline="", encoding="utf-8-sig") as stream:
        benchmark = {row["input"]: row for row in csv.DictReader(stream)}
    OUTPUT.mkdir(exist_ok=True)
    rows = []
    charts = []
    for index, job in enumerate(report["jobs"]):
        name = job["id"]
        episode = EVALUATION / f"job_{index:02d}" / "episode_000"
        official = json.loads((episode / "validation/summary.json").read_text(encoding="utf-8"))
        intervals = read_intervals(episode / "input/trajectory.csv")
        item = benchmark[name]
        makespan = float(item["makespan_s"])
        if official["status"] != item["validator_status"] or abs(official["schedule"]["makespan_s"] - makespan) > 1e-6:
            raise ValueError(f"Benchmark and Validator differ for {name}")
        if any(abs(entries[-1][1] - makespan) > 1e-6 for entries in intervals.values()):
            raise ValueError(f"Trajectory and makespan differ for {name}")
        simultaneous, triple = overlap_seconds(intervals)
        times = {robot: {mode: sum(end - start for start, end, current in entries if current == mode)
                         for mode in MODES} for robot, entries in intervals.items()}
        row = dict(input=name, calculation_time_s=float(item["calculation_time_s"]),
                   makespan_s=makespan, validator=official["status"],
                   simultaneous_2plus_s=simultaneous, simultaneous_3_s=triple,
                   **{f"robot_{robot}_{mode.lower()}_s": times[robot][mode]
                      for robot in (1, 2, 3) for mode in MODES})
        rows.append(row)
        fig = figure_for_job(name, intervals, makespan)
        fig.write_html(OUTPUT / f"{name}_gantt.html", include_plotlyjs=True)
        charts.append(to_html(fig, full_html=False, include_plotlyjs=index == 0))
    with (OUTPUT / "gantt_metrics.csv").open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    table_rows = "\n".join(
        f"<tr><td><a href='{html.escape(row['input'])}_gantt.html'>{html.escape(row['input'])}</a></td>"
        f"<td>{row['calculation_time_s']:.3f}</td><td>{row['makespan_s']:.3f}</td>"
        f"<td>{row['validator']}</td><td>{row['simultaneous_2plus_s']:.3f}</td>"
        f"<td>{row['simultaneous_3_s']:.3f}</td></tr>" for row in rows)
    page = f"""<!doctype html><html lang='ko'><head><meta charset='utf-8'>
<title>학습 모델 6개 STL Gantt</title><style>
body{{font-family:Arial,sans-serif;max-width:1160px;margin:24px auto;padding:0 18px;color:#17233b}}
table{{border-collapse:collapse;width:100%;margin:18px 0 28px}}th,td{{padding:9px;border:1px solid #d7dce4;text-align:right}}
th:first-child,td:first-child{{text-align:left}}th{{background:#f1f5f9}}section{{margin:28px 0;border-bottom:1px solid #ddd}}
</style></head><body><h1>1.0.2 학습 모델 · 검증 STL 6개 Gantt</h1>
<p>모델: {html.escape(model.name)} · 1,024 layer steps · 기존 저장 평가 결과. T=이동, D=적층, W=대기.
계산시간은 STL 처리 벽시계 시간이며 makespan은 궤적의 시뮬레이션 시간입니다.</p>
<table><thead><tr><th>형상</th><th>계산시간 (초)</th><th>Makespan (초)</th><th>Validator</th>
<th>2대 이상 동시 가동 (초)</th><th>3대 동시 가동 (초)</th></tr></thead>
<tbody>{table_rows}</tbody></table>{''.join(f'<section>{chart}</section>' for chart in charts)}</body></html>"""
    (OUTPUT / "index.html").write_text(page, encoding="utf-8")
    for row in rows:
        print(f"{row['input']:<16} calc={row['calculation_time_s']:.3f}s "
              f"makespan={row['makespan_s']:.3f}s {row['validator']} "
              f"overlap2+={row['simultaneous_2plus_s']:.3f}s overlap3={row['simultaneous_3_s']:.3f}s")
    print(f"Gantt: {OUTPUT / 'index.html'}")


if __name__ == "__main__":
    main()
