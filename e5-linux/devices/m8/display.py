#!/usr/bin/env python3
"""Compatibility entry for the shared SPRD display adaptation."""
from pathlib import Path
import runpy


def apply(kernel):
    return runpy.run_path(str(Path(__file__).resolve().parents[1] / 'common/display.py'))['apply'](kernel)
