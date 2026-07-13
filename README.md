# Cop–Thief League Interop Kit

**Conformance test vectors + agreed-enhancement modules for the official final-project assignment**
— *Distributed Cops-and-Robbers over a Peer-to-Peer Network*, Dr. Yoram Reuven Segal, book v3.0.0
(Orchestration of AI Agents, University of Haifa).

**This is not the game spec — [the book](https://github.com/rmisegal/Game-P2P-Cop-Chase) is.** The
book fixes the transport (MCP/FastMCP), the game (hidden positions, the pheromone scent, capture,
scoring), the commit-reveal, the `config/game.json` constitution, and the Gmail-API reporting. This
repo adds the one thing the book does not ship: **machine-checkable vectors** for the byte-level
constructions two independent implementations must agree on — plus a few opt-in enhancements.

## Why this exists

The book says "hash the canonical JSON." But two clean-room codebases that serialize even slightly
differently will silently fail each other's post-game audit and both take a **technical loss** —
zero points. The classic trap: the reference hashes with `ensure_ascii=False` (native UTF-8), so a
Hebrew hint like `אני ליד הכיכר` is hashed raw; an implementation that `\uXXXX`-escapes it computes
a different hash, the opponent's audit re-hash of your revealed log misses, and the match voids for
both sides. There is no vector in the book to catch this before match day. There is one here.

It gets sharper: the release itself publishes **three inconsistent commit constructions** (the
book's ch.5 listing, its audit-chapter snippet, and the reference implementation each hash
differently — the book's own clarification page makes listings non-binding, so nothing resolves
it). Implement from the wrong page in good faith and you fail every audit against a team that
implemented from another. This kit pins one form (the reference's), documents the contradiction,
and ships a `divergent_forms` vector that hashes one input under all three — so a failing team can
see in seconds which construction it accidentally built.

Your competitive grade is a **league rank → 75–100**, and it's driven by how many *distinct*
opponents you can finish a clean game with (first meeting only; up to 10). Every team that can't
hash-agree with you is a game you can't score. This kit is how a team certifies — alone, on its own
schedule — that it will interoperate.

## What's here

| File | What it is |
|---|---|
| [`SPEC.md`](SPEC.md) | The interop surface: canonical JSON, commit-reveal, agreement signature + `game_uid`, pheromone math, report bytes — mapped to the book's chapters, plus opt-in enhancements |
| [`vectors/`](vectors/) | Machine-generated fixtures — 5 CORE files (book conformance) + 2 ENH files (opt-in), 20+ checks |
| [`verify_vectors.py`](verify_vectors.py) | Stdlib-only reference checker — `python verify_vectors.py` |
| [`gen_vectors.py`](gen_vectors.py) | Regenerates every fixture from the reference constructions; CI fails on drift |
| [`examples/`](examples/) | A worked exchange (agreement → sealed steps → audit → settlement), every hash real and regenerable |

The constructions were confirmed byte-for-byte against the official reference implementation. Every
vector is generated from our own synthetic inputs — no reference content is copied.

## The interop surface (what must match cross-team)

1. **Canonical JSON** — `sort_keys=True, ensure_ascii=False, separators=(",", ":")`, UTF-8.
2. **Commit-reveal** — `SHA256(canonical_json(payload)|nonce)`; the opponent re-hashes your
   revealed log at audit.
3. **Agreement signature** — `SHA256(canonical_json(terms)|nonce)`; the pre-game gate.
4. **`game_uid`** — `UUID(SHA256(canonical(terms)|sorted-group-ids)[:16])`.
5. **Pheromone field** — radial emission + per-step decay (self-test, but breaks your belief map if wrong).
6. **Report bytes** — the emailed body is the exact canonical bytes that were hashed.

Everything else — strategy, GUI, prompts, infra — is private and needs no agreement.

## How to adopt

1. Read [`SPEC.md`](SPEC.md) — it's short and maps each construction to a book chapter.
2. Run `python verify_vectors.py` to see the reference constructions reproduce every fixture.
3. Port the checks into your own suite and point them at `vectors/*.json`. When your implementation
   reproduces every **CORE** vector, your bytes match every other conformant team's.
4. The real acceptance test: feed a partner's revealed log to your verifier and yours to theirs —
   both audits must pass with zero `tamper_forfeit`. The sparring server (Appendix B) exists so you
   can do this without a partner online.

## Enhancements (opt-in)

The book invites teams to agree on extras and exploit undefined gaps, as long as it's signed into
`config/game.json` and weakens no mandatory minimum. This repo offers, as opt-ins: a transcript
interlock DAG (`prev`/`prev_recv`) that hardens the book's per-step commits against wholesale
re-forgery; a joint-seed coin flip for randomized-but-fair starts; synchronized fixture scheduling;
and demo staging. See SPEC Appendix A.

## Relationship to the book (and IP)

The book (© Dr. Segal) and its reference implementation (Educational-Use-only) are the authority;
this kit is complementary, not a competing standard. We cite the book by chapter, link the reference
repo, and copy neither its text nor its code. Hash outputs are facts, the algorithms are the book's,
the words here are ours.

— Team ImreEyal
