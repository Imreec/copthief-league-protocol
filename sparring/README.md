# The sparring peer

A practice opponent you run **locally**. The full rulebook, no mail, simple brains.

Play a complete six-sub-game series against it before you ever contact another team — and find
out about your serialization, your receiver contract and your artifacts on your own schedule
instead of during someone else's window.

```bash
# a full six-sub-game series against itself — no dependencies, a few seconds
python -m sparring.cli selfplay

# stand up a real peer for your implementation to dial
docker compose -f sparring/docker-compose.await.yml up
# then point your peer at http://localhost:8931/mcp
```

---

## What you get

A conformant opponent that will refuse you for the same reasons a real team would, and say which:

- the four MCP tools under the reference's names, **including the asymmetry** — `submit_audit`
  takes `payload`, the other three take `message`;
- a signed-terms handshake that distinguishes **terms absent** (a wire-shape fault on the sender's
  side) from **terms differing** (a constitution disagreement) — and prints the canonical strings,
  because a float that differs only in `repr` is invisible in a value diff and fatal to a signature;
- locked-model declarations, pairing declarations, and the at-least-once receiver contract;
- commit-reveal with a real end-of-game **mutual audit** that will call you tampered if your bytes
  differ from the kit's — which is exactly what a real opponent's audit would do;
- all four artifacts under one `game_uid`, named by the book's App. F grammar.

**It speaks Hebrew and emoji on purpose.** With `--hint-lang mixed` (the default) some sub-games
carry Hebrew hints and one carries an astral-plane character. SPEC §2 calls `ensure_ascii=False`
the single most important fact in the kit, because a serializer that escapes non-ASCII produces
hints your opponent cannot re-hash — and the failure surfaces as a false `tamper_forfeit` that
zeroes *both* teams. A peer that only ever said ASCII would let you finish a whole rehearsal
without discovering it. Use `--hint-lang en` if you want that off.

## What you do *not* get, by construction

| | |
|---|---|
| **No mail. At all.** | Not "disabled" — absent. `python -m sparring.guards.no_mail` scans the source and refuses to let the peer start if a mail surface exists, and the manifest hash of that scan is written into the declaration artifact. Seven rules, including outbound-network confinement, because a package could import no mail library and still open a socket to port 587. |
| **No report.** | Sparring is an uncounted warm-up (App. E rule 52), so nothing is owed by either side. The result artifact carries **no signature key at all**, only `"settlement": "not_owed"` — a label can be edited, but a missing preimage cannot be emailed. |
| **No tuned anything.** | Random and greedy, public-knowledge and shallow. `guards/purity.py` holds `policies/` to an import surface with no file reads and no weights formats, so a brain here physically cannot load a trained model. |
| **No counted mode.** | `RunMode.SPARRING` is the only value that exists. A mode whose preflight demanded a deliverable would make this host refuse itself at startup, so the modes that would demand one are not in the code. |

**Point your own mail at yourselves or at nothing while practising — never at the lecturer.**
See [`../docs/WARNINGS.md`](../docs/WARNINGS.md) §3.

## Commands

```
python -m sparring.cli selfplay                    # zero dependencies
python -m sparring.cli serve  --peer <url>         # a real peer over MCP
python -m sparring.cli doctor --peer <url>         # classify their edge before you agree a T
python -m sparring.cli replay <dir>                # Verified OK / TAMPERED
```

Exit codes are distinct so a script can tell failures apart: `0` clean · `2` usage · `3` preflight
refused · `4` handshake refused · `5` port already held · `6` a sub-game ended in a technical loss
or tamper forfeit · `7` no opponent arrived.

Useful flags: `--policy {greedy,random}` · `--scent-model {subtractive_chebyshev_v1,multiplicative_book_v1}`
· `--seed` · `--lie-rate` · `--hint-lang {en,he,mixed}` · `--reorder-window` · `--turn-timeout`.

## Two honest notes

**Greedy vs greedy always draws.** Both agents move one cell per turn, so a pursuer cannot close
distance on an evader that keeps moving away; the cop only wins by cornering, and the greedy thief
weights its moves to keep exits open. That is a real property of the game rather than a bug, and it
is worth knowing before you tune anything. Use `--policy random` if you want to see captures, or
just play your own brain against it — which is the point.

**This is a third independent implementation of the game layer, not of the crypto.** The rules,
engine, state machine, wire, receiver contract and artifacts are written from `SPEC.md` and the
book. The byte-level constructions are imported from the kit's own `verify_vectors.py` — the same
functions the fixtures are generated from — so the peer cannot drift from the published vectors,
and equally **cannot catch a bug inside them**. Playing a real team remains the true test.

## How it is checked

Everything except the HTTP surface runs with **nothing installed**:

```
python -m sparring.guards.no_mail        # the mail surface is absent
python -m sparring.guards.purity         # one hash seam, one clock, no tuned weights
python -m unittest discover -s sparring/tests -t .
```

The suite includes a seeded six-sub-game series over an in-process transport, and **the same
series again over a transport that duplicates, reorders and drops-then-retries messages** — with
the outcome ledger required to come out byte-identical. That is the §7.1 receiver contract proven
at the level that matters: not "we handled a duplicate" but "the duplicates changed nothing about
who won".
