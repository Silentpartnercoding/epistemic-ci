# Contributing

Small, reviewable contributions are welcome.

1. Open an issue or focused pull request describing the failure mode.
2. Add a regression test that fails before the implementation change.
3. Keep claims no broader than the executable evidence.
4. Run `python3 -m unittest discover -s tests -v` and the demo.

V0 is deliberately limited to the four checks documented in the README.
Proposals for additional checks should identify the exact false-positive or
false-negative behavior, its expected failure condition, and a minimal fixture.

Never include credentials, private datasets, proprietary strategy documents, or
unredacted production evidence in an issue, fixture, or pull request.
