#!/usr/bin/env python3
"""Thin entrypoint: ``blufire leadgen run`` from the systemd timer.

All real logic lives in :mod:`blufire.agents.daily_lead_gen`.
"""

from __future__ import annotations

import sys

from blufire.cli import main

if __name__ == "__main__":
    sys.exit(main(["leadgen", "run", "--scope", "daily"]))
