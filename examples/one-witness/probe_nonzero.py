#!/usr/bin/env python3
"""Cited as evidence #2: the total is present at all.

A corollary of test_exact under every mutation this configuration declares.
Both pass on the clean tree, both fail on each declared defect, and the
configuration cannot tell them apart.
"""
import sys
from compute import total
sys.exit(0 if total() > 0 else 1)
