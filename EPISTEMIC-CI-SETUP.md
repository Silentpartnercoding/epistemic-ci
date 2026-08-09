# Agent-assisted setup

This file is an execution contract for a coding or review agent pairing
Epistemic CI with another repository. The agent may discover and propose. It
must not silently supply the repository owner's meaning or treat its own review
as independent evidence.

## Procedure

1. Run discovery without changing project code:

   ```bash
   epistemic-ci init --root . --output epistemic-ci-onboarding.json
   ```

2. Read the report. Treat verification commands and artifacts as candidates,
   not facts.
3. Ask the repository owner, in plain language:
   - Which final files or results do people actually trust?
   - Which planted mistakes must make verification fail?
   - What exact population or evidence produced the result?
4. Restate the answers and the discovered verification command. Explain the
   machine consequence of each answer. Do not continue until the owner confirms
   the restatement.
5. Write an answers file using
   `epistemic-ci.onboarding-answers.v1`. `human_confirmed: true` records an
   assertion supplied through the agent; it is not proof of identity or
   authority.
6. Implement the smallest project-specific adapters and
   `.epistemic-ci.json` needed to express those confirmed boundaries. Do not
   broaden the claim, population, artifacts, or mutation set.
7. Validate the complete pairing:

   ```bash
   epistemic-ci init \
     --root . \
     --answers .epistemic-ci-answers.json \
     --config .epistemic-ci.json \
     --output epistemic-ci-onboarding.json \
     --force
   ```

8. A pairing is only ready to present when the report status is
   `ready_for_human_review`. Show the owner:
   - trusted outputs;
   - checked population;
   - planted failure cases;
   - candidate-config fingerprint;
   - all four deterministic check results.
   The command also verifies that the candidate configuration uses the
   human-confirmed verification command and binds every trusted output.
9. Open a pull request. Do not merge or claim independent verification without
   the required human or separately controlled reviewer.

## Fail-closed boundaries

- Do not turn discovery guesses into confirmed facts.
- Do not use natural-language answers as executable tests; translate them into
  replayable mutations and commands.
- Do not claim the observation command is honest merely because its JSON is
  well formed.
- Do not execute untrusted pull-request code with privileged credentials.
- Do not describe two agents under one controller as independent.
