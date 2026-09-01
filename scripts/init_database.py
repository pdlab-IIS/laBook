"""Initialize a new laBook database without overwriting an existing file."""

from __future__ import annotations

import argparse
import json
import sys

from db import DATABASE, initialize_database


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", default=DATABASE)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        initialize_database(args.database)
    except Exception as error:
        print(
            json.dumps(
                {"status": "error", "error": type(error).__name__},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1

    print(json.dumps({"status": "ok"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
