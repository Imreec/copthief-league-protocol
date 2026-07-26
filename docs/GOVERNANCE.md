# Governance — what the tiers mean, and what it takes to move between them

Every fixture in [`vectors/`](../vectors/) carries a **tier**. The tier is a claim about *how much
you should trust it*, and this page is the only authoritative definition of those claims. If some
other document in this repo paraphrases the rule and disagrees with this page, this page wins and
the paraphrase is a bug.

Read this before opening an issue that proposes a new construction, and before believing a
`PROMOTED` label.

---

## The four tiers

| Tier | What it claims | What you should do about it |
|---|---|---|
| **`CORE`** | Two independent implementations **must** produce these bytes, or the game cannot start, cannot audit, or cannot settle. Confirmed byte-for-byte against the official reference implementation. | Reproduce every one of them before you play anyone. This is the interop floor. |
| **`PROMOTED`** | Not required by the book, but **a second independent implementation has reproduced it**. The claim has survived contact with someone else's code. | Safe to build against. Still declare it — see the locked-model rule in [`../SPEC.md`](../SPEC.md) §7. |
| **`PROPOSED`** | Published so that a second implementation *can* reproduce it. **One implementation only.** It may be wrong in ways nobody has noticed yet. | Read it, reproduce it, and tell us — reproducing it is what promotes it. Do not assume an opponent has it. |
| **`ENH`** | An opt-in enhancement (SPEC Appendix A). Binding on a pair **only** if both teams signed it into their `config/game.json`. | Ignore it unless you and your opponent both agreed to it. |

Tiers are about *evidence*, not about importance. `CORE` outranks `PROMOTED` because the book and
the reference force it, not because it was checked harder.

---

## The promotion bar

> **A fixture is promoted from `PROPOSED` to `PROMOTED` when a second, independent implementation
> reproduces it — and the evidence for that is cited in this repository.**

All three clauses bind.

**"Second."** Ours does not count. The kit's own `verify_vectors.py` reproducing a fixture proves
only that the generator and the checker agree, which they do by construction — `gen_vectors.py`
imports the checker. Self-consistency is not evidence.

**"Independent."** The other implementation must not have been derived from these vectors. The
strongest form is a clean-room build from the book that *predates* the fixture; the next strongest
is a build from the SPEC prose without reading the fixture values. An implementation that was fixed
*by* looking at our numbers has confirmed our numbers to itself and nothing more.

**"Reproduces."** Byte-exact on every case in the fixture, with zero tolerance, or — where the
fixture pins behaviour rather than bytes (a refusal truth table, a receiver contract) — the same
decision on every row. Partial reproduction is a partial result: promote the cases that were
reproduced, or don't promote.

### What counts as evidence

Two forms, both acceptable:

1. **A clean-room reproduction** — another team runs their implementation against the fixture and
   reports the result. Cite the issue number and the team.
2. **A live cross-implementation run** — the construction was exercised by two implementations
   playing each other, and the artifacts show it. Cite the run: date, what was played, and which
   observable in the archived records demonstrates it.

The citation goes **in the tree** — in `SPEC.md` beside the claim and in the fixture's own
`description`, so a reader can check the basis of a `PROMOTED` label without leaving the repo and
without asking us. A promotion whose evidence is only in someone's memory is not a promotion.

Where the evidence lives in a private repository, cite the **run**, never the path: the reader
needs to know what happened and when, not to be pointed at something they cannot open.

### What a promotion does *not* do

- **It does not make anything mandatory.** Only the book makes things mandatory. A `PROMOTED`
  fixture is still opt-in unless it is also `CORE`.
- **It does not widen what may be chosen.** The book's Appendix F binding table is unaffected by
  anything on this page. A construction that lowers a binding minimum is refused by the table
  regardless of how many implementations reproduced it.
- **It does not travel.** Promoting `X` says nothing about `Y`, even if the same team reproduced
  both and even if they ship together.

### Demotion, and what happens when the book revises

A `PROMOTED` fixture returns to `PROPOSED` if the evidence turns out not to support it — a
reproduction that was not independent, a case that was never actually run. Say so in the commit;
a quiet demotion is the same failure as a stale promotion.

**If the book revises**, every `CORE` construction is re-verified against the new reference code
*before* the vectors are updated. `CORE` means "the reference does this"; a new reference means the
claim has to be re-earned, not carried forward.

---

## How a tier is recorded (and why it cannot go stale)

The tier is declared **once**, in the `TIERS` registry at the top of
[`../gen_vectors.py`](../gen_vectors.py):

```python
"scent_book_v3.json": ("PROMOTED", "§5.1", "`multiplicative_book_v1` — the book's own scent model"),
```

From there:

- `_write()` stamps it into the fixture as `"status"`, and **refuses to write a fixture whose tier
  is not registered**;
- `verify_vectors.py` reads `status` back for its runtime banner, and **refuses a fixture that
  declares no tier** — it never carries a tier literal of its own;
- `gen_vectors.py` regenerates [`../vectors/INDEX.md`](../vectors/INDEX.md) from the same registry;
- CI regenerates everything and fails on any drift.

So the tier is written in one place and read in three, and prose elsewhere links the index rather
than restating it. For the current check count, run the checker — it prints what it actually ran:

```
53 checks across 10 fixtures — 7 CORE, 1 PROMOTED, 2 ENH
```

**Why this is mechanised rather than remembered.** It was not, and it drifted.
`multiplicative_book_v1` was promoted on 2026-07-20; the commit updated `SPEC.md`, the generator's
description and the fixture, and missed the checker's banner and the README's counts. For six days
the repo shipped a fixture that said `PROMOTED` while its own verifier printed `[PROPOSED]` beside
it — a kit whose single promise is that its claims are checkable, making an unchecked claim about
itself. The registry exists so that cannot recur.

---

## Current promotions

| Fixture / section | Promoted | Evidence |
|---|---|---|
| `multiplicative_book_v1` — [`vectors/scent_book_v3.json`](../vectors/scent_book_v3.json), SPEC §5.1 | 2026-07-20 | Clean-room reproduction by **anrbj666** (Alon Engel, Renat Karimov), issue #6: byte-exact on the kernel, both emit cases, all three walk turns, both scalar traces and every ordering-probe case with zero tolerance — from an implementation built from the book alone, predating these vectors. |

---

## Credit

Contributions are credited by name, in the SPEC beside the thing contributed and in the fixture's
`description`. This is not courtesy — it is provenance: a reader deciding how much to trust a
construction should be able to see who else has looked at it.

The reviewer who opens an issue **closes it**, after verifying the fix. We do not close other
people's issues on their behalf.

See [`../CONTRIBUTING.md`](../CONTRIBUTING.md) for how to file a reproduction, a conformance
failure, or a proposal.
