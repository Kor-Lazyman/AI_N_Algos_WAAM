"""Compare the exact warm-start policy with the completed minor_2 validation policy."""
from __future__ import annotations

import argparse
from collections import defaultdict
import csv
import hashlib
import json
from pathlib import Path
import sys

from stable_baselines3 import PPO
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from evaluate_layers import evaluate_episode, input_hashes, write_json
from layer_assignment_env import LayerPathEnv, LayerRewardWeights


def activity(trajectory: Path, makespan: float) -> dict:
    """Assign each interval to its starting CSV row's T/D/W mode."""
    rows = defaultdict(list)
    with trajectory.open(newline='', encoding='utf-8') as stream:
        for row in csv.DictReader(stream):
            rows[int(row['robot_id'])].append((float(row['time_s']), row['mode']))
    if sorted(rows) != [1, 2, 3] or makespan <= 0:
        raise ValueError('Expected three robots and a positive makespan')
    per_robot = {}
    for robot, own in sorted(rows.items()):
        totals = dict(T=0.0, D=0.0, W=0.0)
        for (time, mode), (end, _) in zip(own, own[1:]):
            if end < time or mode not in totals:
                raise ValueError('Non-monotonic or unknown trajectory mode')
            totals[mode] += end-time
        if abs(own[-1][0]-makespan) > 1e-4 or abs(sum(totals.values())-makespan) > 1e-4:
            raise ValueError('Trajectory does not span the official makespan')
        per_robot[str(robot)] = dict(deposition_s=totals['D'], travel_s=totals['T'], wait_s=totals['W'],
                                    deposition_utilization=totals['D']/makespan,
                                    active_utilization=(totals['D']+totals['T'])/makespan)
    return dict(per_robot=per_robot,
                mean_deposition_utilization=sum(r['deposition_utilization'] for r in per_robot.values())/3,
                mean_active_utilization=sum(r['active_utilization'] for r in per_robot.values())/3)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('--device', default='cuda')
    args = parser.parse_args()
    run = args.run.resolve()
    metadata = json.loads((run/'training.json').read_text(encoding='utf-8'))
    if metadata.get('status') != 'completed' or metadata.get('actual_timesteps') != metadata.get('requested_timesteps'):
        raise ValueError('The requested training run is not complete')
    before_path = Path(metadata['warm_start']['model'])
    if hashlib.sha256(before_path.read_bytes()).hexdigest() != metadata['warm_start']['sha256']:
        raise ValueError('Warm-start model changed since training')
    after_path = run/'ppo_model.zip'
    last_validation = run/'validation'/f"step_{metadata['actual_timesteps']:08d}"
    before_model = PPO.load(before_path, device=args.device)
    after_model = PPO.load(after_path, device=args.device)
    snapshot_model = PPO.load(last_validation/'model_snapshot.zip', device=args.device)
    if before_model.action_space != after_model.action_space or before_model.observation_space != after_model.observation_space:
        raise ValueError('Before and after policy spaces differ')
    if after_model.num_timesteps != snapshot_model.num_timesteps or not all(
            torch.equal(after_model.policy.state_dict()[name], value)
            for name, value in snapshot_model.policy.state_dict().items()):
        raise ValueError('Final saved model differs from final validation snapshot')

    output = run/'comparison'
    output.mkdir(exist_ok=False)
    comparisons = []
    weights = LayerRewardWeights(**metadata['reward_weights'])
    for index, job in enumerate(metadata['validation_jobs']):
        scenario = Path(job['scenario'])
        if input_hashes(scenario) != job['input_sha256']:
            raise ValueError(f'Frozen validation job changed: {scenario}')
        env = LayerPathEnv(scenario, reward_weights=weights)
        if env.action_space != before_model.action_space or env.observation_space != before_model.observation_space:
            raise ValueError('Policy/environment spaces differ')
        try:
            for episode_index, seed in enumerate(metadata['eval_seeds']):
                before_dir = output/'before'/f'job_{index:02d}'/f'episode_{episode_index:03d}'
                before = evaluate_episode(before_model, env, seed, before_dir, progress_every=0)
                after_dir = last_validation/f'job_{index:02d}'/f'episode_{episode_index:03d}'
                after = json.loads((after_dir/'episode.json').read_text(encoding='utf-8'))
                row = dict(job=job['id'], seed=seed, before=dict(status=before['status'],
                          iou=before['iou'], makespan_s=before['makespan_s']),
                          after=dict(status=after['status'], iou=after['iou'], makespan_s=after['makespan_s']))
                if before['success'] and after['success']:
                    row['before'].update(activity(before_dir/'input/trajectory.csv', before['makespan_s']))
                    row['after'].update(activity(after_dir/'input/trajectory.csv', after['makespan_s']))
                    row['makespan_reduction_pct'] = 100*(before['makespan_s']-after['makespan_s'])/before['makespan_s']
                    row['deposition_utilization_change_pp'] = 100*(row['after']['mean_deposition_utilization']-
                                                                    row['before']['mean_deposition_utilization'])
                comparisons.append(row)
                print(f"{job['id']}: {before['status']} {before['makespan_s']} -> "
                      f"{after['status']} {after['makespan_s']}", flush=True)
        finally:
            env.close()

    def mean(values):
        return sum(values)/len(values) if values else None

    complete = [row for row in comparisons if 'makespan_reduction_pct' in row]
    summary = dict(jobs=len(comparisons), both_pass=len(complete),
                   before_makespan_mean_s=mean([r['before']['makespan_s'] for r in complete]),
                   after_makespan_mean_s=mean([r['after']['makespan_s'] for r in complete]),
                   before_mean_deposition_utilization=mean([r['before']['mean_deposition_utilization'] for r in complete]),
                   after_mean_deposition_utilization=mean([r['after']['mean_deposition_utilization'] for r in complete]),
                   before_mean_active_utilization=mean([r['before']['mean_active_utilization'] for r in complete]),
                   after_mean_active_utilization=mean([r['after']['mean_active_utilization'] for r in complete]))
    if complete:
        summary['makespan_reduction_pct'] = 100*(summary['before_makespan_mean_s']-
                                                   summary['after_makespan_mean_s'])/summary['before_makespan_mean_s']
        summary['deposition_utilization_change_pp'] = 100*(summary['after_mean_deposition_utilization']-
                                                             summary['before_mean_deposition_utilization'])
    data = dict(comparison='initial 1.0.2 warm-start weights vs final minor_2 model',
                source_model=str(before_path), final_model=str(after_path),
                final_validation=str(last_validation), same_inputs=True,
                seeds=metadata['eval_seeds'], utilization_definition='D seconds / full official makespan, averaged over 3 robots',
                active_utilization_definition='(D+T) seconds / full official makespan, averaged over 3 robots',
                summary=summary, jobs=comparisons)
    write_json(output/'comparison.json', data)
    with (output/'comparison.csv').open('w', newline='', encoding='utf-8-sig') as stream:
        writer = csv.writer(stream)
        writer.writerow(['job','seed','before_status','after_status','before_makespan_s','after_makespan_s',
                         'makespan_reduction_pct','before_D_utilization_pct','after_D_utilization_pct',
                         'D_utilization_change_pp','before_DT_utilization_pct','after_DT_utilization_pct',
                         'before_robot1_D_pct','before_robot2_D_pct','before_robot3_D_pct',
                         'after_robot1_D_pct','after_robot2_D_pct','after_robot3_D_pct'])
        for row in comparisons:
            b,a = row['before'],row['after']
            pct = lambda d,k: 100*d[k] if k in d else None
            writer.writerow([row['job'],row['seed'],b['status'],a['status'],b['makespan_s'],a['makespan_s'],
                row.get('makespan_reduction_pct'),pct(b,'mean_deposition_utilization'),pct(a,'mean_deposition_utilization'),
                row.get('deposition_utilization_change_pp'),pct(b,'mean_active_utilization'),pct(a,'mean_active_utilization'),
                *(100*b['per_robot'][str(i)]['deposition_utilization'] if 'per_robot' in b else None for i in (1,2,3)),
                *(100*a['per_robot'][str(i)]['deposition_utilization'] if 'per_robot' in a else None for i in (1,2,3))])
    lines = ['# minor_2: before and after training', '',
             'Before = original 1.0.2 model weights used to initialize this training run. After = final model at 2,560 layer steps.',
             'Both use the exact frozen validation STL/config inputs and the same deterministic evaluation seeds.',
             'D utilization = deposition seconds / official makespan, averaged across the three robots. T and W are excluded.',
             '', '| Validation STL | Validator before → after | Makespan before → after (s) | Reduction | D utilization before → after |',
             '|---|---|---:|---:|---:|']
    for row in comparisons:
        b,a = row['before'],row['after']
        util = f"{100*b['mean_deposition_utilization']:.1f}% → {100*a['mean_deposition_utilization']:.1f}%" if 'mean_deposition_utilization' in b else 'N/A'
        delta = f"{row['makespan_reduction_pct']:+.2f}%" if 'makespan_reduction_pct' in row else 'N/A'
        fmt = lambda value: f'{value:.2f}' if value is not None else 'N/A'
        lines.append(f"| {row['job']} | {b['status']} → {a['status']} | {fmt(b['makespan_s'])} → {fmt(a['makespan_s'])} | {delta} | {util} |")
    lines.extend(['', f"Both Validator PASS: {summary['both_pass']}/{summary['jobs']}.",
                  (f"Mean makespan: {summary['before_makespan_mean_s']:.2f} → {summary['after_makespan_mean_s']:.2f} s ({summary['makespan_reduction_pct']:+.2f}% reduction)." if complete else 'Mean makespan: N/A.'),
                  (f"Mean D utilization: {100*summary['before_mean_deposition_utilization']:.2f}% → {100*summary['after_mean_deposition_utilization']:.2f}% ({summary['deposition_utilization_change_pp']:+.2f} percentage points)." if complete else 'Mean D utilization: N/A.'),
                  'Per-robot D and D+T utilization, IoU, exact timing, and input provenance are in comparison.csv and comparison.json.',
                  'A positive reduction means shorter makespan; a negative reduction means longer makespan.', ''])
    (output/'README.md').write_text('\n'.join(lines), encoding='utf-8')
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == '__main__':
    main()
