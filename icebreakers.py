#!/usr/bin/env python3
"""CSV in, CSV out: add an Icebreaker column to a lead list.

    python icebreakers.py leads.csv                       # -> leads-icebreakers.csv
    python icebreakers.py leads.csv --backend mock        # offline, canned answers
    python icebreakers.py reapply leads-icebreakers.csv   # overrides only, no model calls
    python icebreakers.py drive --list                    # optional Google Drive hand-off

See README.md.
"""
import sys

from lead_icebreakers.cli import main

if __name__ == "__main__":
    sys.exit(main())
