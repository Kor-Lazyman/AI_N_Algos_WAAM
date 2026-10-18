"""Check the real held-out STL files before training or evaluation uses them."""
import json
import unittest

import trimesh

from evaluate_layers import ROOT, discover_scenarios, input_hashes
from run_validation_set import verify_dataset


class ValidationDatasetTests(unittest.TestCase):
    def test_manifest_meshes_and_split_are_valid(self):
        directory = ROOT / "validation_stl"
        jobs = verify_dataset(directory)
        self.assertEqual(len(jobs), 6)
        training = discover_scenarios(ROOT / "stl_files")
        train_targets = {input_hashes(path)["target.stl"] for path in training}
        validation_targets = [input_hashes(path)["target.stl"] for path in jobs]
        self.assertEqual(len(set(validation_targets)), len(jobs))
        self.assertFalse(train_targets.intersection(validation_targets))
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(len(manifest["jobs"]), len(jobs))
        for job in jobs:
            with self.subTest(job=job.name):
                mesh = trimesh.load(job / "target.stl", force="mesh", process=True)
                self.assertTrue(mesh.is_watertight)
                self.assertGreater(mesh.volume, 0)
                self.assertLess(max(abs(mesh.bounds[:, :2].flatten())), 250)


if __name__ == "__main__":
    unittest.main()
