"""Evaluate a version 1.0.2-minor layer-path PPO model with the official Validator."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime
import hashlib
import io
import json
from pathlib import Path
from statistics import mean
import time
import warnings
import zipfile

import numpy as np
import torch
from stable_baselines3 import PPO

from validator_adapter import VALIDATOR_ROOT, run_validation
from export_trajectories import export_episode
from layer_assignment_env import ACTION_DESCRIPTION, ENVIRONMENT_SCHEMA, VERSION, LayerPathEnv, LayerRewardWeights
from waam_validator.errors import WaamValidatorError

ROOT = Path(__file__).resolve().parent
EVALUATION_CRITERION = "complete_schedule_and_validator_pass_v1"
INPUT_NAMES = ("config.yaml", "target.stl")


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def json_value(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Cannot serialize {type(value).__name__}")


def write_json(path: Path, data) -> None:
    """Keep the last complete report if a process is interrupted while writing."""
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=json_value), encoding="utf-8")
    temporary.replace(path)


def input_hashes(scenario: Path) -> dict:
    return {name: sha256(scenario / name) for name in INPUT_NAMES}


def discover_scenarios(stl_dir: Path) -> list[Path]:
    scenarios = sorted({p.parent.resolve() for p in stl_dir.rglob("target.stl")})
    if not scenarios:
        raise ValueError(f"No target.stl jobs found under {stl_dir}")
    for scenario in scenarios:
        if not (scenario / "config.yaml").is_file():
            raise ValueError(f"Missing config.yaml: {scenario}")
    return scenarios


def latest_model(runs_dir: Path) -> Path:
    """Ignore legacy action spaces and unfinished layer-training runs."""
    candidates = []
    for path in runs_dir.rglob("ppo_model.zip"):
        metadata = path.with_name("training.json")
        if not metadata.is_file():
            continue
        try:
            settings = json.loads(metadata.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            warnings.warn(f"Skipping unreadable metadata {metadata}: {exc}")
            continue
        if (isinstance(settings, dict) and settings.get("status") == "completed"
                and settings.get("version") == VERSION
                and settings.get("environment") == ENVIRONMENT_SCHEMA):
            candidates.append(path)
    if not candidates:
        raise ValueError(f"No completed {VERSION} layer-path model found under {runs_dir}")
    return max(candidates, key=lambda p: (p.stat().st_mtime_ns, str(p))).resolve()


def load_training(model_path: Path) -> tuple[dict, bytes]:
    if not model_path.is_file():
        raise ValueError(f"Model not found: {model_path}")
    settings = json.loads(model_path.with_name("training.json").read_text(encoding="utf-8"))
    if settings.get("version") != VERSION or settings.get("environment") != ENVIRONMENT_SCHEMA:
        raise ValueError(f"A {VERSION} layer-path PPO model is required; legacy task models are incompatible")
    # An explicit checkpoint can be evaluated while training continues. Read once.
    model_bytes = model_path.read_bytes()
    with zipfile.ZipFile(io.BytesIO(model_bytes)) as archive:
        if archive.testzip() is not None:
            raise ValueError("Model archive is incomplete; retry after saving finishes")
    return settings, model_bytes


def evaluation_jobs(settings: dict, source: str, stl_dir: Path,
                    validation_dir: Path | None = None, test_dir: Path | None = None) -> list[dict]:
    # 공개 split 이름 train은 기존 저장 보고서의 stl 값과 연결한다.
    if source == "train":
        source = "stl"
    if source == "test":
        # 최종 test는 모델 선택에 사용하지 않은 독립 데이터만 허용한다.
        directory = (test_dir or ROOT.parent / "test").resolve()
        originals = discover_scenarios(directory)
        excluded = {job["input_sha256"]["target.stl"] for job in settings["training_jobs"]}
        for job in settings.get("validation_jobs", [settings.get("validation_job")]):
            if job:
                excluded.add(job["input_sha256"]["target.stl"])
        for folder in (stl_dir, validation_dir or ROOT.parent / "validation"):
            if Path(folder).is_dir():
                excluded.update(input_hashes(path)["target.stl"] for path in discover_scenarios(Path(folder)))
        hashes = [input_hashes(path) for path in originals]
        targets = [item["target.stl"] for item in hashes]
        if len(set(targets)) != len(targets) or excluded.intersection(targets):
            raise ValueError("Test STL must be unique and disjoint from train/validation")
        return [dict(id=path.name, source=str(path), scenario=str(path), input_sha256=digest)
                for path, digest in zip(originals, hashes)]
    if source == "example":
        jobs = [settings["validation_job"]]
    elif source == "stl":
        originals = discover_scenarios(stl_dir)
        current_hashes = sorted((input_hashes(path) for path in originals), key=lambda x: json.dumps(x, sort_keys=True))
        saved_hashes = sorted((job["input_sha256"] for job in settings["training_jobs"]), key=lambda x: json.dumps(x, sort_keys=True))
        if current_hashes != saved_hashes:
            raise ValueError("stl_files inputs differ from this run's training data")
        jobs = settings["training_jobs"]
    elif source == "validation":
        validation_dir = (validation_dir or ROOT.parent / "validation").resolve()
        originals = discover_scenarios(validation_dir)
        current = [input_hashes(path) for path in originals]
        training_targets = {job["input_sha256"]["target.stl"] for job in settings["training_jobs"]}
        if any(item["target.stl"] in training_targets for item in current):
            raise ValueError("Validation STL overlaps the training data")
        if "validation_jobs" in settings:
            jobs = settings["validation_jobs"]
            if sorted(current, key=lambda x: json.dumps(x, sort_keys=True)) != sorted(
                    (job["input_sha256"] for job in jobs), key=lambda x: json.dumps(x, sort_keys=True)):
                raise ValueError("Validation inputs differ from this run's frozen validation data")
        else:
            # Older models only snapshot the official sample. Keep its training
            # metadata immutable while recording hashes of the external set.
            jobs = [dict(id=path.name, source=str(path), scenario=str(path),
                         input_sha256=digest) for path, digest in zip(originals, current)]
    else:
        raise ValueError("eval-source must be example, validation or stl")
    for job in jobs:
        scenario = Path(job["scenario"])
        if input_hashes(scenario) != job["input_sha256"]:
            raise ValueError(f"Saved input snapshot changed: {scenario}")
    return jobs


def space_schema(env) -> dict:
    return dict(action=dict(type="MultiDiscrete", nvec=env.action_space.nvec.tolist(), fields=ACTION_DESCRIPTION),
                observation=dict(shape=list(env.observation_space.shape), dtype=str(env.observation_space.dtype)))


def evaluate_episode(model, env, seed: int, output: Path, *, progress_every=1) -> dict:
    """Ask the terminal step to save its official validation for reuse below."""
    previous = vars(env).get("evaluate_output")
    had_previous = "evaluate_output" in vars(env)
    env.evaluate_output = output.resolve()
    try:
        return _evaluate_episode(model, env, seed, output, progress_every=progress_every)
    finally:
        if had_previous:
            env.evaluate_output = previous
        else:
            del env.evaluate_output


def completed_validation(env, info: dict, output: Path):
    """Reuse only this episode's saved result with unchanged validated inputs."""
    artifacts = getattr(env, "terminal_validation_artifacts", None)
    if not isinstance(artifacts, dict):
        return run_validation(env.export(output / "input"), output / "validation"), None, False
    if Path(artifacts.get("output", "")).resolve() != output.resolve():
        raise ValueError("Terminal validation belongs to a different episode output")
    job = output / "input"
    actual = {name: sha256(job / name) for name in (*INPUT_NAMES, "trajectory.csv")}
    if actual != artifacts.get("input_sha256"):
        raise ValueError("Terminal validation inputs changed after validation")
    result = getattr(env, "terminal_validation", None)
    if result is not None and (output / "validation/summary.json").is_file():
        validated_signature = getattr(result, "input_signature", None)
        if isinstance(validated_signature, dict):
            validated_hashes = {name: fingerprint.get("sha256")
                                for name, fingerprint in validated_signature.items()}
            if validated_hashes != actual:
                raise ValueError("Terminal inputs differ from the official Validator input signature")
        return result, None, True
    if info.get("terminal_status") == "ERROR" and (output / "validation/error.json").is_file():
        return None, info.get("terminal_error") or "Official terminal validation failed", True
    # A result whose report files disappeared must be regenerated for delivery.
    return run_validation(job, output / "validation"), None, False


