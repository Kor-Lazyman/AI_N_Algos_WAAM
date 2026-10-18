"""Legacy filename: time each independent test STL and report official Validator makespan and status.

python -m tools.benchmark [--model path/to/ppo_model.zip] [--device cuda]
"""
from __future__ import annotations
import argparse
import csv
import json
from pathlib import Path

from evaluate_layers import ROOT, discover_scenarios, input_hashes, main as evaluate


def verify_dataset(directory: Path) -> list[Path]:
    jobs = discover_scenarios(directory.resolve())
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    recorded = {job["id"]: job for job in manifest["jobs"]}
    if len(jobs) != len(recorded) or {job.name for job in jobs} != set(recorded):
        raise ValueError("Validation dataset and manifest job list differ")
    for job in jobs:
        actual = input_hashes(job)
        expected = recorded[job.name]
        if actual != {"config.yaml": expected["config_sha256"],
                      "target.stl": expected["target_sha256"]}:
            raise ValueError(f"Validation dataset changed: {job}")
    return jobs


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--test-dir", type=Path, default=ROOT / "test")
    parser.add_argument("--model", type=Path)
    parser.add_argument("--runs-dir", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--episodes", type=int, default=1)
    parser.add_argument("--seed", type=int)
    args = parser.parse_args(argv)
    # test 폴더는 사용자 입력이며 manifest가 없어도 평가할 수 있다.
    jobs = discover_scenarios(args.test_dir)
    print(f"Verified {len(jobs)} held-out STL jobs", flush=True)
    forwarded = ["--split", "test", "--test-dir", str(args.test_dir),
                 "--device", args.device, "--episodes", str(args.episodes)]
    for flag, value in (("--model", args.model), ("--runs-dir", args.runs_dir),
                        ("--output", args.output), ("--seed", args.seed)):
        if value is not None:
            forwarded.extend((flag, str(value)))
    report = evaluate(forwarded)
    output = Path(report["output"])
    rows = []
    for job in report["jobs"]:
        statuses = {episode["status"] for episode in job["episodes"]}
        status = next(iter(statuses)) if len(statuses) == 1 else "MIXED"
        rows.append(dict(input=job["id"], calculation_time_s=round(job["job_wall_time_s"], 3),
                         makespan_s=job["summary"]["makespan_completed_mean_s"],
                         validator_status=status, validator_passed=job["summary"]["pass_rate"] == 1.0,
                         episodes=len(job["episodes"])))
    with (output / "per_shape_results.csv").open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print("Input              Calculation (s)  Makespan (s)  Validator", flush=True)
    for row in rows:
        makespan = (f"{row['makespan_s']:.3f}" if row["makespan_s"] is not None else "N/A")
        print(f"{row['input']:<18} {row['calculation_time_s']:>15.3f}  "
              f"{makespan:>12}  {row['validator_status']}", flush=True)
    print(f"CSV: {output / 'per_shape_results.csv'}", flush=True)
    print(f"Test set: {report['summary']['pass_rate']:.1%} PASS "
          f"({report['summary']['episodes']} episodes)", flush=True)
    return report


if __name__ == "__main__":
    main()
