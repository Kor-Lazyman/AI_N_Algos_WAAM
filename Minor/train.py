"""Train PPO with one complete layer-path generation per step (version 1.0.2-minor)."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime
import json
import math
from pathlib import Path
import shutil
import time

import torch
from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import BaseCallback
from stable_baselines3.common.logger import configure
from stable_baselines3.common.monitor import Monitor

from evaluate_layers import (EVALUATION_CRITERION, INPUT_NAMES, discover_scenarios,
                             evaluate_episode, input_hashes, json_value, space_schema, summarize, write_json)
from layer_assignment_env import (ENVIRONMENT_SCHEMA, VERSION, LayerPathEnv,
                                  LayerRewardWeights, MultiLayerEnv)

from placement import PlacementEnv, PlacedLayerEnv, PlacementProgressCallback, PLACEMENT_SCHEMA, save_model_pair

ROOT = Path(__file__).resolve().parent


class LayerProgressCallback(BaseCallback):
    """Persist each sampled action/reward even before an optimizer update ends."""

    def __init__(self, output: Path, started: float, progress_every=8):
        super().__init__()
        self.output, self.started, self.progress_every = output, started, progress_every
        self._last_step_time = time.perf_counter()

    def _on_rollout_start(self):
        self._last_step_time = time.perf_counter()

    def _on_step(self) -> bool:
        now = time.perf_counter()
        self.logger.record_mean("layer/step_wall_time_s", now - self._last_step_time)
        self._last_step_time = now
        for index, info in enumerate(self.locals["infos"]):
            record = dict(info, step=self.num_timesteps,
                          action=np_action(self.locals["actions"][index]),
                          reward=float(self.locals["rewards"][index]),
                          wall_time_s=time.perf_counter() - self.started)
            self.logger.record_mean("layer/reward", record["reward"])
            for key in ("layer_iou", "layer_duration_s", "mean_robot_utilization",
                        "idle_factor", "weighted_layer_duration_s", "reward_iou", "reward_time",
                        "reward_invalid", "reward_terminal", "reassigned_segments", "serial_fallback", "mean_deposition_utilization", "total_wait_s", "deposition_2plus_s", "deposition_3_s", "scheduler_reduction_s"):
                if key in info and info[key] is not None:
                    self.logger.record_mean(f"layer/{key}", float(info[key]))
            self.logger.record_mean("layer/rejected", float(bool(info.get("failure_reason"))))
            if self.locals["dones"][index]:
                self.logger.record_mean("episode/completion_rate", float(info["schedule_complete"]))
                self.logger.record_mean("episode/pass_rate", float(info.get("terminal_status") == "PASS"))
            with self.output.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(record, ensure_ascii=False, default=json_value) + "\n")
            if self.num_timesteps % self.progress_every == 0:
                print(f"Layer step {self.num_timesteps}: {info.get('scenario_id', '')} "
                      f"{info['completed_layers']}/{info['total_layers']}, "
                      f"reward={record['reward']:.6f}, elapsed={record['wall_time_s']:.1f}s", flush=True)
        return True


def np_action(action):
    return action.tolist() if hasattr(action, "tolist") else action


def snapshot_dataset_inputs(scenarios: list[Path], validation_scenarios: list[Path],
                            destination: Path) -> tuple[list[dict], list[dict]]:
    """Freeze disjoint training and validation STL/config jobs before learning."""
    if not validation_scenarios:
        raise ValueError("The validation dataset is empty")
    validation_hashes = [input_hashes(path) for path in validation_scenarios]
    hashes = [input_hashes(scenario) for scenario in scenarios]
    if not scenarios:
        raise ValueError("Training dataset is empty")
    training_targets = {digest["target.stl"] for digest in hashes}
    validation_targets = [digest["target.stl"] for digest in validation_hashes]
    if training_targets.intersection(validation_targets):
        raise ValueError("The validation sample must not be included in training")
    if len(set(validation_targets)) != len(validation_targets):
        raise ValueError("Duplicate validation STL targets")

    def copy_job(source, directory, digest):
        directory.mkdir(parents=True, exist_ok=False)
        for name in INPUT_NAMES:
            shutil.copyfile(source / name, directory / name)
        # Detect source changes during copying before using inconsistent inputs.
        if input_hashes(directory) != digest:
            raise ValueError(f"Input changed while snapshotting: {source}")
        return dict(id=source.name, source=str(source.resolve()), scenario=str(directory.resolve()),
                    input_sha256=digest)

    jobs = [copy_job(source, destination / "training" / f"{index:02d}_{source.name}", digest)
            for index, (source, digest) in enumerate(zip(scenarios, hashes))]
    validation_jobs = [copy_job(source, destination / "validation" /
                       (source.name if len(validation_scenarios) == 1 else f"{index:02d}_{source.name}"), digest)
                       for index, (source, digest) in enumerate(zip(validation_scenarios, validation_hashes))]
    return jobs, validation_jobs


def snapshot_inputs(scenarios: list[Path], validation: Path, destination: Path) -> tuple[list[dict], dict]:
    """Backward-compatible single-sample snapshot helper."""
    jobs, validation_jobs = snapshot_dataset_inputs(scenarios, [validation], destination)
    return jobs, validation_jobs[0]


def validation_score(records: list[dict]) -> float:
    return summarize(records)["pass_rate"]


def validation_key(records):
    """PASS rate first, then lower shape-normalized makespan, then D overlap."""
    ratios, overlaps = [], []
    for record in records:
        steps = record.get("steps", [])
        reference = sum(step.get("time_reference_s", 0.0) for step in steps)
        ratios.append(record["makespan_s"]/max(reference, 1e-9) if record["success"] else 100.0)
        duration = record["makespan_s"] or 1.0
        overlaps.append(sum(step.get("deposition_2plus_s", 0.0) for step in steps)/duration if record["success"] else 0.0)
    return validation_score(records), -sum(ratios)/len(ratios), sum(overlaps)/len(overlaps)


def parser_for_training():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stl-dir", type=Path, default=ROOT.parent / "train")
    parser.add_argument("--validation-dir", type=Path, default=ROOT.parent / "validation",
                        help="Held-out STL/config jobs used for periodic validation")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--init-model", type=Path, help="Warm-start policy weights from compatible original or Minor PPO; reset optimizer")
    parser.add_argument("--placement", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--placement-steps", type=int, default=2, help="Full-STL placement episodes per alternating update; >=2")
    parser.add_argument("--placement-every", type=int, default=1, help="Layer PPO updates between placement updates")
    parser.add_argument("--init-placement-model", type=Path)
    parser.add_argument("--timesteps", type=int, default=1024, help="Layer-generation steps; rounds up to a rollout")
    parser.add_argument("--updates", type=int, help="Exact rollout/update count; overrides timesteps")
    parser.add_argument("--early-stopping", action=argparse.BooleanOptionalAction, default=True,
                        help="Allow KL-based optimizer early stopping in both PPO networks")
    parser.add_argument("--initial-validation", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--n-steps", type=int, default=64)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--eval-every", type=int, default=4, help="PPO updates between validation-set evaluations")
    parser.add_argument("--eval-episodes", type=int, default=1, help="Episodes per validation shape")
    parser.add_argument("--gamma", type=float, default=0.99)
    parser.add_argument("--gae-lambda", type=float, default=0.95)
    parser.add_argument("--learning-rate", type=float, default=3e-4)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--device", default="cuda", help="PPO device (default: cuda); geometry/Validator use CPU")
    parser.add_argument("--tensorboard", action=argparse.BooleanOptionalAction, default=True,
                        help="Write TensorBoard events (enabled by default)")
    parser.add_argument("--tensorboard-log", type=Path, default=ROOT / "result/tensorboard",
                        help="TensorBoard root; each training run gets a separate directory")
    parser.add_argument("--export-stl", action=argparse.BooleanOptionalAction, default=False,
                        help="After final validation-set evaluation, evaluate all training shapes and export CSV/STL")
    return parser


def validate_args(parser, args):
    if args.updates is not None:
        if args.updates < 1:
            parser.error("updates must be positive")
        args.timesteps = args.updates * args.n_steps
    if args.placement_steps < 2 or args.placement_every < 1:
        parser.error("placement-steps >=2 and placement-every >=1 are required")
    if min(args.timesteps, args.eval_every, args.eval_episodes) < 1:
        parser.error("timesteps, eval-every and eval-episodes must be positive")
    if not 2 <= args.batch_size <= args.n_steps or args.n_steps % args.batch_size:
        parser.error("Require n-steps >= batch-size >= 2 and batch-size must divide n-steps")
    if not 0 <= args.gamma <= 1 or not 0 <= args.gae_lambda <= 1:
        parser.error("gamma and gae-lambda must be in [0, 1]")
    if not math.isfinite(args.learning_rate) or args.learning_rate <= 0:
        parser.error("learning-rate must be finite and positive")
    if not 0 <= args.seed < 2**32 - 10000 - args.eval_episodes + 1:
        parser.error("training and validation seeds must be in [0, 2**32)")
    if args.device.startswith("cuda") and not torch.cuda.is_available():
        parser.error("CUDA is unavailable; use a CUDA-enabled environment or --device cpu explicitly")


def main(argv=None):
    parser = parser_for_training()
    args = parser.parse_args(argv)
    validate_args(parser, args)
    if args.tensorboard:
        try:
            from torch.utils.tensorboard import SummaryWriter  # noqa: F401
        except ImportError:
            parser.error("TensorBoard is missing. Run: python -m pip install tensorboard; or use --no-tensorboard")
    try:
        scenarios = discover_scenarios(args.stl_dir.resolve())
        validation_scenarios = discover_scenarios(args.validation_dir.resolve())
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    output = (args.output or ROOT / "result/training" /
              ("layers_minor_" + datetime.now().strftime("%Y%m%d_%H%M%S_%f"))).resolve()
    if output.exists():
        parser.error("Choose a new output directory; existing results are not overwritten")
    output.mkdir(parents=True, exist_ok=False)
    tensorboard_dir = (args.tensorboard_log.resolve() /
                       (output.name + "_" + datetime.now().strftime("%Y%m%d_%H%M%S_%f"))) if args.tensorboard else None
    started = time.perf_counter()
    weights = LayerRewardWeights()
    settings = dict(
        version=VERSION, environment=ENVIRONMENT_SCHEMA, step_unit="layer", status="started",
        started_at=datetime.now().astimezone().isoformat(),
        evaluation_criterion=EVALUATION_CRITERION, validation_score_metric="pass_rate_then_normalized_makespan_then_deposition_overlap",
        evaluation_split="validation_set", requested_timesteps=args.timesteps,
        requested_updates=math.ceil(args.timesteps / args.n_steps),
        early_stopping=args.early_stopping, initial_validation=args.initial_validation,
        reward_weights=asdict(weights), reward_formula="iou_gt_0.9_utilization_over_makespan_v1",
        placement_enabled=args.placement, placement_schema=PLACEMENT_SCHEMA,
        placement_steps_per_update=args.placement_steps, placement_every=args.placement_every,
        placement_reward="mean_of_layer_rewards_from_this_stl_only",
        utilization_definition="mean_deposition_time_divided_by_layer_makespan",
        policy="MlpPolicy",
        ppo=dict(gamma=args.gamma, gae_lambda=args.gae_lambda, learning_rate=args.learning_rate,
                 n_steps=args.n_steps, batch_size=args.batch_size, seed=args.seed, device=args.device, target_kl=0.02 if args.early_stopping else None),
        eval_seeds=[args.seed + 10000 + i for i in range(args.eval_episodes)],
        eval_every_updates=args.eval_every, geometry_device="cpu",
        paths_generated_online=True, training_trace="training_layer_trace.jsonl",
        tensorboard_enabled=args.tensorboard,
        tensorboard_log=str(tensorboard_dir) if tensorboard_dir else None,
    )
    metadata = output / "training.json"

    def save_settings():
        settings["wall_time_s"] = time.perf_counter() - started
        write_json(metadata, settings)

    save_settings()
    training = validation = monitored = model = training_logger = None
    placement_env = placement_model = placement_logger = None
    try:
        jobs, validation_jobs = snapshot_dataset_inputs(scenarios, validation_scenarios, output / "inputs")
        settings.update(training_jobs=jobs, validation_jobs=validation_jobs,
                        validation_job=validation_jobs[0],
                        validation_dir=str(args.validation_dir.resolve()))
        save_settings()
        print(f"Training {len(jobs)} STL jobs; validation: {len(validation_jobs)} held-out jobs\n"
              f"Version: {VERSION}; one step = one layer; requested device: {args.device}", flush=True)
        if args.placement:
            placement_env = PlacementEnv([Path(job["scenario"]) for job in jobs], reward_weights=weights)
            placement_model = PPO("MlpPolicy", placement_env, device=args.device, seed=args.seed+777,
                                  n_steps=args.placement_steps, batch_size=args.placement_steps,
                                  n_epochs=4, gamma=1.0, learning_rate=args.learning_rate,
                                  target_kl=0.02 if args.early_stopping else None, policy_kwargs=dict(log_std_init=-2.0), verbose=1)
            if args.init_placement_model:
                source = PPO.load(args.init_placement_model, device=args.device)
                if source.observation_space != placement_model.observation_space or source.action_space != placement_model.action_space:
                    raise ValueError("Incompatible placement policy spaces")
                placement_model.policy.load_state_dict(source.policy.state_dict(), strict=True)
            placement_logger = configure(str((tensorboard_dir or output / "logs") / "placement"),
                                         ["stdout", "tensorboard"] if args.tensorboard else ["stdout"])
            placement_model.set_logger(placement_logger)
            placement_model.save(output / "placement_initial")
            settings["placement_model"] = "placement_model.zip"
            settings["placement_actual_device"] = str(placement_model.device)
            settings["placement_policy_parameter_devices"] = sorted({str(p.device) for p in placement_model.policy.parameters()})
            settings["placement_ppo"] = dict(n_steps=args.placement_steps, batch_size=args.placement_steps,
                n_epochs=4, gamma=1.0, learning_rate=args.learning_rate, seed=args.seed+777,
                target_kl=0.02 if args.early_stopping else None, log_std_init=-2.0, device=args.device)
            settings["placement_spaces"] = dict(action_shape=list(placement_env.action_space.shape),
                                                 observation_shape=list(placement_env.observation_space.shape))
        training = MultiLayerEnv([Path(job["scenario"]) for job in jobs], reward_weights=weights,
                                 placement_policy=placement_model)
        validation = [(PlacedLayerEnv(Path(job["scenario"]), placement_model, reward_weights=weights)
                       if placement_model is not None else LayerPathEnv(Path(job["scenario"]), reward_weights=weights))
                      for job in validation_jobs]
        if any(training.observation_space != env.observation_space or
               training.action_space != env.action_space for env in validation):
            raise ValueError("Training and validation layer environment spaces do not match")
        monitored = Monitor(training, filename=str(output / "monitor.csv"),
                            info_keywords=("schedule_complete", "iou"))
        model = PPO("MlpPolicy", monitored, **settings["ppo"], verbose=1)
        if args.init_model:
            import hashlib
            source = PPO.load(args.init_model, device=args.device)
            if source.action_space != model.action_space or source.observation_space != model.observation_space:
                raise ValueError("Warm-start requires identical original/Minor action and observation spaces")
            model.policy.load_state_dict(source.policy.state_dict(), strict=True)
            settings["warm_start"] = dict(model=str(args.init_model.resolve()),
                sha256=hashlib.sha256(args.init_model.read_bytes()).hexdigest(),
                source_timesteps=source.num_timesteps, optimizer="reset")
            del source
            save_settings()
        if placement_env is not None:
            placement_env.layer_policy = model
        # Configure once: repeated learn() calls must share the same event stream.
        training_logger = configure(str(tensorboard_dir or output / "logs"),
                                    ["stdout", "tensorboard"] if args.tensorboard else ["stdout"])
        model.set_logger(training_logger)
        if tensorboard_dir:
            print(f"TensorBoard events: {tensorboard_dir}", flush=True)
        parameter_devices = sorted({str(parameter.device) for parameter in model.policy.parameters()})
        if args.device.startswith("cuda") and (model.device.type != "cuda" or
                any(not device.startswith("cuda") for device in parameter_devices)):
            raise RuntimeError("CUDA was requested but PPO parameters were not allocated on CUDA")
        settings.update(actual_device=str(model.device), policy_parameter_devices=parameter_devices,
                        spaces=space_schema(training))
        if model.device.type == "cuda":
            settings["gpu_name"] = torch.cuda.get_device_name(model.device)
        save_settings()
        updates = math.ceil(args.timesteps / args.n_steps)
        best_score, best_key, history = -math.inf, (-math.inf, -math.inf, -math.inf), []
        callback = LayerProgressCallback(output / "training_layer_trace.jsonl", started)
        for update in range(0 if args.initial_validation else 1, updates + 1):
            # Step zero evaluates the unchanged model pair before any learning.
            if update > 0:
                rollout_started = time.perf_counter()
                model.learn(total_timesteps=args.n_steps, reset_num_timesteps=False, callback=callback)
                rollout_seconds = time.perf_counter() - rollout_started
                if placement_model is not None and update % args.placement_every == 0:
                    placement_model.learn(total_timesteps=args.placement_steps, reset_num_timesteps=False,
                        callback=PlacementProgressCallback(output / "placement_trace.jsonl"))
                    placement_model.logger.dump(step=placement_model.num_timesteps)
                    settings["placement_actual_timesteps"] = placement_model.num_timesteps
                optimizer_devices = {}
                for state in model.policy.optimizer.state.values():
                    for name, value in state.items():
                        if torch.is_tensor(value):
                            optimizer_devices.setdefault(name, set()).add(str(value.device))
                settings.update(completed_updates=update, actual_timesteps=model.num_timesteps,
                                training_episode_counts=training.episode_counts,
                                training_step_counts=training.step_counts,
                                optimizer_state_devices={name: sorted(devices) for name, devices in optimizer_devices.items()},
                                last_update_wall_time_s=rollout_seconds,
                                last_update_layers_per_s=args.n_steps / max(rollout_seconds, 1e-9))
                model.logger.record("performance/update_wall_time_s", rollout_seconds)
                model.logger.record("performance/layers_per_s", settings["last_update_layers_per_s"])
                # SB3 logs rollout data before optimization. Flush optimizer metrics
                # now as well, including the last update of a short training run.
                model.logger.dump(step=model.num_timesteps)
                # Always preserve the latest complete optimizer update.
                save_model_pair(model, placement_model, output / "checkpoint", output / "placement_checkpoint")
                save_settings()
                print(f"Update {update}/{updates}: {model.num_timesteps} layer steps, "
                      f"{rollout_seconds:.1f}s/update, {settings['last_update_layers_per_s']:.3f} layers/s", flush=True)
            if update % args.eval_every and update != updates:
                continue
            evaluation_dir = output / "validation" / f"step_{model.num_timesteps:08d}"
            evaluation_dir.mkdir(parents=True, exist_ok=False)
            save_model_pair(model, placement_model, evaluation_dir / "model_snapshot", evaluation_dir / "placement_snapshot")
            records = []
            for job_index, env in enumerate(validation):
                for episode_index, seed in enumerate(settings["eval_seeds"]):
                    records.append(evaluate_episode(model, env, seed,
                        evaluation_dir / f"job_{job_index:02d}" / f"episode_{episode_index:03d}"))
            selection = validation_key(records)
            summary = dict(update=update, step=model.num_timesteps, **summarize(records), score=selection[0],
                           normalized_makespan=-selection[1], deposition_overlap_ratio=selection[2], selection_key=list(selection))
            for key, value in summary.items():
                if key not in ("step", "update") and isinstance(value, (int, float)) and math.isfinite(value):
                    model.logger.record(f"validation/{key}", value)
            model.logger.dump(step=model.num_timesteps)
            history.append(summary)
            write_json(evaluation_dir / "evaluation.json", dict(
                version=VERSION, environment=ENVIRONMENT_SCHEMA, model_timesteps=model.num_timesteps,
                evaluation_criterion=EVALUATION_CRITERION, split="validation_set",
                validation_jobs=validation_jobs, seeds=settings["eval_seeds"], summary=summary,
                episodes=[{k: v for k, v in record.items() if k not in ("steps", "validation")} for record in records]))
            write_json(output / "validation_history.json", history)
            if selection > best_key:
                best_key = selection
                best_score = summary["score"]
                save_model_pair(model, placement_model, output / "best_model", output / "best_placement_model")
                settings.update(best_validation_score=best_score, best_selection_key=list(selection), best_step=model.num_timesteps,
                                best_model="best_model.zip")
            save_settings()
            print(f"Validation set ({len(validation_jobs)} jobs): PASS rate={summary['pass_rate']:.3f}, "
                  f"IoU={summary['iou_mean']:.6f}, reward={summary['ep_rew_mean']:.6f}", flush=True)
        save_model_pair(model, placement_model, output / "ppo_model", output / "placement_model")
        settings.update(status="exporting" if args.export_stl else "completed", model="ppo_model.zip")
        save_settings()
        if args.export_stl:
            from evaluate_layers import main as evaluate_all_shapes
            final_output = output / "final_stl_evaluation"
            report = evaluate_all_shapes([
                "--model", str(output / "ppo_model.zip"), "--eval-source", "stl",
                "--stl-dir", str(args.stl_dir.resolve()), "--device", args.device,
                "--output", str(final_output)])
            settings["final_stl_evaluation"] = str(final_output)
            settings["final_stl_summary"] = report["summary"]
            settings["final_stl_exports_ready"] = all(
                episode.get("artifacts", {}).get("status") == "READY"
                for job in report["jobs"] for episode in job["episodes"])
            if not settings["final_stl_exports_ready"]:
                save_settings()
                raise RuntimeError("Final shape evaluation/export incomplete; see final_stl_evaluation reports")
        settings.update(status="completed", completed_at=datetime.now().astimezone().isoformat())
        save_settings()
        print(f"Training completed: {output / 'ppo_model.zip'}", flush=True)
    except KeyboardInterrupt:
        if model is not None:
            save_model_pair(model, placement_model, output / "checkpoint", output / "placement_checkpoint")
            settings["actual_timesteps"] = model.num_timesteps
        settings["status"] = "interrupted"
        save_settings()
        print(f"Interrupted; checkpoint and settings: {output}", flush=True)
        raise
    except Exception as exc:
        settings.update(status="failed", error=f"{type(exc).__name__}: {exc}")
        save_settings()
        raise
    finally:
        if placement_logger is not None:
            placement_logger.close()
        if placement_env is not None:
            placement_env.close()
        if training_logger is not None:
            training_logger.close()
        if monitored is not None:
            monitored.close()
        elif training is not None:
            training.close()
        if validation is not None:
            for env in validation:
                env.close()


def run(argv=None):
    """공통 실행 진입점: 학습(내부 validation 포함) 또는 최종 test를 선택한다."""
    import sys
    arguments = list(sys.argv[1:] if argv is None else argv)
    selector = argparse.ArgumentParser(add_help=False)
    selector.add_argument("--mode", choices=("train", "test"), default="train")
    mode, remaining = selector.parse_known_args(arguments)
    if "--help" in arguments or "-h" in arguments:
        print("공통 옵션: --mode {train,test} (기본값: train)")
    if mode.mode == "train":
        # 학습 중에는 validation 세트로 best 모델을 선택하며 test는 읽지 않는다.
        return main(remaining)
    # test는 저장 모델을 독립 입력으로 평가한다. validation은 학습 내부에서만 사용한다.
    if any(arg.split("=", 1)[0] in ("--split", "--eval-source") for arg in remaining):
        selector.error("Use --mode to select the dataset; do not combine it with --split/--eval-source")
    from evaluate_layers import main as evaluate
    return evaluate(["--split", mode.mode, *remaining])


if __name__ == "__main__":
    run()
