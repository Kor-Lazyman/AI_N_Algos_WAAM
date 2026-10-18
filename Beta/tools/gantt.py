"""Draw Gantt charts from an existing train, validation, or test evaluation.

Run from the 1.0.2 project root with the existing ``waam`` Python environment::

    python -m tools.gantt --evaluation result/layer_evaluation/RUN

The script reads the archived trajectories and Validator reports. It does not
run inference again, so the recorded calculation times remain comparable.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
from pathlib import Path

import plotly.graph_objects as go
from plotly.io import to_html


MODES = ("T", "D", "W")
COLORS = {"T": "#2563eb", "D": "#16a34a", "W": "#f59e0b"}
LABELS = {"T": "이동 T", "D": "적층 D", "W": "대기 W"}
MAX_VISUAL_BINS = 1500


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


def display_intervals(entries, makespan):
    """Keep short paths exact and sample long paths for a responsive browser chart."""
    if len(entries) <= MAX_VISUAL_BINS:
        return entries, False
    width = makespan / MAX_VISUAL_BINS
    shown = []
    pointer = 0
    for index in range(MAX_VISUAL_BINS):
        start = index * width
        end = makespan if index + 1 == MAX_VISUAL_BINS else (index + 1) * width
        midpoint = (start + end) / 2
        while pointer + 1 < len(entries) and entries[pointer][1] <= midpoint:
            pointer += 1
        mode = entries[pointer][2]
        if shown and shown[-1][2] == mode:
            shown[-1] = (shown[-1][0], end, mode)
        else:
            shown.append((start, end, mode))
    return shown, True


def figure_for_job(name: str, intervals, makespan: float) -> go.Figure:
    fig = go.Figure()
    display = {}
    sampled = False
    for robot, entries in intervals.items():
        display[robot], reduced = display_intervals(entries, makespan)
        sampled = sampled or reduced
    for mode in MODES:
        starts, durations, robots, hovers = [], [], [], []
        for robot, entries in display.items():
            for start, end, current in entries:
                if current == mode:
                    starts.append(start)
                    durations.append(end - start)
                    robots.append(f"로봇 {robot}")
                    hovers.append(f"로봇 {robot} · {LABELS[mode]}<br>{start:.3f}–{end:.3f} s<br>{end-start:.3f} s")
        fig.add_bar(x=durations, base=starts, y=robots, orientation="h",
                    name=LABELS[mode], marker_color=COLORS[mode],
                    hovertext=hovers, hoverinfo="text")
    fig.update_layout(title=name + (" · sampled view" if sampled else ""), barmode="overlay", height=260,
                      margin=dict(l=90, r=30, t=45, b=50),
                      paper_bgcolor="white", plot_bgcolor="white",
                      xaxis=dict(title="시간 (초)", range=[0, makespan * 1.02], showgrid=True),
                      yaxis=dict(categoryorder="array", categoryarray=["로봇 3", "로봇 2", "로봇 1"]),
                      legend=dict(orientation="h", y=1.16, x=0))
    return fig


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evaluation", type=Path, required=True, help="Completed evaluation folder")
    parser.add_argument("--output", type=Path, help="Chart folder; defaults to evaluation/gantt")
    args = parser.parse_args(argv)
    evaluation = args.evaluation.resolve()
    output = (args.output or evaluation / "gantt").resolve()
    report = json.loads((evaluation / "evaluation.json").read_text(encoding="utf-8"))
    if len(report["jobs"]) != report["total_jobs"]:
        raise ValueError("The evaluation has not completed")
    if not report["jobs"]:
        raise ValueError("Evaluation has no jobs")
    model_label = "reference planner (not trained)"
    if report.get("model"):
        model = Path(report["model"])
        if hashlib.sha256(model.read_bytes()).hexdigest() != report["model_sha256"]:
            raise ValueError("Saved model hash differs from the evaluation record")
        model_label = model.name
    output.mkdir(exist_ok=True)
    rows = []
    summary_rows = []
    charts = []
    for index, job in enumerate(report["jobs"]):
        name = job["id"]
        if len(job["episodes"]) != 1:
            raise ValueError("Gantt currently expects one episode per shape")
        episode = evaluation / f"job_{index:02d}" / "episode_000"
        official = json.loads((episode / "validation/summary.json").read_text(encoding="utf-8"))
        intervals = read_intervals(episode / "input/trajectory.csv")
        makespan = float(official["schedule"]["makespan_s"])
        if official["status"] != job["episodes"][0]["status"] or abs(float(job["episodes"][0]["makespan_s"]) - makespan) > 1e-6:
            raise ValueError(f"Evaluation and Validator differ for {name}")
        if any(abs(entries[-1][1] - makespan) > 1e-6 for entries in intervals.values()):
            raise ValueError(f"Trajectory and makespan differ for {name}")
        simultaneous, triple = overlap_seconds(intervals)
        times = {robot: {mode: sum(end - start for start, end, current in entries if current == mode)
                         for mode in MODES} for robot, entries in intervals.items()}
        row = dict(input=name, calculation_time_s=float(job["job_wall_time_s"]),
                   makespan_s=makespan, validator=official["status"],
                   simultaneous_2plus_s=simultaneous, simultaneous_3_s=triple,
                   **{f"robot_{robot}_{mode.lower()}_s": times[robot][mode]
                      for robot in (1, 2, 3) for mode in MODES})
        rows.append(row)
        summary_rows.append({key: row[key] for key in ("input", "calculation_time_s", "makespan_s", "validator", "simultaneous_2plus_s", "simultaneous_3_s")})
        fig = figure_for_job(name, intervals, makespan)
        fig.write_html(output / f"{name}_gantt.html", include_plotlyjs=True)
        charts.append(to_html(fig, full_html=False, include_plotlyjs=index == 0))
    with (output / "gantt_metrics.csv").open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    with (output / "per_shape_results.csv").open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(summary_rows[0]))
        writer.writeheader()
        writer.writerows(summary_rows)
    table_rows = "\n".join(
        f"<tr><td><a href='{html.escape(row['input'])}_gantt.html'>{html.escape(row['input'])}</a></td>"
        f"<td>{row['calculation_time_s']:.3f}</td><td>{row['makespan_s']:.3f}</td>"
        f"<td>{row['validator']}</td><td>{row['simultaneous_2plus_s']:.3f}</td>"
        f"<td>{row['simultaneous_3_s']:.3f}</td></tr>" for row in rows)
    page = f"""<!doctype html><html lang='ko'><head><meta charset='utf-8'>
