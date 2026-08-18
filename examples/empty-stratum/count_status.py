#!/usr/bin/env python3
"""Print how many corpus documents are in the given status. One integer."""
import pathlib, sys
want = sys.argv[1]
corpus = pathlib.Path(__file__).parent.joinpath("corpus").glob("*.txt")
print(sum(1 for p in corpus if f"status: {want}" in p.read_text()))
