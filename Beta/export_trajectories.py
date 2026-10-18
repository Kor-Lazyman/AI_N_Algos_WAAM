"""Export deposited STL from existing, verified trajectories without rerunning PPO.

Example: python export_trajectories.py --evaluation result/layer_evaluation/RUN
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import time

from validator_adapter import load_config
from waam_validator.provenance import input_signature
from waam_validator.shape.deposition import build_deposited_layers
from waam_validator.shape.mesh_export import export_deposited_stl
from waam_validator.trajectory.loader import load_trajectory_csv
from waam_validator.trajectory.validator import validate_trajectory_set


def export_episode(episode: Path) -> dict:
    """Require an official PASS with matching input content before exporting."""
    episode = Path(episode)
    job = episode / 'input'
    signature = input_signature(job)
    validation = episode / 'validation'
    summary = json.loads((validation / 'summary.json').read_text(encoding='utf-8'))
    manifest = json.loads((validation / 'validation_inputs.json').read_text(encoding='utf-8'))
    if summary.get('status') != 'PASS':
        raise ValueError('Only Validator PASS trajectories can be exported')
    # Copying between folders may change timestamps; content hashes must match.
    if {k: v['sha256'] for k, v in signature.items()} != {
            k: v['sha256'] for k, v in manifest['inputs'].items()}:
        raise ValueError('Validated trajectory/config/target content has changed')
    started = time.perf_counter()
    config = load_config(job / 'config.yaml')
    trajectories = load_trajectory_csv(job / 'trajectory.csv', config)
    if validate_trajectory_set(trajectories, config).violations:
        raise ValueError('Trajectory validation failed during export')
    layers = build_deposited_layers(trajectories, config)
    temporary = episode / '.deposited.stl.tmp'
    try:
        export_deposited_stl(layers, config, temporary)
        if input_signature(job) != signature:
            raise ValueError('Inputs changed during STL export')
        temporary.replace(episode / 'deposited.stl')
    finally:
        temporary.unlink(missing_ok=True)
    result = dict(status='READY', validation_status='PASS',
                  trajectory='input/trajectory.csv', deposited_stl='deposited.stl',
                  layers=len(layers), input_sha256={k: v['sha256'] for k, v in signature.items()},
                  deposited_stl_sha256=hashlib.sha256((episode / 'deposited.stl').read_bytes()).hexdigest(),
                  wall_time_s=time.perf_counter() - started)
    (episode / 'artifacts.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    return result


def export_evaluation(evaluation: Path, output: Path) -> dict:
    """Create one easy-to-find folder per shape and episode with CSV + STL."""
    report = json.loads((evaluation / 'evaluation.json').read_text(encoding='utf-8'))
    if output.exists():
        raise ValueError(f'Choose a new output directory: {output}')
    output.mkdir(parents=True)
    manifest = dict(version='Beta', source_evaluation=str(evaluation.resolve()), shapes=[])
    for index, job in enumerate(report['jobs']):
        for number, _ in enumerate(job['episodes']):
            episode = evaluation / f'job_{index:02d}' / f'episode_{number:03d}'
            artifacts = export_episode(episode)
            # Index prevents duplicate or user-provided IDs from overwriting files.
            name = f'{index + 1:02d}' if len(job['episodes']) == 1 else f'{index + 1:02d}_episode_{number:03d}'
            destination = output / name
            destination.mkdir()
            for filename in ('trajectory.csv', 'config.yaml', 'target.stl'):
                shutil.copy2(episode / 'input' / filename, destination / filename)
            shutil.copy2(episode / 'deposited.stl', destination / 'deposited.stl')
            shutil.copy2(episode / 'validation/summary.json', destination / 'validation_summary.json')
            manifest['shapes'].append(dict(artifacts, id=job['id'], folder=name,
                                          trajectory=f'{name}/trajectory.csv',
                                          deposited_stl=f'{name}/deposited.stl'))
            (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
            print(f"Exported {job['id']}: {destination} ({artifacts['layers']} layers)", flush=True)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evaluation', required=True, type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    export_evaluation(args.evaluation, args.output or args.evaluation / 'exports')


if __name__ == '__main__':
    main()
