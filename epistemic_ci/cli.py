from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .core import ConfigurationError, RESULT_SCHEMA, load_config, run_all


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="epistemic-ci",
        description="Test whether a declared research-verification path is non-vacuous.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    run = subparsers.add_parser("run", help="run the four v0 meta-validation checks")
    run.add_argument("--config", default=".epistemic-ci.json")
    run.add_argument("--root", default=".")
    run.add_argument("--output", default="epistemic-ci-result.json")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.root).resolve()
    output = Path(args.output)
    if not output.is_absolute():
        output = root / output
    try:
        config_path = Path(args.config)
        if not config_path.is_absolute():
            config_path = root / config_path
        config = load_config(config_path.resolve())
        result = run_all(root, config)
    except (ConfigurationError, OSError) as exc:
        result = {
            "schema": RESULT_SCHEMA,
            "status": "fail",
            "checks": [
                {
                    "name": "configuration",
                    "status": "fail",
                    "reason": str(exc),
                    "details": None,
                }
            ],
        }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
