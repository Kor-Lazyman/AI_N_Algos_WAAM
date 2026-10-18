"""PPO 재학습 전, 영역 배정과 동시 스케줄을 실제 Validator로 검사한다."""
from __future__ import annotations
import argparse
import json
import shutil
import time
from datetime import datetime
from pathlib import Path

from evaluate_layers import ROOT, evaluate_episode, input_hashes, summarize, write_json
from layer_assignment_env import LayerPathEnv, VERSION, ENVIRONMENT_SCHEMA
from territory import reference_action


def make_demo(destination):
    """원본 train 셀 설정 그대로, 서로 떨어진 3개 적층 영역을 만든다."""
    import trimesh
    destination.mkdir()
    shutil.copy2(ROOT.parent / 'train/01/config.yaml', destination / 'config.yaml')
    meshes = []
    for x, y in ((-450, 0), (225, 389.71), (225, -389.71)):
        mesh = trimesh.creation.box(extents=(64, 64, 2))
        mesh.apply_translation((x, y, 1))
        meshes.append(mesh)
    trimesh.util.concatenate(meshes).export(destination / 'target.stl')
    return destination


def territory_chart(env, output):
    import plotly.graph_objects as go
    from validator_adapter import parts
    layer, target = env.layers[0]
    colors = ['#2563eb', '#16a34a', '#ef4444']
    figure = go.Figure()
    for r, region in enumerate(env.territories[layer]):
        for index, polygon in enumerate(parts(region, 'Polygon')):
            x, y = polygon.exterior.xy
            figure.add_scatter(x=list(x), y=list(y), mode='lines', fill='toself',
                name=f'Robot {r+1}', legendgroup=str(r), showlegend=index == 0,
                line_color=colors[r], opacity=0.6)
            for hole in polygon.interiors:
                x, y = hole.xy
                figure.add_scatter(x=list(x), y=list(y), mode='lines', line_color='black',
                                  showlegend=False)
    figure.update_layout(title='Beta · first-layer nearest-base territories',
                         xaxis_title='X (mm)', yaxis_title='Y (mm)')
    figure.update_yaxes(scaleanchor='x', scaleratio=1)
    figure.write_html(output / 'territories.html', include_plotlyjs=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group()
    source.add_argument('--scenario', type=Path, help='Folder containing target.stl and config.yaml')
    source.add_argument('--demo', action='store_true', help='Create three separated work areas')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(argv)
    output = (args.output or ROOT/'result/plans'/datetime.now().strftime('%Y%m%d_%H%M%S_%f')).resolve()
    output.mkdir(parents=True, exist_ok=False)
    scenario = make_demo(output/'demo_input') if args.demo else (args.scenario or ROOT.parent/'validation/01_rectangle').resolve()
    started = time.perf_counter()
    env = LayerPathEnv(scenario)
    class ReferencePolicy:
        def predict(self, observation, deterministic=True):
            return reference_action(env), None
    try:
        territory_chart(env, output)
        record = evaluate_episode(ReferencePolicy(), env, 42, output/'job_00/episode_000')
    finally:
        env.close()
    wall = time.perf_counter()-started
    job = dict(id=scenario.name, scenario=str(scenario), input_sha256=input_hashes(scenario),
               job_wall_time_s=wall, summary=summarize([record]),
               episodes=[{key: value for key, value in record.items() if key not in ('steps', 'validation')}])
    report = dict(version=VERSION, environment=ENVIRONMENT_SCHEMA, policy_type='reference_not_trained',
                  model=None, model_timesteps=0, split='planner_check', total_jobs=1, completed_jobs=1,
                  jobs=[job], summary=summarize([record]), output=str(output))
    write_json(output/'evaluation.json', report)
    metrics = dict(status=record['status'], calculation_time_s=wall, makespan_s=record['makespan_s'],
        deposition_3_s=sum(step.get('deposition_3_s', 0) for step in record['steps']),
        deposition_2plus_s=sum(step.get('deposition_2plus_s', 0) for step in record['steps']),
        reordered_tasks=sum(step.get('reordered_tasks', 0) for step in record['steps']))
    write_json(output/'beta_metrics.json', metrics)
    if record['schedule_complete'] and record['makespan_s'] is not None:
        from tools.gantt import main as gantt
        gantt(['--evaluation', str(output)])
    print(json.dumps(metrics, indent=2), flush=True)
    print(f'Results: {output}', flush=True)
    return report


if __name__ == '__main__':
    main()
