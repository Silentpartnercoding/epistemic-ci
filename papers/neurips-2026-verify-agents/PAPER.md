# Who Verifies the Verifier? Executable Failure Tests for Agent Evaluation Harnesses

*Anonymous submission — NeurIPS 2026 Workshop, "Who Verifies the Agents?" (demo track, ≤4 pages, non-archival, double blind).*

## Abstract

Agent evaluation harnesses are treated as trusted infrastructure: when their CI
is green, downstream readers treat the evaluation as meaningful. We demonstrate
three failure classes in which a harness is **green, sound, and disconnected
from the property it claims to measure**. Each was observed in a working
research pipeline rather than constructed for this paper. Critically, none is
detectable by sensitivity testing — the standard defence — because in all three
cases planting a defect *does* make verification fail. We present a small
vendor-neutral meta-gate that turns each failure into an executable check, and
report what a passing run of that gate does and does not establish.

## 1. The gap

The dominant assurance move for an evaluation harness is *sensitivity*: plant a
defect, confirm the pipeline goes red. This establishes that the verification
path reacts to the defects an author declared. It cannot establish that the
harness reads the inputs it claims to read, that two green tests are two pieces
of evidence, or that the population contains the phenomenon the endpoint
measures.

Those three gaps are not hypothetical. Each of the failures below was found in a
running pipeline, after that pipeline had passed ordinary review, preregistration
and mutation testing.

## 2. Three observed failures

### 2.1 A pinned input that was never read

A runner declared its results came from specific pinned bytes and recorded a
digest of them. It read the working tree instead. Every recorded digest matched,
because the digest was taken of the same working-tree copy that was executed.

**Why sensitivity misses it.** The failure is *insensitivity in the wrong place*.
Corrupting a live input correctly turns the run red; corrupting the pin changes
nothing, and nothing in the harness notices that "nothing changed" was the wrong
answer.

**The check.** Corrupt the workspace copy of every declared pinned input; the
result must not move. A runner that claims pinned provenance but reads the
working tree fails.

### 2.2 Two tests that were one piece of evidence

Two tests were cited as independent support for one assurance claim. No declared
mutation separated them: every mutation that fired one fired the other.

**Why sensitivity misses it.** Both tests fail when a defect is planted, which is
exactly what a sensitivity check demands. The correlation *is* the defect, and it
reads as health.

**The check.** For every pair of tests cited as separate evidence, require at
least one declared mutation that separates their fire patterns. The check does
not decide implication, which is undecidable; it reports that the *configuration*
cannot distinguish them, which is a fact about the configuration. Two genuinely
independent tests may coincide on a small mutation set, and the result says so
rather than asserting redundancy.

### 2.3 A population that could not move the endpoint

A preregistered experiment declared a primary endpoint, froze its protocol before
the run, instrumented both arms identically, and produced an honest number that
**could not have come out any other way**. Its corpus contained zero instances of
the feature its mechanism acted on. The endpoint was pinned to its baseline
before any data existed.

A second, independent instance arose in a different project while this paper was
being prepared. A method that consumes recorded ancestry was to be evaluated on a
corpus in which 5.5% of items recorded any ancestry at all. The measurement was
not wrong; there was nothing for the mechanism to read.

**Why sensitivity misses it.** The verifier is *sound*. Planting a defect does
make verification fail. Preregistration, ablation and mutation testing all
interrogate the **instrument**, and the instrument was fine. Nothing looked at
the **population**.

**The check.** Require every stratum the endpoint depends on to contain
instances, expressed as strata rather than one count — a single positive count
passes the case the check exists to catch. The author names the population
property their own mechanism depends on, which they must already know to explain
why the mechanism works, and a **negative control** population where the property
is absent must report below the minimum. A probe that cannot distinguish the two
is rejected as unfalsifiable, and that verdict is reported *before* any
reachability verdict.

## 3. What ordinary CI reports

| Claimed guarantee | Ordinary CI | Observed failure | Meta-gate | Assurance actually established |
|---|---|---|---|---|
| "results came from the pinned inputs" | green; digests match | runner read the working tree | **fails** (pin insensitivity) | none — the digest described the executed copy |
| "two independent tests support this" | green; both pass | no mutation separates them | **fails** (no separating mutation) | one piece of evidence, not two |
| "the endpoint was preregistered and honest" | green; sound verifier | population lacks the stratum | **refuses** (stratum empty) | the number, and nothing about the mechanism |

The pattern across all three rows: **ordinary CI is not wrong.** It answers its
own question correctly. The gap is between the question it answers and the
question a reader believes a green check answered.

## 4. Demonstration

The meta-gate is a small vendor-neutral tool run alongside an existing pipeline.
It plants each declared defect in a fresh isolated workspace, exercises the
declared checker, and emits a machine-readable result. All checks fail closed: a
surviving, invalid, missing, escaped or timed-out test fails the run.

The demo shows an ordinary green pipeline for which the meta-gate refuses the
assurance claim, for each of the three classes.

## 5. What a passing run does not establish

Stated in the artifact itself, and carried in a machine-readable
`assurance_bound` object so a summary or badge cannot drop it:

- planted defects are the ones the configuration **declares**. A verifier whose
  author declared only defects it happens to catch will pass. Deciding whether a
  declared mutation set is representative requires knowing which defects matter,
  which is the thing under study;
- sensitivity of a pin — that corrupting what the pin *resolves to* fails the
  run — depends on the pin mechanism and is reported as **not established** where
  the configuration supplies no way to exercise it, rather than assumed;
- the gate certifies no scientific claim, no representativeness, no independence
  of two sources in the world, and no honesty of an observation command.

## 6. Why this is a demo, not a benchmark

We deliberately do not report a detection rate. The failures are drawn from
observed incidents, not sampled from a population, and a rate over incidents an
author selected would describe the selection. The claim is existential and
falsifiable in the direction that matters: **these three classes exist, they
survive the standard defence, and each is mechanically checkable.** A reader who
believes a class is already covered by sensitivity testing can refute us by
exhibiting a sensitivity test that catches it.

## 7. What we are asking the workshop for

Adversarial review, in the workshop's own terms. Specifically: a fourth failure
class that survives sensitivity testing; a demonstration that one of our three is
in fact catchable by an existing method; or an independent run of the gate
against an unrelated harness. The last is the one we cannot manufacture — an
external control domain is precisely the thing a project cannot generate for
itself.

---

### Submission notes (not part of the paper)

- **Anonymity.** The paper as written names no author, project, organisation or
  repository. Both projects referenced in §2 are public and would de-anonymise
  the submission if named; the camera-ready may name them.
- **Overlap.** The workshop welcomes work under review or recently published.
  §2.3's first instance and the meta-gate are described in public repositories;
  a related preprint exists. Declare this in the submission form.
- **Remaining work is author-controlled:** render into the NeurIPS workshop
  LaTeX template, confirm the ≤4-page limit after templating, and submit through
  OpenReview at `NeurIPS.cc/2026/Workshop/Verify-Agents` before **29 August
  2026, 23:59 AoE**.
