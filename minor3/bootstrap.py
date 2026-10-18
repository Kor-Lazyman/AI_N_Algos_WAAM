"""Reuse the project's geometry/config packages; do not run full validation."""
import os
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
PROJECT=Path(os.environ.get('MINOR3_PROJECT',ROOT.parent)).resolve()
sys.path.insert(0,str(PROJECT/'minor_2'))

