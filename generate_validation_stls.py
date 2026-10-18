"""Create reproducible, held-out STL jobs for layer-path validation.

The first job copies the official sample; five new jobs vary footprint topology.
Run once: python generate_validation_stls.py --output validation_stl
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil

from shapely.geometry import Point, Polygon, box
import trimesh

from validator_adapter import VALIDATOR_ROOT


ROOT = Path(__file__).resolve().parent


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def shapes():
    return [
        ("01_rectangle", "100 × 60 mm rectangle, two layers", box(-50, -30, 50, 30), 4.0),
        ("02_triangle", "triangular footprint, one layer",
         Polygon([(-50, -35), (50, -35), (0, 45)]), 2.0),
        ("03_l_shape", "L-shaped footprint, two layers",
         Polygon([(-55, -45), (55, -45), (55, -15), (-20, -15), (-20, 50), (-55, 50)]), 4.0),
        ("04_cross", "cross-shaped footprint, one layer",
         box(-52, -16, 52, 16).union(box(-16, -52, 16, 52)), 2.0),
        ("05_ring", "annular footprint with a hole, one layer",
         Point(0, 0).buffer(52, resolution=48).difference(Point(0, 0).buffer(19, resolution=48)), 2.0),
    ]


def generate(output: Path):
    if output.exists():
        raise FileExistsError(f"Choose a new output directory: {output}")
    output.mkdir(parents=True)
    sample = VALIDATOR_ROOT / "examples/sample_job"
    jobs = []
    for name, description, polygon, height in [
        ("00_sample", "official sample reference", None, None), *shapes()
    ]:
        job = output / name
        job.mkdir()
        shutil.copy2(sample / "config.yaml", job / "config.yaml")
        if polygon is None:
            shutil.copy2(sample / "target.stl", job / "target.stl")
        else:
            if not polygon.is_valid or polygon.is_empty:
                raise ValueError(f"Invalid polygon: {name}")
            mesh = trimesh.creation.extrude_polygon(polygon, height, engine="earcut")
            if not mesh.is_watertight or mesh.volume <= 0:
                raise ValueError(f"Non-printable STL: {name}")
            mesh.export(job / "target.stl")
        # STL duplicates vertices per triangle; merge them when checking the
        # watertight mesh represented by those triangles.
        mesh = trimesh.load(job / "target.stl", force="mesh", process=True)
        jobs.append(dict(id=name, description=description, target_sha256=sha256(job / "target.stl"),
                         config_sha256=sha256(job / "config.yaml"),
                         bounds_mm=mesh.bounds.tolist(), watertight=bool(mesh.is_watertight),
                         triangles=len(mesh.faces)))
    manifest = dict(dataset="held_out_validation_stl_v1", jobs=jobs)
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "validation_stl")
    args = parser.parse_args()
    manifest = generate(args.output)
    print(f"Created {len(manifest['jobs'])} validation STL jobs under {args.output}")


if __name__ == "__main__":
    main()
