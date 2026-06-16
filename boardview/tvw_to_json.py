#!/usr/bin/env python3
"""Wrapper to run the scripts/tvw_to_json.py from any CWD."""
import sys
from pathlib import Path

repo_root = Path(__file__).parent.resolve()
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from scripts import tvw_to_json


def main():
    tvw_to_json.main()


if __name__ == '__main__':
    main()
