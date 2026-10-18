from pathlib import Path
import html,json

ROOT=Path(__file__).resolve().parents[1]
names={"01":"01 Honeycomb","02":"02 Spiral","03":"03 Triangular truss","04":"04 Motor inner","05":"05 Twisted shell","06":"06 Angle frame",
       "00_sample":"00 sample","01_rectangle":"01 rectangle","02_triangle":"02 triangle","03_l_shape":"03 L shape","04_cross":"04 cross","05_ring":"05 ring"}

for variant in ('main','minor1','minor2'):
    for kind,root_name in [('stl_files','stl_files'),('validation_data','validation_data')]:
        folder=ROOT/variant/root_name; rows=[]
        for target in sorted(folder.rglob('target.stl')):
            if target.parent.name!='input':continue
            episode=target.parent.parent
            stem=episode.parent.name
            ident=stem.replace('job_','')
            try:eval_data=json.loads((folder/'evaluation.json').read_text(encoding='utf-8'))
            except Exception:eval_data={}
            if eval_data.get('jobs'):
                try: ident=eval_data['jobs'][int(ident)]['id']
                except (ValueError,IndexError,KeyError):pass
            name=names.get(ident,ident)
            summary=episode/'validation'/'summary.json'
            validator=json.loads(summary.read_text(encoding='utf-8')) if summary.exists() else {}
            chart=folder/'gantt'/f'{ident}_gantt.html'
            if not chart.exists():chart=folder/'gantt'/f'{stem}_gantt.html'
            image=folder/'images'/f'{stem}_episode_000_input_target_target.svg'
            if not image.exists():
                matches=list((folder/'images').glob(f'{stem}*target.svg'))
                image=matches[0] if matches else None
            links=[]
            if image:links.append(("STL image",image.relative_to(folder)))
            links.extend([("trajectory.csv",episode/'input'/'trajectory.csv'),("Gantt HTML",chart),("Validator JSON",summary),("Validator report",episode/'validation'/'validation_report.md')])
            cells=''.join(f'<a href="{html.escape(Path(path).relative_to(folder).as_posix())}">{label}</a> ' for label,path in links if Path(path).exists())
            rows.append(f'<tr><td>{html.escape(name)}</td><td>{html.escape(str(validator.get("status","")))}</td><td>{cells}</td></tr>')
        page='<!doctype html><html lang="ko"><meta charset="utf-8"><title>'+variant+' '+kind+'</title><style>body{font:15px Arial;margin:32px;color:#17233b}table{border-collapse:collapse;width:100%}th,td{border:1px solid #ccd3df;padding:10px;text-align:left}th{background:#eff4fa}a{margin-right:10px}</style><h1>'+variant+' '+kind+'</h1><table><tr><th>STL</th><th>Validator</th><th>Artifacts</th></tr>'+''.join(rows)+'</table></html>'
        (folder/'index.html').write_text(page,encoding='utf-8')
        print(f'{variant}/{kind}: {len(rows)} items')