<title>WAAM 평가 Gantt</title><style>
body{{font-family:Arial,sans-serif;max-width:1160px;margin:24px auto;padding:0 18px;color:#17233b}}
table{{border-collapse:collapse;width:100%;margin:18px 0 28px}}th,td{{padding:9px;border:1px solid #d7dce4;text-align:right}}
th:first-child,td:first-child{{text-align:left}}th{{background:#f1f5f9}}section{{margin:28px 0;border-bottom:1px solid #ddd}}
</style></head><body><h1>WAAM Beta 경로 Gantt</h1>
<p>모델: {html.escape(model_label)} · {report['model_timesteps']} layer steps · T=이동, D=적층, W=대기.
계산시간은 STL 로딩·슬라이싱·경로 생성·공식 검증·출력까지의 벽시계 시간이며 makespan은 로봇 궤적의 시뮬레이션 시간입니다.
긴 궤적은 차트 표시만 최대 1500 시간 구간으로 샘플링하며 CSV 지표는 모든 원본 구간으로 계산합니다.</p>
<table><thead><tr><th>형상</th><th>계산시간 (초)</th><th>Makespan (초)</th><th>Validator</th>
<th>2대 이상 동시 가동 (초)</th><th>3대 동시 가동 (초)</th></tr></thead>
<tbody>{table_rows}</tbody></table>{''.join(f'<section>{chart}</section>' for chart in charts)}</body></html>"""
    (output / "index.html").write_text(page, encoding="utf-8")
    for row in rows:
        print(f"{row['input']:<16} calc={row['calculation_time_s']:.3f}s "
              f"makespan={row['makespan_s']:.3f}s {row['validator']} "
              f"overlap2+={row['simultaneous_2plus_s']:.3f}s overlap3={row['simultaneous_3_s']:.3f}s")
    print(f"Gantt: {output / 'index.html'}")


if __name__ == "__main__":
    main()
