# Three fixtures where ordinary CI is green and the gate refuses

Each fixture is a small, complete, **honest** pipeline. Ordinary verification
passes. Seven of the eight checks pass. Exactly one refuses.

```
                       ordinary verify   checks passing   refusing
empty-stratum          PASS              7 / 8            effect-reachability
pin-drift              PASS              7 / 8            pinned-input-binding
one-witness            PASS              7 / 8            evidential-independence
```

The one-failure property is deliberate and is pinned by
`tests/test_failure_class_fixtures.py`. A fixture failing four checks would
demonstrate an incomplete configuration, not the defect it is about.

## Why these three are not caught by planting defects

The standard defence is sensitivity: plant a defect, confirm verification goes
red. **All three fixtures pass that defence.** `vacuous-test` is green in every
one of them — the declared defect does make verification fail. The verifier is
working. It simply is not connected to what a reader assumes a green check
established.

### `pin-drift` — the pinned input that was never read

`run.py` declares that its result came from `pinned/threshold.txt` and records a
SHA-256 of it. It reads the workspace copy, and hashes the same copy it read, so
the digest always matches. Ordinary verification confirms the digest. It cannot
fail.

The gate corrupts the workspace copy of the pin and requires the result **not to
move**. It moves. This check has the opposite polarity to the others: everywhere
else corruption must cause failure, and here it must cause nothing.

### `one-witness` — two tests that are one piece of evidence

`test_exact` and `test_nonzero` are cited as separate evidence. Both pass on the
clean tree; every declared mutation fires both. Ordinary CI reports *two tests
passed*, which reads as two independent confirmations.

The gate reports that no declared mutation separates them. It does not claim the
tests are logically redundant — that is undecidable. It reports a fact about the
**configuration**: this mutation set cannot tell them apart. The remedy is a
mutation that separates them, or an admission that they are one witness.

### `empty-stratum` — a population that cannot move the endpoint

Eight documents, all `status: searched`. The endpoint is *"a clean verdict is
refused when coverage is incomplete."* The mechanism's only lever is incomplete
coverage, and the corpus contains none: `searched 8 · not_searched 0`.

Verification is sound and the number is honest. It was decided before any data
existed. This is the only one of the three that interrogates the **population**
rather than the verification path, and no amount of checking the checker finds
it.

## Running them

```sh
epistemic-ci run --root examples/empty-stratum --config .epistemic-ci.json
epistemic-ci run --root examples/pin-drift     --config .epistemic-ci.json
epistemic-ci run --root examples/one-witness   --config .epistemic-ci.json
```

Each exits non-zero and names one check.

## What they do not establish

That these are the only such classes, or that a real pipeline fails this way
often. They are existence proofs: **each class is real, each survives
sensitivity testing, and each is mechanically checkable.** A reader who believes
one of them is already covered by an existing method can refute that by
exhibiting a sensitivity test which catches it.
