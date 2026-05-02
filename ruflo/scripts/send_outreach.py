#!/usr/bin/env python3
"""Thin entrypoint: enrichment + draft path for HubSpot leads.

All real logic lives in :mod:`blufire.agents.email_outreach`.
"""

from __future__ import annotations

import sys

from blufire.cli import main

if __name__ == "__main__":
    sys.exit(
        main(
            [
                "outreach",
                "run",
                "--campaign",
                "Daily HubSpot lead drafting (review-and-send)",
                "--dry-run",
            ]
        )
    )
