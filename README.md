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
differently — and the book's own clarification page makes printed listings non-binding, so the
choice formally falls to the teams). Implement from the wrong page in good faith and you fail
every audit against a team that implemented from another. This kit pins the reference's form —
which is also the only one of the three that binds the full record (the audit-snippet form hashes
just `nonce|move`, leaving `state` and `intent` unbound) — documents the contradiction per the
book's academic-freedom clause, and ships a `divergent_forms` vector hashing the same sealed
record under all three, so a failing team can see in seconds which construction it accidentally
built.

Your competitive grade is a **league rank → 75–100**, and it's driven by how many *distinct*
opponents you can finish a clean game with (first meeting only; up to 10). Every team that can't
hash-agree with you is a game you can't score. This kit is how a team certifies — alone, on its own
schedule — that it will interoperate.

## What's here

| File | What it is |
|---|---|
| [`SPEC.md`](SPEC.md) | The interop surface: canonical JSON, commit-reveal, agreement signature + `game_uid`, pheromone math, report bytes, locked-model declarations — mapped to the book's chapters, plus opt-in enhancements |
| [`vectors/`](vectors/) | Machine-generated fixtures, one file per construction — each declares its own tier; roster at [`vectors/INDEX.md`](vectors/INDEX.md) |
| [`verify_vectors.py`](verify_vectors.py) | Stdlib-only reference checker — `python verify_vectors.py`; prints the roster and the totals it ran |
| [`gen_vectors.py`](gen_vectors.py) | Regenerates every fixture from the reference constructions; CI fails on drift |
| [`examples/`](examples/) | A worked exchange (agreement → sealed steps → audit → settlement), every hash real and regenerable |
| [`sparring/`](sparring/) | A practice opponent you run locally — full rulebook, no mail, simple brains. `python -m sparring.cli selfplay` |
| [`docs/WARNINGS.md`](docs/WARNINGS.md) | The mistakes that cost points — including the opponent's. Read before configuring any recipient |
| [`docs/LEAGUE-OPS.md`](docs/LEAGUE-OPS.md) | How a scheduled window actually runs: the T-protocol, netcheck discipline, topologies, budget math |
| [`tools/`](tools/) | `check_artifacts.py` (your four artifacts, before anyone sees them) and `netcheck.py` (your network, before you name a start time) |
| [`docs/GOVERNANCE.md`](docs/GOVERNANCE.md) | What `CORE` / `PROMOTED` / `PROPOSED` / `ENH` claim, and what it takes to promote one |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | How to report a conformance failure, file a reproduction, or propose a construction |

The constructions were confirmed byte-for-byte against the official reference implementation. Every
vector is generated from our own synthetic inputs — no reference content is copied.

## The interop surface (what must match cross-team)

1. **Canonical JSON** — `sort_keys=True, ensure_ascii=False, separators=(",", ":")`, UTF-8.
2. **Commit-reveal** — `SHA256(canonical_json(payload)|nonce)`; the opponent re-hashes your
   revealed log at audit.
3. **Agreement signature** — `SHA256(canonical_json(terms)|nonce)`; the pre-game gate.
4. **`game_uid` and `game_id`** — `UUID(SHA256(canonical(terms)|sorted-group-ids)[:16])` and
   `"-vs-".join(sorted(group_ids))`. Both sort the pair, so neither peer has to be told which order
   to use; a peer that names itself first gives one match two different `game_id`s.
5. **Pheromone field** — radial emission + per-step decay (self-test, but breaks your belief map if wrong).
6. **Report bytes + consensus signature** — the emailed body is the exact canonical bytes that
   were hashed, and the consensus signature inside the report uses a **second (spaced)
   serialization** with sign-then-insert ordering (SPEC §6 — found by Alon's team).
7. **Locked-model declarations** — one doc schema (`family`/`name`/`params`/`example`) serving
   scent models, wire shapes and information modes, hashed and declared at negotiate time.
   Refusal fires only when **both** peers declare and disagree; silence never refuses (SPEC §7).

Three more are **behaviour** rather than bytes, pinned as truth tables because answering them
differently costs a game just as surely as a bad hash — and unlike a hash, you cannot catch these
by comparing a digest with a partner: the locked-model refusal rule (§7), the at-least-once
receiver contract (§7.1) and the pairing declaration `sub_game_number` + `role` (§7.2).

Everything else — strategy, GUI, prompts, infra — is private and needs no agreement.

## How to adopt

1. Read [`SPEC.md`](SPEC.md) — it's short and maps each construction to a book chapter.
2. Run `python verify_vectors.py` to see the reference constructions reproduce every fixture.
3. Port the checks into your own suite and point them at `vectors/*.json`. When your implementation
   reproduces every **CORE** vector, your bytes match every other conformant team's.
4. Check your own artifacts before anyone else does — `python tools/check_artifacts.py <dir>`.
   It catches the defect that zeroes **both** teams: a report whose `game_uid` is not the one the
   handshake derived.
5. Before you name a start time, prove your network: `python tools/netcheck.py <peer-url>` to
   classify their edge, and `--loopback <port> <your hostnames>` to prove your own receiving path.
   A bare `502` check cannot tell a healthy idle tunnel from one with no ingress.
6. Read [`docs/WARNINGS.md`](docs/WARNINGS.md) before configuring any recipient, and
   [`docs/LEAGUE-OPS.md`](docs/LEAGUE-OPS.md) before agreeing a window.
7. Rehearse a whole series against the [sparring peer](sparring/) — the full rulebook, no mail,
   and it speaks Hebrew on the wire so a serializer that escapes non-ASCII fails there rather than
   at a real opponent's audit.
8. The real acceptance test: feed a partner's revealed log to your verifier and yours to theirs —
   both audits must pass with zero `tamper_forfeit`.

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
