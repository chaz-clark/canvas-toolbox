# Answer keys (grading reference)

Optional folder. Use this for assignments where the grader needs a reference
solution — typically code/notebook take-home assessments (Key Challenges, lab
exercises, problem sets). For rubric-only or outcomes-only assignments where
the grader judges against a rubric without a reference solution, this folder
doesn't apply.

## Layout

Drop the instructor answer-key notebook here, one folder per assignment:

```
grading/answer_keys/
  <assignment_a>/  ← drop the answer-key .ipynb here
  <assignment_b>/  ← drop the answer-key .ipynb here
```

Any filename is fine — e.g. `grading/answer_keys/kc1/kc1_key.ipynb`. One
notebook per assignment is the cleanest shape, but one notebook covering all
sections of an assignment works too.

## What happens to the raw `.ipynb`

1. The raw `.ipynb` you drop here is **gitignored and never committed** —
   the answer key is the instructor's work and likely hardcodes tokens
   (Databricks PATs, GitHub PATs, API keys, S3 secrets) used for testing.
2. On run, the key is **secret-scrubbed** (tokens/PATs redacted, emails
   redacted, user paths redacted) and extracted to a clean reference
   (`<assignment>/key_clean.md`) containing code + the expected text outputs
   per question. Images are dropped to keep the file small.
3. The grader reads the **clean** reference (`key_clean.md`) to sharpen
   per-question feedback. The key is a **reference, not a gate** — many
   real-world tasks have valid alternate approaches, so the key informs
   feedback; it doesn't force one right answer into the score.

Run the secret-scrub with:

```bash
uv run python canvas_toolbox/lib/tools/grader_prep_answer_key.py \
  grading/answer_keys/<assignment>/<key>.ipynb
```

Output lands alongside the source as `key_clean.md`.

## FERPA / security notes

- `.ipynb` files (raw answer keys) are gitignored; only this README and the
  empty `.gitkeep` placeholder folders are tracked.
- `key_clean.md` is gitignored too — answer keys stay local. The clean
  version is what the grading AI reads; the raw is never seen by the AI.
- **Revoke any hardcoded PAT/token regardless** — scrubbing protects the
  cloud hop, not the token itself. Treat the raw `.ipynb` as containing
  *secrets* even after scrub.
- The answer key is the **instructor's** own work, so the scrubber redacts
  *secrets* (PATs, tokens, API keys, emails, /Users paths), not *names* —
  there are no student names in an instructor's own answer key. For
  student work, use `grader_deidentify_*` instead.

## When to skip this folder

- Rubric-only assignments (essay, performance review, project defense — the
  rubric is the only reference)
- Outcomes-only assignments (the grader scores against named outcomes, not a
  reference solution)
- Discussion grading (no single reference answer)

Skip means: don't create the folder, don't run `grader_prep_answer_key.py`.
The grader operates fine without an answer key when the rubric is the
authority.