def _evaluate_episode(model, env, seed: int, output: Path, *, progress_every=1) -> dict:
    output.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    observation, info = env.reset(seed=seed)
    trace = []
    while not env.done:
        action, _ = model.predict(observation, deterministic=True)
        action = np.asarray(action, dtype=np.int64)
        step_started = time.perf_counter()
        observation, reward, terminated, truncated, info = env.step(action)
        trace.append(dict(info, action=action.tolist(), reward=float(reward),
                          step_wall_time_s=time.perf_counter() - step_started))
        # Persist partial results too, including a failure on the first layer.
        write_json(output / "layer_trace.json", trace)
        if progress_every and len(trace) % progress_every == 0:
            print(f"    layers {info['completed_layers']}/{info['total_layers']}, "
                  f"IoU={info['iou']:.6f}, reward={float(reward):.6f}, "
                  f"wall={time.perf_counter() - started:.1f}s", flush=True)
        if terminated or truncated:
            break
    record = dict(
        version=VERSION, environment=ENVIRONMENT_SCHEMA, seed=seed,
        evaluation_criterion=EVALUATION_CRITERION, step_unit="layer",
        episode_reward=sum(step["reward"] for step in trace), episode_length=len(trace),
        schedule_complete=bool(info["schedule_complete"]),
        completed_layers=int(info["completed_layers"]), total_layers=int(info["total_layers"]),
        status="INFEASIBLE", success=False, iou=float(info["iou"]),
        makespan_s=None, partial_makespan_s=float(info["makespan_s"]),
        failure_reason=info.get("failure_reason"), steps=trace,
    )
    if info["schedule_complete"]:
        try:
            result, terminal_error, reused = completed_validation(env, info, output)
        except WaamValidatorError as exc:
            record.update(status="ERROR", failure_reason=f"{exc.code}: {exc.message}")
        except (OSError, ValueError) as exc:
            record.update(status="ERROR", failure_reason=f"VALIDATION_ARTIFACT_ERROR: {exc}")
        else:
            record["terminal_validation_reused"] = reused
            if terminal_error is not None:
                record.update(status="ERROR", failure_reason=terminal_error)
            else:
                record.update(status=result.status, success=result.status == "PASS",
                              iou=float(result.shape.iou), makespan_s=float(result.schedule.makespan_s),
                              validation=result.summary_dict())
    if record["success"]:
        try:
            record["artifacts"] = export_episode(output)
        except Exception as exc:
            record["artifacts"] = dict(status="ERROR", error=f"{type(exc).__name__}: {exc}")
            # Keep official validation status separate from export status.
            print(f"STL export failed: {exc}", flush=True)
    record["wall_time_s"] = time.perf_counter() - started
    write_json(output / "episode.json", record)
    return record


