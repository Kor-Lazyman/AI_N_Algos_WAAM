"""Reuse the pinned minor_2 planner and official Validator from the parent project."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent
# SCHEDULER_PROJECT is useful for isolated tests before installation.
import os
PROJECT = Path(os.environ.get('SCHEDULER_PROJECT', PROJECT)).resolve()
MINOR = PROJECT / 'minor_2'
if not (MINOR / 'layer_assignment_env.py').is_file():
    raise RuntimeError(f'Place scheduler next to minor_2: {PROJECT}')
sys.path.insert(0, str(MINOR))

