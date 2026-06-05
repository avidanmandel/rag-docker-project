#!/usr/bin/env python3
"""Isolated soak harness constants (no production runtime impact)."""

from __future__ import annotations

import time

BASELINE_SET_ID = f"candidate-soak-{int(time.time())}"
RUNTIME = "/tmp/scoutmatch-soak-runtime"