def summarize(records: list[dict]) -> dict:
    if not records:
        raise ValueError("At least one evaluation episode is required")
    completed_times = [r["makespan_s"] for r in records if r["makespan_s"] is not None]
    successful_times = [r["makespan_s"] for r in records if r["success"]]
    return dict(episodes=len(records), step_unit="layer",
                completion_rate=mean(float(r["schedule_complete"]) for r in records),
                pass_rate=mean(float(r["schedule_complete"] and r["status"] == "PASS") for r in records),
                success_rate=mean(float(r["success"]) for r in records),
                ep_rew_mean=mean(r["episode_reward"] for r in records),
                ep_len_mean=mean(r["episode_length"] for r in records),
                iou_mean=mean(r["iou"] for r in records),
                makespan_completed_mean_s=mean(completed_times) if completed_times else None,
                makespan_success_mean_s=mean(successful_times) if successful_times else None)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs-dir", type=Path, default=ROOT / "result/training")
    parser.add_argument("--model", type=Path, help="Explicit model ZIP with adjacent training.json")
    # --split은 평가할 입력 종류이며, --eval-source는 이전 명령 호환용이다.
    split_group = parser.add_mutually_exclusive_group()
    split_group.add_argument("--split", choices=("train", "test"), help="Input dataset to evaluate")
    split_group.add_argument("--eval-source", choices=("stl", "test"))
    parser.add_argument("--test-dir", type=Path, default=ROOT.parent / "test", help="Independent final-test STL/config jobs")
    parser.add_argument("--stl-dir", type=Path, default=ROOT.parent / "train")
    parser.add_argument("--validation-dir", type=Path, default=ROOT.parent / "validation")
    parser.add_argument("--episodes", type=int, default=1, help="Episodes per shape")
    parser.add_argument("--seed", type=int)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    args.eval_source = {"train": "stl"}.get(args.split, args.split) or args.eval_source or "test"
    if args.episodes < 1:
        parser.error("episodes must be positive")
    if args.device.startswith("cuda") and not torch.cuda.is_available():
        parser.error("CUDA is unavailable; use a CUDA-enabled environment or --device cpu explicitly")
    try:
        model_path = args.model.resolve() if args.model else latest_model(args.runs_dir.resolve())
        settings, model_bytes = load_training(model_path)
        jobs = evaluation_jobs(settings, args.eval_source, args.stl_dir.resolve(), args.validation_dir.resolve(), args.test_dir.resolve())
        weights = LayerRewardWeights(**settings["reward_weights"])
    except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile) as exc:
        parser.error(str(exc))
    seed = args.seed if args.seed is not None else settings["ppo"]["seed"] + 10000
    if not 0 <= seed < 2**32 - args.episodes + 1:
        parser.error("seed and episode seeds must be in [0, 2**32)")
    output = (args.output or ROOT / "result/layer_evaluation" /
              datetime.now().strftime("%Y%m%d_%H%M%S_%f")).resolve()
    if output.exists():
        parser.error("Choose a new output directory; existing results are not overwritten")
    model = PPO.load(io.BytesIO(model_bytes), device=args.device)
    placement_model = None
    if settings.get("placement_enabled"):
        pair = json.loads(model_path.with_suffix('.pair.json').read_text(encoding='utf-8'))
        placement_path = model_path.with_name(pair['placement_file'])
        placement_bytes = placement_path.read_bytes()
        if (hashlib.sha256(model_bytes).hexdigest() != pair['layer_sha256'] or
                hashlib.sha256(placement_bytes).hexdigest() != pair['placement_sha256']):
            raise ValueError('Layer/placement model pair differs from saved hashes; retry after checkpoint save')
        placement_model = PPO.load(io.BytesIO(placement_bytes), device=args.device)

    output.mkdir(parents=True, exist_ok=False)
    (output / "model_snapshot.zip").write_bytes(model_bytes)
    if placement_model is not None:
        (output / "placement_snapshot.zip").write_bytes(placement_bytes)
        from placement import record_model_pair
        record_model_pair(output / 'model_snapshot.zip', output / 'placement_snapshot.zip')
    report = dict(version=VERSION, environment=ENVIRONMENT_SCHEMA, output=str(output),
                  evaluation_criterion=EVALUATION_CRITERION, model=str(model_path),
                  model_sha256=hashlib.sha256(model_bytes).hexdigest(),
                  model_timesteps=model.num_timesteps, training=settings,
                  actual_device=str(model.device), evaluation_source=args.eval_source,
                  split={"example": "validation_sample", "validation": "validation_set",
                         "stl": "training_set", "test": "test_set"}[args.eval_source],
                  deterministic=True, reward_weights=asdict(weights), step_unit="layer",
                  reward_formula="iou_gt_0.9_utilization_over_makespan_v1",
                  training_reward_formula=settings.get("reward_formula", "unweighted_time_v1"),
                  seeds=[seed + i for i in range(args.episodes)], jobs=[], total_jobs=len(jobs))
    if placement_model is not None:
        report.update(placement_model=str(placement_path), placement_model_sha256=hashlib.sha256(placement_bytes).hexdigest())
    write_json(output / "evaluation.json", report)
    records = []
    print(f"Model: {model_path}\nDevice: {model.device}\nEvaluation: {args.eval_source}", flush=True)
    for job_index, job in enumerate(jobs):
        job_started = time.perf_counter()
        if placement_model is not None:
            from placement import PlacedLayerEnv
            env = PlacedLayerEnv(Path(job["scenario"]), placement_policy=placement_model, reward_weights=weights)
        else:
            env = LayerPathEnv(Path(job["scenario"]), reward_weights=weights)
        try:
            if env.observation_space != model.observation_space or env.action_space != model.action_space:
                raise ValueError("Model and layer environment spaces do not match")
            job_records = [evaluate_episode(model, env, episode_seed,
                           output / f"job_{job_index:02d}" / f"episode_{i:03d}")
                           for i, episode_seed in enumerate(report["seeds"])]
        finally:
            env.close()
        # Includes STL loading/slicing, path generation, official validation,
        # deposited-STL export and writing the episode reports.
        job_wall_time_s = time.perf_counter() - job_started
        records.extend(job_records)
        report["jobs"].append(dict(job, job_wall_time_s=job_wall_time_s,
                                   summary=summarize(job_records), episodes=[
            {k: v for k, v in record.items() if k not in ("steps", "validation")} for record in job_records]))
        report.update(summary=summarize(records), completed_jobs=len(report["jobs"]))
        write_json(output / "evaluation.json", report)
        print(f"{job['id']}: {json.dumps(report['jobs'][-1]['summary'])}; "
              f"calculation_wall_time_s={job_wall_time_s:.3f}", flush=True)
    print(f"Results: {output}", flush=True)
    return report


if __name__ == "__main__":
    main()
