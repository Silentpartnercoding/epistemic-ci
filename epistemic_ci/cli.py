from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .core import ConfigurationError, RESULT_SCHEMA, load_config, run_all
from .onboarding import OnboardingError, build_onboarding_report


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
    init = subparsers.add_parser(
        "init",
        help="discover a repository and create an agent-readable onboarding report",
    )
    init.add_argument("--root", default=".")
    init.add_argument("--output", default="epistemic-ci-onboarding.json")
    init.add_argument("--answers")
    init.add_argument("--config")
    init.add_argument("--force", action="store_true")
    return parser


def _resolve(root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def _run(args: argparse.Namespace, root: Path) -> int:
    output = _resolve(root, args.output)
    try:
        config_path = _resolve(root, args.config)
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


def _init(args: argparse.Namespace, root: Path) -> int:
    output = _resolve(root, args.output)
    if output.exists() and not args.force:
        print(f"refusing to replace existing onboarding report: {output}", file=sys.stderr)
        return 2
    if args.config and not args.answers:
        print(
            "--config requires --answers so configuration can be checked "
            "against human confirmation",
            file=sys.stderr,
        )
        return 2
    try:
        answers = _resolve(root, args.answers).resolve() if args.answers else None
        config = _resolve(root, args.config).resolve() if args.config else None
        report = build_onboarding_report(root, answers, config)
    except (OnboardingError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.root).resolve()
    if args.command == "init":
        return _init(args, root)
    return _run(args, root)


if __name__ == "__main__":
    sys.exit(main())
