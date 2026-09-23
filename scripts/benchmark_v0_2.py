#!/usr/bin/env python3
"""Compatibility entry point; implementation: heat_index.pipeline.benchmark_canonical."""
import sys
from pathlib import Path

if str(Path(__file__).resolve().parents[1]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from heat_index.compat import expose
expose(__name__, globals(), "heat_index.pipeline.benchmark_canonical")
