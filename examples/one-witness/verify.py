#!/usr/bin/env python3
"""Ordinary verification: run both tests. Green means 'two tests passed'."""
import subprocess, sys, pathlib
here = pathlib.Path(__file__).parent
failed = [t for t in ("probe_exact.py", "probe_nonzero.py")
          if subprocess.run([sys.executable, t], cwd=here).returncode != 0]
if failed:
    print("FAIL:", ", ".join(failed)); sys.exit(1)
print("PASS: 2 tests passed")
