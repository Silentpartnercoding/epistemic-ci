# NeurIPS 2026 — "Who Verifies the Agents?" demo submission

**Status: drafted, not submitted.**

| | |
|---|---|
| Deadline | **29 August 2026, 23:59 AoE** — verified from the workshop site |
| Track | Demo paper, **≤4 pages** excluding references/appendices |
| Review | **Double blind** |
| Archival | **Non-archival** — appears on OpenReview, not formal proceedings |
| Overlap | Work under review or recently published is **welcome** |
| Portal | OpenReview `NeurIPS.cc/2026/Workshop/Verify-Agents` |

Source: [`PAPER.md`](PAPER.md). Current length ~1,340 words including the
submission notes, which is comfortably inside four pages once templated.

## The claim, and how to refute it

Three failure classes in which an evaluation harness is green, sound, and
disconnected from what it claims to measure — and **all three survive sensitivity
testing**, because planting a defect makes verification fail in every one of
them.

The claim is existential, not a rate. It is refuted by exhibiting a sensitivity
test that catches any of the three, and that invitation is in the paper.

## Why no detection rate is reported

The failures are observed incidents, not a sample. A rate over incidents the
author selected would describe the selection rather than the method — the same
defect the paper is about, committed by the paper. This is deliberate and stated
in §6.

## Evidence provenance

Every row in §3 is an observed failure in a working pipeline, not a construction:

- **pinned input** — a runner that recorded digests of the working-tree copy it
  actually executed;
- **evidential independence** — two tests cited as separate evidence that no
  declared mutation separated;
- **effect reachability** — two independent instances in different projects. The
  second arose while this paper was being drafted: a method consuming recorded
  ancestry, evaluated on a corpus where 5.5% of items record any ancestry.

## Author-controlled steps

1. Render into the NeurIPS workshop LaTeX template.
2. Confirm ≤4 pages **after** templating — the table is the item most likely to
   push it over.
3. Keep it anonymous. Both referenced projects are public and naming either
   de-anonymises the submission; the camera-ready may name them.
4. Declare the overlap (public repositories, related preprint) on the form.
5. Submit via OpenReview before the deadline.
