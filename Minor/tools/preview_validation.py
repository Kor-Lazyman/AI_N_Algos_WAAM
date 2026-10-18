"""Evaluate a saved training checkpoint on its frozen validation set during a run."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from stable_baselines3 import PPO
from evaluate_layers import evaluate_episode, summarize, write_json, input_hashes
from layer_assignment_env import VERSION, ENVIRONMENT_SCHEMA, LayerRewardWeights
from placement import PlacedLayerEnv, record_model_pair
from train import validation_key


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('--device', default='cuda')
    parser.add_argument('--wait', action='store_true', help='Wait for the first complete paired checkpoint')
    args = parser.parse_args()
    run = args.run.resolve()
    while args.wait and not (run/'checkpoint.pair.json').is_file():
        status = json.loads((run/'training.json').read_text(encoding='utf-8'))['status']
        if status in ('failed', 'interrupted'):
            raise RuntimeError(f'Training ended before the first checkpoint: {status}')
        time.sleep(5)
    settings = json.loads((run/'training.json').read_text(encoding='utf-8'))
    model_path = run/'checkpoint.zip'
    pair = json.loads(model_path.with_suffix('.pair.json').read_text(encoding='utf-8'))
    layer_bytes = model_path.read_bytes()
    placement_bytes = model_path.with_name(pair['placement_file']).read_bytes()
    if hashlib.sha256(layer_bytes).hexdigest() != pair['layer_sha256'] or hashlib.sha256(placement_bytes).hexdigest() != pair['placement_sha256']:
        raise ValueError('Checkpoint pair is being replaced; retry after it is saved.')
    model = PPO.load(io.BytesIO(layer_bytes), device=args.device)
    placement_model = PPO.load(io.BytesIO(placement_bytes), device=args.device)
    step = model.num_timesteps
    output = run/'validation'/f'step_{step:08d}'
    output.mkdir(parents=True, exist_ok=False)
    (output/'model_snapshot.zip').write_bytes(layer_bytes)
    (output/'placement_snapshot.zip').write_bytes(placement_bytes)
    record_model_pair(output/'model_snapshot.zip', output/'placement_snapshot.zip')
    records = []
    for job_index, job in enumerate(settings['validation_jobs']):
        path = Path(job['scenario'])
        if input_hashes(path) != job['input_sha256']:
            raise ValueError('Frozen validation inputs were modified')
        env = PlacedLayerEnv(path, placement_model, reward_weights=LayerRewardWeights())
        try:
            for episode_index, seed in enumerate(settings['eval_seeds']):
                records.append(evaluate_episode(model, env, seed, output/f'job_{job_index:02d}'/f'episode_{episode_index:03d}'))
        finally:
            env.close()
    selection = validation_key(records)
    summary = dict(update=step//settings['ppo']['n_steps'], step=step, **summarize(records),
                   normalized_makespan=-selection[1], selection_key=list(selection))
    write_json(output/'evaluation.json', dict(version=VERSION, environment=ENVIRONMENT_SCHEMA,
        model_timesteps=step, split='validation_set', preview_only=True,
        note='Read-only preview during training; does not change training or best model selection.',
        validation_jobs=settings['validation_jobs'], seeds=settings['eval_seeds'], summary=summary,
        episodes=[{k:v for k,v in record.items() if k not in ('steps','validation')} for record in records]))
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
