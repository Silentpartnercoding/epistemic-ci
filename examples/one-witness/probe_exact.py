#!/usr/bin/env python3
"""Cited as evidence #1: the total is exactly right."""
import sys
from compute import total
sys.exit(0 if total() == 42 else 1)
