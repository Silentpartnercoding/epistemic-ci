# Vacuous-green comparison

This demonstration shows a narrow failure mode: an ordinary verification
command returns success even though it never reads the declared source whose
value supposedly supports the result.

The files are intentionally small and synthetic:

- `source.txt` is the input that should matter;
- `ordinary_ci.py` is intentionally defective and checks only
  `frozen_expected.txt`;
- `.epistemic-ci.json` declares a controlled `PASS` → `FAIL` mutation in the
  source;
- Epistemic CI applies that mutation in a copied workspace and observes that
  the ordinary command still exits successfully.

## Run the comparison

First run the ordinary check:

```bash
python3 examples/vacuous-green/ordinary_ci.py
```

It exits `0` and prints `ORDINARY CI: PASS`.

Then run Epistemic CI:

```bash
epistemic-ci run \
  --root examples/vacuous-green \
  --config .epistemic-ci.json \
  --output epistemic-ci-result.json
```

That command is expected to exit `1`. Its `vacuous-test` result names
`change-source-verdict` as a survivor: changing the declared source did not
make the ordinary verifier fail. The other three v0 checks pass, isolating the
demonstrated defect.

For a single command that asserts the expected contrast without leaving a
failing shell status:

```bash
python3 -m unittest tests.test_vacuous_green_demo -v
```

This is a demonstration fixture, not evidence about an external repository or
a certification of scientific correctness.
