"""Layer training/evaluation contracts; run with Python's built-in unittest."""

from contextlib import redirect_stderr
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import zipfile

import numpy as np

from validator_adapter import VALIDATOR_ROOT, run_validation
from evaluate_layers import (ENVIRONMENT_SCHEMA, VERSION, discover_scenarios, evaluate_episode,
                             evaluation_jobs, input_hashes, latest_model, load_training, sha256, LayerPathEnv)
from train import (parser_for_training, snapshot_dataset_inputs, snapshot_inputs,
                          validate_args, validation_score)


def make_job(root: Path, name: str, target=b"target") -> Path:
    job = root / name
    job.mkdir(parents=True)
    (job / "target.stl").write_bytes(target)
    (job / "config.yaml").write_text("robots: []\n", encoding="utf-8")
    return job


class LayerTrainingTests(unittest.TestCase):
    def test_multiple_validation_stls_are_frozen_and_disjoint(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            train = make_job(root, "train", b"train")
            first = make_job(root, "first", b"first")
            second = make_job(root, "second", b"second")
            jobs, validation_jobs = snapshot_dataset_inputs(
                [train], [first, second], root / "snapshots")
            self.assertEqual(len(jobs), 1)
            self.assertEqual([job["id"] for job in validation_jobs], ["first", "second"])
            self.assertEqual([job["input_sha256"] for job in validation_jobs],
                             [input_hashes(first), input_hashes(second)])
            self.assertTrue(all(Path(job["scenario"]).is_dir() for job in validation_jobs))
            (second / "target.stl").write_bytes(b"changed")
            self.assertEqual(input_hashes(Path(validation_jobs[1]["scenario"])),
                             validation_jobs[1]["input_sha256"])
            with self.assertRaisesRegex(ValueError, "must not be included"):
                snapshot_dataset_inputs([train], [first, train], root / "overlap")
            with self.assertRaisesRegex(ValueError, "Duplicate validation"):
                snapshot_dataset_inputs([train], [first, first], root / "duplicate")

    def test_snapshots_only_raw_inputs_and_keeps_validation_out(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            train = make_job(root, "training", b"training_stl")
            validation = make_job(root, "sample", b"sample_stl")
            (train / "tasks.json").write_text("old predetermined tasks", encoding="utf-8")
            jobs, validation_job = snapshot_inputs([train], validation, root / "snapshots")
            self.assertEqual(len(jobs), 1)
            self.assertEqual(jobs[0]["input_sha256"], input_hashes(train))
            self.assertFalse((Path(jobs[0]["scenario"]) / "tasks.json").exists())
            self.assertEqual(validation_job["input_sha256"], input_hashes(validation))
            (train / "target.stl").write_bytes(b"changed original")
            self.assertEqual((Path(jobs[0]["scenario"]) / "target.stl").read_bytes(), b"training_stl")

    def test_validation_shape_cannot_leak_into_training(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            train = make_job(root, "training")
            validation = make_job(root, "sample")
            with self.assertRaisesRegex(ValueError, "must not be included"):
                snapshot_inputs([train], validation, root / "snapshots")
            self.assertFalse((root / "snapshots").exists())

    def test_cuda_is_default_and_never_silently_falls_back(self):
        parser = parser_for_training()
        args = parser.parse_args([])
        self.assertEqual(args.device, "cuda")
        with patch("train.torch.cuda.is_available", return_value=False), redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                validate_args(parser, args)
            cpu_args = parser.parse_args(["--device", "cpu"])
            validate_args(parser, cpu_args)

    def test_best_model_score_is_validator_pass_rate_only(self):
        records = [dict(schedule_complete=True, status="PASS", success=True,
                        episode_reward=-3, episode_length=5, iou=0.5, makespan_s=50),
                   dict(schedule_complete=True, status="FAIL", success=False,
                        episode_reward=100, episode_length=5, iou=1.0, makespan_s=1)]
        self.assertEqual(validation_score(records), 0.5)

    def test_discovery_requires_config_for_every_stl(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            job = make_job(root, "01")
            self.assertEqual(discover_scenarios(root), [job.resolve()])
            (job / "config.yaml").unlink()
            with self.assertRaisesRegex(ValueError, "Missing config"):
                discover_scenarios(root)


class LayerEvaluationTests(unittest.TestCase):
    def test_validation_source_checks_frozen_set_and_supports_older_models(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            train = make_job(root / "train", "01", b"train")
            first = make_job(root / "validation", "first", b"first")
            second = make_job(root / "validation", "second", b"second")
            jobs, validation_jobs = snapshot_dataset_inputs(
                [train], [first, second], root / "snapshots")
            settings = dict(training_jobs=jobs, validation_jobs=validation_jobs,
                            validation_job=validation_jobs[0])
            self.assertEqual(evaluation_jobs(settings, "validation", root / "train",
                                             root / "validation"), validation_jobs)
            old_settings = dict(training_jobs=jobs, validation_job=validation_jobs[0])
            external = evaluation_jobs(old_settings, "validation", root / "train",
                                       root / "validation")
            self.assertEqual([job["id"] for job in external], ["first", "second"])
            self.assertEqual(external[1]["input_sha256"], input_hashes(second))
            (second / "target.stl").write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "differ"):
                evaluation_jobs(settings, "validation", root / "train", root / "validation")
            (second / "target.stl").write_bytes(b"train")
            with self.assertRaisesRegex(ValueError, "overlaps"):
                evaluation_jobs(old_settings, "validation", root / "train", root / "validation")

    def test_latest_excludes_newer_legacy_and_unfinished_models(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, timestamp, status, schema, version in [
                ("layer_old", 10, "completed", ENVIRONMENT_SCHEMA, VERSION),
                ("layer_latest", 20, "completed", ENVIRONMENT_SCHEMA, VERSION),
                ("unfinished", 30, "started", ENVIRONMENT_SCHEMA, VERSION),
                ("legacy", 40, "completed", "stl_multi_v1", "1.0.1"),
            ]:
                run = root / name
                run.mkdir()
                model = run / "ppo_model.zip"
                model.touch()
                os.utime(model, (timestamp, timestamp))
                (run / "training.json").write_text(json.dumps(dict(status=status, environment=schema, version=version)))
            self.assertEqual(latest_model(root), (root / "layer_latest/ppo_model.zip").resolve())

    def test_explicit_checkpoint_is_frozen_and_checks_schema(self):
        with tempfile.TemporaryDirectory() as directory:
            model = Path(directory) / "checkpoint.zip"
            with zipfile.ZipFile(model, "w") as archive:
                archive.writestr("data", "saved model")
            metadata = model.with_name("training.json")
            settings = dict(status="started", environment=ENVIRONMENT_SCHEMA, version=VERSION)
            metadata.write_text(json.dumps(settings))
            returned_settings, frozen = load_training(model)
            model.write_bytes(b"new in-progress save")
            self.assertEqual(returned_settings, settings)
            with zipfile.ZipFile(io.BytesIO(frozen)) as archive:
                self.assertEqual(archive.read("data"), b"saved model")
            metadata.write_text(json.dumps(dict(settings, environment="stl_multi_v1")))
            with self.assertRaisesRegex(ValueError, "incompatible"):
                load_training(model)

    def test_evaluation_detects_snapshot_and_source_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            train = make_job(root / "stls", "01", b"train")
            sample = make_job(root, "sample", b"sample")
            jobs, validation = snapshot_inputs([train], sample, root / "snapshots")
            settings = dict(training_jobs=jobs, validation_job=validation)
            self.assertEqual(evaluation_jobs(settings, "example", root / "stls"), [validation])
            self.assertEqual(evaluation_jobs(settings, "stl", root / "stls"), jobs)
            (train / "target.stl").write_bytes(b"source changed")
            with self.assertRaisesRegex(ValueError, "differ"):
                evaluation_jobs(settings, "stl", root / "stls")
            (Path(validation["scenario"]) / "config.yaml").write_text("modified")
            with self.assertRaisesRegex(ValueError, "snapshot changed"):
                evaluation_jobs(settings, "example", root / "stls")

    def test_multidiscrete_action_and_reward_trace_saved_and_validator_controls_success(self):
        for status, expected in [("PASS", True), ("FAIL", False)]:
            with self.subTest(status=status), tempfile.TemporaryDirectory() as directory:
                env, model, result = Mock(), Mock(), Mock()
                env.done = False
                env.reset.return_value = (np.zeros(1), {})
                action = np.array([7, 2, 3, 1, 1, 2, 5])
                model.predict.return_value = (action, None)

                def complete(received):
                    np.testing.assert_array_equal(received, action)
                    env.done = True
                    return np.zeros(1), -0.1, True, False, dict(
                        schedule_complete=True, completed_layers=1, total_layers=1,
                        iou=0.5, layer_iou=0.5, makespan_s=10,
                    )

                env.step.side_effect = complete
                result.status = status
                result.shape.iou = 0.5
                result.schedule.makespan_s = 10
                result.summary_dict.return_value = {}
                output = Path(directory) / "episode"
                with patch("evaluate_layers.run_validation", return_value=result) as validator:
                    record = evaluate_episode(model, env, 42, output, progress_every=0)
                self.assertEqual(record["success"], expected)
                self.assertEqual(record["episode_length"], 1)
                self.assertEqual(record["steps"][0]["action"], action.tolist())
                self.assertEqual(record["episode_reward"], -0.1)
                self.assertTrue((output / "episode.json").is_file())
                self.assertEqual(json.loads((output / "layer_trace.json").read_text())[0]["action"], action.tolist())
                validator.assert_called_once()
                env.export.assert_called_once()

    def test_failed_layer_is_saved_without_claiming_validator_pass(self):
        env, model = Mock(), Mock()
        env.done = False
        env.reset.return_value = (np.zeros(1), {})
        model.predict.return_value = (np.zeros(7, dtype=np.int64), None)

        def fail(action):
            env.done = True
            return np.zeros(1), -2.0, True, False, dict(
                schedule_complete=False, completed_layers=0, total_layers=8,
                iou=0.0, layer_iou=0.0, makespan_s=0, failure_reason="unreachable")

        env.step.side_effect = fail
        with tempfile.TemporaryDirectory() as directory, patch("evaluate_layers.run_validation") as validator:
            record = evaluate_episode(model, env, 42, Path(directory) / "episode", progress_every=0)
        self.assertEqual(record["status"], "INFEASIBLE")
        self.assertFalse(record["success"])
        self.assertEqual(record["completed_layers"], 0)
        self.assertIsNone(record["makespan_s"])
        validator.assert_not_called()
        env.export.assert_not_called()

    def test_terminal_validation_is_reused_only_with_unchanged_saved_inputs(self):
        for mode, expected_status in [("pass", "PASS"), ("changed", "ERROR"), ("error", "ERROR")]:
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                env, model, result = Mock(), Mock(), Mock()
                previous_output = Path(directory) / "previous"
                env.evaluate_output = previous_output
                env.reset.return_value = (np.zeros(1), {})
                env.done = False
                model.predict.return_value = (np.zeros(7, dtype=np.int64), None)
                result.status = "PASS"
                result.shape.iou = 0.97
                result.schedule.makespan_s = 10
                result.summary_dict.return_value = {}

                def complete(action):
                    env.done = True
                    output = env.evaluate_output
                    job = make_job(output, "input")
                    (job / "trajectory.csv").write_text("generated trajectory")
                    env.terminal_validation_artifacts = dict(output=str(output.resolve()),
                        input_sha256={name: sha256(job / name) for name in ("config.yaml", "target.stl", "trajectory.csv")})
                    reports = output / "validation"
                    reports.mkdir()
                    (reports / ("error.json" if mode == "error" else "summary.json")).write_text("{}")
                    env.terminal_validation = None if mode == "error" else result
                    if mode == "changed":
                        (job / "trajectory.csv").write_text("changed after validation")
                    return np.zeros(1), 1.0, True, False, dict(
                        schedule_complete=True, completed_layers=1, total_layers=1, iou=0.97,
                        makespan_s=10, terminal_status="ERROR" if mode == "error" else "PASS",
                        terminal_error="TEST_ERROR: failed" if mode == "error" else None)

                env.step.side_effect = complete
                with patch("evaluate_layers.run_validation") as validator:
                    record = evaluate_episode(model, env, 42, Path(directory) / "episode", progress_every=0)
                self.assertEqual(record["status"], expected_status)
                self.assertEqual(record["success"], mode == "pass")
                self.assertEqual(env.evaluate_output, previous_output)
                if mode != "changed":
                    self.assertTrue(record["terminal_validation_reused"])
                else:
                    self.assertIn("inputs changed", record["failure_reason"])
                validator.assert_not_called()
                env.export.assert_not_called()

    def test_evaluation_output_hook_is_removed_after_exception(self):
        env, model = Mock(), Mock()
        env.done = False
        env.reset.return_value = (np.zeros(1), {})
        model.predict.side_effect = RuntimeError("prediction failed")
        self.assertNotIn("evaluate_output", vars(env))
        with tempfile.TemporaryDirectory() as directory, self.assertRaisesRegex(RuntimeError, "prediction failed"):
            evaluate_episode(model, env, 42, Path(directory) / "episode", progress_every=0)
        self.assertNotIn("evaluate_output", vars(env))

    def test_real_sample_runs_official_validator_once_and_saves_complete_reports(self):
        env = LayerPathEnv(VALIDATOR_ROOT / "examples/sample_job")
        model = Mock()
        model.predict.return_value = (np.array([0, 1, 0, 0, 0, 0, 0]), None)
        try:
            with tempfile.TemporaryDirectory() as directory:
                output = Path(directory) / "episode"
                with patch("layer_assignment_env.run_validation", wraps=run_validation) as terminal_validator, \
                     patch("evaluate_layers.run_validation", wraps=run_validation) as duplicate_validator:
                    record = evaluate_episode(model, env, 42, output, progress_every=0)
                self.assertEqual(record["status"], "PASS")
                self.assertTrue(record["terminal_validation_reused"])
                terminal_validator.assert_called_once()
                duplicate_validator.assert_not_called()
                self.assertTrue((output / "input/trajectory.csv").is_file())
                self.assertTrue((output / "validation/summary.json").is_file())
                self.assertEqual(record["artifacts"]["status"], "READY")
                import trimesh
                from export_trajectories import export_episode
                mesh = trimesh.load(output / "deposited.stl", force="mesh")
                self.assertGreater(len(mesh.faces), 0)
                self.assertGreater(mesh.volume, 0)
                with (output / "input/trajectory.csv").open("a") as handle:
                    handle.write("\n")
                with self.assertRaisesRegex(ValueError, "content has changed"):
                    export_episode(output)
        finally:
            env.close()


if __name__ == "__main__":
    unittest.main()
