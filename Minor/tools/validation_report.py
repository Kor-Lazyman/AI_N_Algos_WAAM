"""Summarize one Minor training run without running or changing its policies."""
import argparse
import json
import time
from html import escape
from pathlib import Path


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def report(run):
    settings = read(run / 'training.json')
    evaluations = [read(p) for p in sorted((run / 'validation').glob('step_*/evaluation.json'))]
    if not evaluations:
        return settings['status']
    first, last = evaluations[0], evaluations[-1]
    lines = ['# Minor training validation', '',
             f"Status: **{settings['status']}**; completed updates: {settings.get('completed_updates', 0)}/{settings['requested_updates']}.",
             f"CUDA: {settings.get('actual_device')}; early stopping: {settings['early_stopping']}.",
             f"Latest evaluated update: {last['summary']['update']}; best step: {settings.get('best_step')}.", '',
             'Initial and latest evaluations use the same held-out inputs and seeds. Makespan is simulated schedule time; wall time is computation time.', '',
             '| Validation | Initial PASS | Latest PASS | Initial makespan (s) | Latest makespan (s) | Reduction (%) | Latest IoU | Wall (s) |',
             '|---|---|---|---:|---:|---:|---:|---:|']
    jobs = [job for job in last['validation_jobs'] for _ in last['seeds']]
    for job, before, after in zip(jobs, first['episodes'], last['episodes']):
        a, b = before.get('makespan_s'), after.get('makespan_s')
        reduction = f'{100*(a-b)/a:.2f}' if a and b and before['success'] and after['success'] else 'N/A'
        fmt = lambda value: f'{value:.2f}' if value is not None else 'N/A'
        lines.append(f"| {job['id']} | {before['status']} | {after['status']} | {fmt(a)} | {fmt(b)} | {reduction} | {after['iou']:.6f} | {after['wall_time_s']:.2f} |")
    lines += ['', '## Validation history', '', '| Update | PASS rate | Mean IoU | Mean makespan (s) |', '|---:|---:|---:|---:|']
    for evaluation in evaluations:
        summary = evaluation['summary']
        durations = [r['makespan_s'] for r in evaluation['episodes'] if r['success']]
        mean = f'{sum(durations)/len(durations):.2f}' if durations else 'N/A'
        lines.append(f"| {summary['update']} | {summary['pass_rate']:.1%} | {summary['iou_mean']:.6f} | {mean} |")
    lines += ['', 'Mean makespan includes PASS episodes only; compare with PASS rate. Negative reduction means a longer schedule.', '',
              f"Latest artifacts: [validation/{'step_' + str(last['model_timesteps']).zfill(8)}](validation/{'step_' + str(last['model_timesteps']).zfill(8)})", '',
              'Model selection retains the best validation pair separately; the last pair is always saved after all requested updates.']
    (run / 'VALIDATION_REPORT.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    signature = [(e['model_timesteps'], e['summary']['pass_rate']) for e in evaluations]
    if signature != getattr(report, '_signature', None):
        # A standalone SVG keeps this reporting helper dependency-free.
        maximum = max((e.get('makespan_s') or 0 for stage in (first,last) for e in stage['episodes']), default=1) or 1
        svg = ['<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="470" viewBox="0 0 1000 470">',
               '<rect width="1000" height="470" fill="#f8fafc"/>',
               '<g font-family="Arial, sans-serif" fill="#192c40">',
               f'<text x="40" y="36" font-size="23">Minor validation: before vs update {last["summary"]["update"]}</text>',
               '<text x="40" y="66" font-size="14">Makespan (seconds). Shorter is better; compare only valid schedules.</text>',
               '<rect x="40" y="83" width="14" height="14" fill="#9aaec4"/><text x="62" y="95">Before</text>',
               '<rect x="160" y="83" width="14" height="14" fill="#177c82"/><text x="182" y="95">Latest</text>']
        width = 900 / max(1, len(jobs))
        for i, (job, before, after) in enumerate(zip(jobs, first['episodes'], last['episodes'])):
            x = 50 + i*width
            for offset, record, color in ((0,before,'#9aaec4'),(width*.38,after,'#177c82')):
                value = record.get('makespan_s') or 0
                h = value / maximum * 230
                color = color if record['success'] else '#c84949'
                svg.append(f'<rect x="{x+offset}" y="{365-h}" width="{width*.30}" height="{h}" fill="{color}"/>')
                svg.append(f'<text x="{x+offset}" y="{355-h}" font-size="12">{value:.1f}</text>')
            svg.append(f'<text x="{x}" y="395" font-size="12">{escape(job["id"])}</text>')
            svg.append(f'<text x="{x}" y="416" font-size="12">{escape(after["status"])} / IoU {after["iou"]:.3f}</text>')
        svg += ['</g></svg>']
        (run / 'validation_progress.svg').write_text(''.join(svg), encoding='utf-8')
        report._signature = signature
    svg = (run / 'validation_progress.svg').read_text(encoding='utf-8')
    html, in_table = [], False
    for line in lines:
        if line.startswith('|'):
            if line.startswith('|---'):
                continue
            if not in_table:
                html.append('<table>')
                in_table = True
            html.append('<tr>'+''.join('<td>'+escape(cell.strip())+'</td>' for cell in line.strip('|').split('|'))+'</tr>')
        else:
            if in_table:
                html.append('</table>')
                in_table = False
            tag = 'h2' if line.startswith('#') else 'p'
            html.append(f'<{tag}>'+escape(line.lstrip('# ').replace('**',''))+f'</{tag}>')
    (run / 'validation.html').write_text('<!doctype html><html><meta charset="utf-8"><meta http-equiv="refresh" content="15"><title>Minor validation</title><style>body{font-family:Arial;margin:24px;background:#f8fafc;color:#192c40}svg{max-width:100%;height:auto}table{border-collapse:collapse;background:white}td{padding:10px;border-bottom:1px solid #dde3e9}tr:first-child{font-weight:bold;background:#e5eef5}p{line-height:1.5}</style>'+svg+''.join(html)+'</html>', encoding='utf-8')
    return settings['status']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('--watch', action='store_true', help='Refresh until training finishes')
    args = parser.parse_args()
    while True:
        try:
            status = report(args.run.resolve())
        except (FileNotFoundError, json.JSONDecodeError):
            status = 'pending'
        if not args.watch or status in ('completed', 'failed', 'interrupted'):
            break
        time.sleep(15)
