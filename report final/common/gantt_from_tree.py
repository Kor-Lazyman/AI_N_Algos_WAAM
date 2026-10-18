from pathlib import Path
import json, sys, html
from plotly.io import to_html
import gantt

root=Path(sys.argv[1]).resolve(); out=root/'gantt';out.mkdir(exist_ok=True)
charts=[]; rows=[]
for summary_path in sorted(root.rglob('validation/summary.json')):
    episode=summary_path.parent.parent
    csv_path=episode/'input'/'trajectory.csv'
    if not csv_path.exists():continue
    summary=json.loads(summary_path.read_text(encoding='utf-8'))
    name=episode.parent.name
    makespan=float(summary.get('schedule',{}).get('makespan_s',0))
    intervals=gantt.read_intervals(csv_path)
    fig=gantt.figure_for_job(name,intervals,makespan)
    filename=f'{name}_gantt.html';fig.write_html(out/filename,include_plotlyjs=True)
    charts.append(to_html(fig,full_html=False,include_plotlyjs=not charts))
    rows.append(f'<tr><td>{html.escape(name)}</td><td>{makespan:.3f}</td><td>{html.escape(summary.get("status",""))}</td><td><a href="{filename}">Gantt</a></td><td><a href="../{episode.relative_to(root).as_posix()}/validation/summary.json">Validator JSON</a></td></tr>')
page='<!doctype html><html lang="ko"><meta charset="utf-8"><title>Validation Gantt</title><h1>Validation results</h1><table border="1"><tr><th>File</th><th>Makespan (s)</th><th>Validator</th><th>Chart</th><th>JSON</th></tr>'+''.join(rows)+'</table>'+''.join(f'<section>{chart}</section>' for chart in charts)+'</html>'
(out/'index.html').write_text(page,encoding='utf-8')
print(f'{len(rows)} validation charts: {out / "index.html"}')
