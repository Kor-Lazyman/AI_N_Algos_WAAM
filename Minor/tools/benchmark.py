"""Compare original schedules with Minor using the same saved policy actions."""
from __future__ import annotations
import argparse
import importlib.util
import json
from pathlib import Path
import sys
from datetime import datetime
from collections import Counter

import numpy as np
from stable_baselines3 import PPO
from evaluate_layers import ROOT, evaluate_episode, input_hashes, sha256, write_json
from layer_assignment_env import LayerPathEnv
from scheduler import activity_metrics
from tools.gantt import read_intervals, figure_for_job


def original_environment():
    spec = importlib.util.spec_from_file_location('_minor_benchmark_original', ROOT.parent / 'layer_assignment_env.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.LayerPathEnv


class ReplayActions:
    def __init__(self, actions):
        self.actions = iter(actions)

    def predict(self, observation, deterministic=True):
        return np.asarray(next(self.actions)), None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', type=Path, required=True)
    parser.add_argument('--scenarios', type=Path, nargs='+', required=True)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--device', default='cuda')
    parser.add_argument('--first-layer', action='store_true', help='Diagnostic only; does not validate the entire STL')
    args = parser.parse_args()
    output = args.output or ROOT / 'result/benchmark' / datetime.now().strftime('%Y%m%d_%H%M%S')
    output.mkdir(parents=True, exist_ok=False)
    model = PPO.load(args.model, device=args.device)
    original = original_environment()
    report = dict(model=str(args.model.resolve()), model_sha256=sha256(args.model),
                  comparison='same_policy_actions_scheduler_only', first_layer_only=args.first_layer,
                  trained_minor=False, jobs=[])
    for index, scenario in enumerate(args.scenarios):
        jobdir = output / f'job_{index:02d}_{scenario.name}'
        before, after = original(scenario), LayerPathEnv(scenario)
        if args.first_layer:
            observation, _ = before.reset(seed=10042)
            action, _ = model.predict(observation, deterministic=True)
            _, _, _, _, b = before.step(action)
            after.reset(seed=10042)
            _, _, _, _, a = after.step(action)
            record = dict(input=str(scenario.resolve()), input_sha256=input_hashes(scenario), action=action.tolist(),
                          before=b, after=a, full_validator_pass=None)
        else:
            b = evaluate_episode(model, before, 10042, jobdir / 'before')
            b.update(version='1.0.2', environment='layer_path_v1')
            write_json(jobdir / 'before/episode.json', b)
            a = evaluate_episode(ReplayActions([step['action'] for step in b['steps']]), after, 10042, jobdir / 'after')
            b.update(activity_metrics(before.rows, before.makespan))
            a.update(activity_metrics(after.rows, after.makespan))
            record = dict(input=str(scenario.resolve()), input_sha256=input_hashes(scenario),
                before={k: v for k, v in b.items() if k not in ('steps', 'validation')},
                after={k: v for k, v in a.items() if k not in ('steps', 'validation')},
                full_validator_pass=b['success'] and a['success'])
            if record['full_validator_pass']:
                record['makespan_reduction_pct'] = 100*(b['makespan_s']-a['makespan_s'])/b['makespan_s']
                for label, episode in [('before', b), ('after', a)]:
                    figure = figure_for_job(f'{scenario.name}: {label}',
                        read_intervals(jobdir / label / 'input/trajectory.csv'), episode['makespan_s'])
                    figure.write_html(jobdir / f'{label}_gantt.html', include_plotlyjs=True)
        report['jobs'].append(record)
        write_json(output / 'comparison.json', report)
        print(json.dumps(record, ensure_ascii=False), flush=True)
        before.close()
        after.close()
    print(f'Results: {output}', flush=True)


if __name__ == '__main__':
    main()
