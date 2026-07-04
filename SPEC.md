# Cop–Thief League Protocol — SPEC v0.2-draft

**Status:** DRAFT for league review — written *before* the official final-project assignment
publishes. Everything here is either (a) battle-tested in the EX06 inter-group bonus (played live,
hash-confirmed byte-identical between two independent implementations), or (b) explicitly marked
**PROPOSED**. Version **1.0** will be cut only after the official assignment PDF drops; §11 lists
what it must resolve.

**Goal:** let any two conforming teams play a full cross-team series — connection, game, result
agreement, identical report emails — with **zero pairwise negotiation**. Conformance is self-serve:
implement to this spec, pass the test vectors in `vectors/`, and you can play anyone who did the same.

## Changes from v0.1-draft

All from the EX06 post-mortem review in
[issue #1](https://github.com/Imreec/copthief-league-protocol/issues/1) (anrbj666 — thank you):

- **§6.4 rewritten (breaking, new vectors):** start derivation now uses 4 digest bytes per cell (no
  single-byte bias, works for any board), a minimum Chebyshev start distance with deterministic
  re-draw (no more one-round instant captures), and a deterministic re-run index (no "by agreement").
- **§6.3:** terminal-ply `turn` pinned (stays on the mover — verified against the EX06 live log)
  plus a terminal-ply vector; note on why fatal state-mismatch is safe in this design.
- **§4.1:** match card split into a hashed `agreement` and an unhashed `transport` (tunnel restarts
  no longer brick the handshake); `scheduled_utc` moved out of the hashed body.
- **§5:** every message now carries a typed trailer (`hello` / `move` / `report_sha`); explicit
  hold-don't-advance rule on unexpected input; single-line + size bound; sender resend rule; `prev`
  hash-chain field making each side's transcript tamper-evident.
- **§2:** floats are now explicitly *rejected* by the reference implementation; astral-plane
  escaping pinned by a vector. New fixtures: match-card hash, joint-seed, terminal state, negative
  vectors (floats, commit-binding). CI runs the verifier and regenerates everything on every push.
- Editorial: §6.1 exemption for the one non-canonical-JSON preimage; §6.2 field-order note;
  trailer parsed-not-hashed clarification; Mode B cards rejected until unblocked; Appendix C
  (non-normative transport tips, contributed by anrbj666).

---

## 1. Design principles

1. **Peer topology, no trusted third party.** Each team runs its own MCP server and its own
   orchestrator/LLM. Nothing central executes game logic. Integrity comes from cryptographic
   commitments and per-ply state hashes, not from a referee.
2. **Natural language is the semantic channel.** Agents communicate intent, observations, and
   negotiation in free prose, interpreted by the receiving side's LLM. The machine-verifiable data
   rides in a small attachment that is inserted and parsed **verbatim** — never generated or
   paraphrased by an LLM.
3. **Fail at ply zero, not ply 37.** Version and configuration mismatches are detected in a
   handshake before the first move. A game that starts is a game both sides can finish.
4. **Everything hashable is canonical.** One canonical JSON form (§2) underlies every hash in the
   protocol (single documented exemption: §6.4). Two implementations that agree on the data agree
   on the bytes. (Note the converse carefully: the wire trailer itself is *parsed*, not hashed —
   see §5.2.)

### 1.1 Terminology

| Term | Meaning |
|---|---|
| **series** (match) | the full encounter between two teams: `num_games` sub-games with a role swap, settled by one mutually confirmed report |
| **sub-game** | one pursuit episode: start cells derived from the seed (§6.4), ends in capture, round-cap survival, or void |
| **round** | one thief ply followed by one cop ply; a sub-game lasts at most `rounds` rounds = `2*rounds` plies |
| **ply** | a single agent's move. Plies are numbered from 0 within a sub-game; thief-first ⇒ the thief owns even plies, the cop odd ones |
| **role swap** | after `swap_at` sub-games the teams exchange cop/thief roles |
| **void** | a sub-game annulled for technical failure (§8.3), re-run so the series completes its quota |
| **EX06** | the course's previous assignment, in which a precursor of this protocol was played live between two independent implementations |

## 2. Canonical JSON (normative)

Every hash in this protocol is `SHA-256` over **canonical JSON bytes** of an object:

- Serialize with **sorted keys**, separators `(",", ":")` (no whitespace).
- **Non-ASCII characters are `\uXXXX`-escaped** (Python `json.dumps` default, `ensure_ascii=True`).
  Astral-plane characters (emoji etc.) become **surrogate pairs** (`"🙂"` → `🙂`) —
  pinned by a fixture in `vectors/canonical_json.json`.
- Encode the resulting string as **UTF-8** (after escaping it is pure ASCII).
- Numbers: **integers only**. Implementations MUST **reject** any float anywhere in an object to be
  hashed (float repr differs across languages; EX06 nearly lost a series to a hand-typed `7.5`).
  The reference implementation raises; `vectors/negative.json` lists objects that MUST be rejected.
- Booleans/null are JSON literals; strings are JSON-escaped.

Python reference: `json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()` after a
recursive no-floats check. Edge-case fixtures: `vectors/canonical_json.json`.

## 3. Topology and transport

- Each team exposes **two MCP servers** (cop, thief) built with FastMCP over **HTTPS**.
- Auth is transport-layer: `Authorization: Bearer <token>`, rejected **before** any tool dispatch.
  Tokens are exchanged privately per match (they are *not* in the match card, §4.1).
- The only public cross-team tool is **`deliver_message(text: str) -> ack`** — a **dumb mailbox**.
  It records the message and returns an acknowledgment. It MUST NOT run an LLM, apply game logic,
  or block on a reply in the response path.
- The loop is **async and client-driven**: on your turn, your orchestrator calls the *opponent's*
  `deliver_message`; you learn their reply by polling your **own** inbox (how your client reads its
  own inbox is private — in-process co-location is the proven pattern).
- The **LLM lives in the orchestrator (client), never in the MCP server.** Servers are secretless.
- Non-normative transport experience (tunnels, rate caps): Appendix C.

## 4. Match setup

### 4.1 Match card (PROPOSED)

A match is defined by one JSON document both teams hold. It has two parts: a hashed **`agreement`**
(the rules both sides commit to) and an unhashed **`transport`** (operational facts that may
legitimately change between issuance and game time — a restarted tunnel MUST NOT brick a match).

```json
{
  "agreement": {
    "protocol": "league/0.2",
    "match_id": "2026-08-01-aleph-vs-bet",
    "groups": {"group_1": "Team-Aleph", "group_2": "Team-Bet"},
    "grid": [10, 10],
    "rounds": 25,
    "num_games": 6,
    "swap_at": 3,
    "max_barriers": 0,
    "disclosure": "A",
    "scent_k": null,
    "stage": "demo",
    "report_email": "league-reports@example.com",
    "seed": "<joint seed, §4.2>",
    "timeouts": {"per_ply_seconds": 120, "per_subgame_seconds": 1800, "max_messages": 200}
  },
  "transport": {
    "urls": {
      "group_1_cop": "https://aleph.example/cop/mcp",
      "group_1_thief": "https://aleph.example/thief/mcp",
      "group_2_cop": "https://bet.example/cop/mcp",
      "group_2_thief": "https://bet.example/thief/mcp"
    },
    "scheduled_utc": "2026-08-01T18:00:00Z"
  }
}
```

- `config_sha256 = SHA-256(canonical_bytes(agreement))` — the `agreement` object **only**. Fixture:
  `vectors/match_card.json`.
- `transport` may be updated any time (new tunnel URL, rescheduled time) by posting the new values
  on the match's lobby Issue (Appendix B) or announcing them in `hello` prose; the agreement hash
  is unaffected. `scheduled_utc` is ISO-8601 UTC (`YYYY-MM-DDThh:mm:ssZ`) and is coordination
  metadata only — never enforced by implementations (clock skew exists; give ±2 min grace socially).
- `rounds` counts **rounds** (thief ply + cop ply): a sub-game is at most `2*rounds` plies.
  Role-swap: sub-games `0..swap_at-1` = group_1 cop vs group_2 thief; the rest swap.
- `timeouts.max_messages` is **per sub-game** (all `deliver_message` receipts, prose included).
- `stage` is a **safety interlock** for order-dependent scoring: implementations MUST NOT send any
  report to the official (lecturer) destination unless `stage` is `"official"`, and no match card
  may be issued with `stage: "official"` until every league team has jointly declared the real
  season open. During the demo season (Appendix B), `report_email` points at a league test mailbox
  or the teams' own inboxes. Implementations MUST take the destination from the card — never
  hardcode it. For the same reason, implementations SHOULD require an explicit human arm step (a
  flag or prompt) before *starting* a `stage: "official"` series: under order-dependent scoring,
  starting a counted game is as consequential as emailing its report.
- Game-rule values (`grid`, `rounds`, scoring) are placeholders until the official assignment fixes
  them — the *shape* of the card is what this spec pins. Bearer tokens are exchanged out of band,
  never in the card.

### 4.2 Joint seed (PROPOSED — trustless coin flip)

Per-sub-game start cells derive from a shared seed (§6.4). So neither team can pick a favorable
seed, generate it jointly by commit-reveal:

1. Each team picks a private random hex string `r` and publishes
   `share_commit = SHA-256(canonical_bytes({"seed_share": r}))`.
2. After both commitments are exchanged, both reveal `r`.
3. `seed = SHA-256(canonical_bytes({"shares": [r_group_1, r_group_2]}))` (group_1's share first).

Either side can verify the other's share against its commitment. Fixtures:
`vectors/joint_seed.json`. A simpler fallback (used in EX06): seed = the SHA-256 report hash of a
previous agreed game.

### 4.3 Ply-zero handshake

Before any move of sub-game 0, each orchestrator sends one greeting message whose trailer (§5) is:

```json
{"v": 1, "type": "hello", "protocol": "league/0.2", "config_sha256": "<hex64>", "group": "Team-Aleph"}
```

- `config_sha256` = canonical hash of the match card's `agreement` (§4.1).
- If the two sides' `protocol` or `config_sha256` differ, the match **MUST NOT start**. Report the
  mismatch to the humans; nothing is void because nothing began.
- The greeting prose is a natural place to confirm readiness and announce current `transport`
  values (fresh tunnel URLs). Tokens should already be configured before the handshake.

## 5. In-game wire format

Every message is **one string** passed to `deliver_message`, with two parts:

```
Your scent trail is getting colder toward the north-east, so I'm
sweeping back along the west wall. Committing my move below.
---LEAGUE-v1---
{"v":1,"type":"move","game":2,"ply":14,"ack":13,"move":[3,4],"commit":"<hex64>","nonce":"8f2c01ab","reveal":null,"state":"<hex64>","prev":"<hex64>"}
```

### 5.1 The prose body (above the fence)

Free natural language — the *actual* agent-to-agent communication (intent, observation, deception,
negotiation). The receiving side interprets it with its LLM. It MUST NOT be required for mechanical
correctness: a conforming implementation can verify and apply the ply from the trailer alone.

### 5.2 The trailer (below the fence)

- Fence line: exactly `---LEAGUE-v1---` on its own line. Everything after the **last** fence line
  must parse as a single JSON object on **one line**, compact (no internal newlines), at most
  **4096 bytes** (EX06: a line-splitting parser ate multi-line messages until prose was flattened —
  the bound keeps trailers trivially bufferable).
- The sender constructs the trailer **programmatically** and appends it verbatim; LLM output MUST
  NOT be able to alter it.
- **The trailer is parsed, not hashed** — field order inside it is free; only the *values* it
  carries (`commit`, `state`, …) are canonical constructions. The one exception is `prev` (below),
  which hashes the previous trailer's exact transmitted bytes.
- **Every trailer carries `type`**: `"hello"` (§4.3), `"move"`, or `"report_sha"` (§9). A receiver
  that gets an unparseable trailer, an unknown `type`, or a message that is valid but not the one
  it is waiting for MUST **hold and re-poll — never advance** on it. (EX06's deepest bug was a
  parser mis-classifying a message and advancing; one side skipped a sub-game and the match
  deadlocked.)
- `move`-type fields:

| Field | Type | Meaning |
|---|---|---|
| `v` | int | trailer schema version (this spec: `1`) |
| `type` | string | `"move"` |
| `game` | int | 0-based sub-game index in the series (kills cross-game misattribution) |
| `ply` | int | 0-based ply number of **this** move within the sub-game |
| `ack` | int | highest opponent `ply` applied so far; `-1` if none |
| `move` | `[row,col]` \| null | this ply's destination — cleartext in Mode A; `null` in Mode B |
| `commit` | hex64 | `commit(move_pos, nonce)` for this ply (§6.2) |
| `nonce` | string \| null | revealed immediately in Mode A (audit); `null` in Mode B |
| `reveal` | object \| null | Mode B delayed reveal: `{"ply": t-k, "pos": [row,col], "nonce": "..."}` |
| `state` | hex64 | common-state hash **after** applying this ply (§6.3) |
| `prev` | hex64 \| null | SHA-256 of the exact UTF-8 bytes of the previous `move` trailer **this sender** transmitted in this sub-game (the line after the fence, no trailing newline); `null` for the sender's first move of the sub-game |

- `prev` makes each side's per-sub-game transcript a **tamper-evident hash chain**: neither side
  can later rewrite its own history, and a committed JSONL transcript plus the chain is
  self-authenticating evidence for dispute resolution. Resends (§8.2) retransmit identical bytes,
  so the chain is unaffected.
- Unknown fields: receivers MUST ignore unknown keys (forward compatibility within a major `v`).
- Coordinate frame (normative, as in EX06): **0-based, top-left origin, `[row, col]`, row-major**.
- Sequencing: `game`/`ply`/`ack` subsume EX06's `SG:` prefix and hold/skip patch. Plies are
  numbered globally within a sub-game (thief-first ⇒ one role owns the even plies, the other the
  odd), so the opponent's expected next `ply` is always known: their first ply by role, then
  `last_applied_opponent_ply + 2`. A receiver holds a future-`ply` block, discards an
  already-applied one (idempotent by `commit`), and applies only the expected same-`game` block.

## 6. Hash constructions (normative — pinned by `vectors/`)

### 6.1 One rule for all (one exemption)

All constructions are `SHA-256(canonical_bytes(obj))` per §2 — **except** the start-cell derivation
(§6.4), which hashes the raw UTF-8 string `f"{seed}:{index}:{draw}"` (a keyed counter, not a JSON
object). That is the protocol's only non-canonical-JSON preimage. The fixtures for §6.2/§6.3 were
generated by the EX06 implementation that played the live hash-confirmed game; §6.4's fixtures are
generated by this repo's reference implementation (v0.2 changed the construction).

### 6.2 Position commitment — `vectors/position_commit.json`

`commit(pos, nonce) = sha256_canonical({"nonce": nonce, "pos": [row, col]})`

(Shown in canonical — sorted — key order; construction order in code is irrelevant because
canonicalization sorts.) Binding both ways: changing position **or** nonce changes the hash —
`vectors/negative.json` pins binding pairs. Nonce is any string chosen by the mover (length free;
16–32 hex chars typical). Example: pos `[2,3]`, nonce `"abc123"` →
`3b37bed7b664a8aa96e14072f885fee2cb617bfb57cd42c1fa7430c8d98f2d22`.

### 6.3 Common-state hash — `vectors/state_hash.json`

`state_hash(barriers, turn, move_count) = sha256_canonical({"barriers": sorted [row,col] pairs (deduped), "move_count": N, "turn": "cop"|"thief"})`

- `move_count` = plies completed (0 before the first ply; +1 per ply).
- `turn` = the role **to move next**. **Terminal ply (normative):** when a ply *ends* the sub-game
  (capture or round cap), there is no next mover — `turn` **stays on the mover** of that final ply.
  This is what the EX06 engines actually did and what produced byte-identical finals live (the
  terminal fixture in `vectors/state_hash.json` reproduces the EX06 live log's final frame).
- The sender computes it **after** applying its own ply; the receiver applies the received move to
  its replica, recomputes, compares. Any mismatch = desync (§8.3), and it is **fatal** (void).
  *Why fatal is safe here:* EX06 had to downgrade state mismatch to a warning mid-league because
  retry-induced `move_count` drift and the terminal-`turn` ambiguity produced false mismatches.
  Both causes are closed in this spec (idempotent receive by `commit` + resend-identical-bytes §8.2;
  terminal rule above) — so a mismatch now means a real divergence. Do not downgrade it.

### 6.4 Seed → start cells — `vectors/derive_starts.json` (v0.2, breaking)

For a draw counter `draw = 0, 1, 2, …` on an `n×n` board:

```
digest    = SHA-256(utf8(f"{seed}:{index}:{draw}"))          # raw digest bytes
cop_cell  = int.from_bytes(digest[0:4],  "big") mod n²
thief_cell= int.from_bytes(digest[4:8],  "big") mod n²
d_min     = min(max(ceil(n/3), 2), n-1)                       # 5→2, 8→3, 10→4
accept iff chebyshev(cop, thief) ≥ d_min, else draw += 1 and re-derive
cell i → [i // n, i mod n]
```

- **4 bytes per cell** removes the v0.1 single-byte flaws (modulo bias — cells 0–55 were 1.5× more
  likely on 10×10 — and the hard ceiling that made cells ≥256 unreachable on n ≥ 17).
- **`d_min` (minimum Chebyshev start distance)** removes instant-capture starts: in the accepted
  EX06 series, three sub-games were decided in one round because the derivation put the cop
  next to the thief. The re-draw is deterministic (both sides walk the same `draw` sequence), and
  termination is guaranteed for n ≥ 2 (opposite corners are always at distance `n-1 ≥ d_min`).
- **`index` (deterministic re-runs):** for sub-game `g`, attempt `a` (first play = 0, first re-run
  after a void = 1, …): `index = g * 16 + a`. No "bump by agreement" — re-runs re-derive with zero
  negotiation.

### 6.5 Report hash

`report_hash = SHA-256(canonical report bytes)` — the subject of the two-phase confirm (§9). The
report schema itself is fixed by the assignment (see §11); the canonicalization is §2, no `version`
key inside the hashed body.

## 7. Disclosure modes

### Mode A — full disclosure + commit audit (EX06-proven, default)

Every ply carries cleartext `move` plus `commit` + `nonce`. Both engines apply the move and stay in
lockstep; the commitment is a per-ply integrity/audit trail. Capture (`cop == thief`) and the round
cap are derived independently and identically by both engines — never declared.

### Mode B — delayed reveal (PROPOSED — the "scent" candidate; not yet playable)

For rules with genuine hidden positions (the final project's scent mechanic), keep the peer topology
by revealing on a lag `k` (match-card `scent_k`):

- At ply `t` the mover sends `commit` for its current position, `move: null`, and
  `reveal = {ply: t-k, pos, nonce}` — the verified position it committed `k` plies ago.
- The receiver verifies the reveal against the stored ply-`t-k` commitment; the lagged trail **is**
  the scent (older = staler). Freshness/decay presentation is an engine concern, not a wire concern.
- End-of-game: both sides reveal all outstanding nonces so the full trajectory is auditable and the
  result (capture claims included) is verifiable before settlement.
- Open design point for v1.0: how capture is *detected* when current positions are hidden (options:
  cop declares a capture claim that thief must answer with a reveal; or capture checks run on the
  lagged trail). **Blocked on the official rules.** Until v1.0 unblocks Mode B, match cards MUST
  NOT set `disclosure: "B"`, and implementations MUST reject cards that do.

## 8. Turn loop, sequencing, failure

### 8.1 Per-ply loop (mover's client)

1. Poll own inbox → take the opponent's latest block (per §5.2 sequencing rules).
2. Verify: `game`/`ply` in sequence → commitment (and reveal, Mode B) → apply to local engine →
   recompute `state_hash` and compare with the block's `state`.
3. Decide own move (LLM + policy). Build commit/nonce; apply locally; compute new `state`.
4. Compose prose + trailer; `deliver_message` to the opponent. Wait (poll) for their reply.

### 8.2 Timeouts, budgets, resends (defaults; match card may override)

- `per_ply_seconds` (default 120): max wait for the opponent's next valid block. **Sender resend
  rule:** if no valid response block arrives within `per_ply_seconds / 2`, resend your last message
  with the **byte-identical** trailer (receivers dedupe by `commit`; the `prev` chain is unaffected).
  Never construct a *different* trailer for the same ply.
- `per_subgame_seconds` (default 1800) and `max_messages` (default 200, **per sub-game**): livelock
  guards.
- All timers run on the **waiter's local clock** (no cross-machine clock agreement is needed
  anywhere in this protocol; `scheduled_utc` is coordination metadata only, §4.1).
- While waiting, a client MUST bound its own reads and keep checking the wall clock — a silent
  opponent becomes a timeout, never an infinite hang.

### 8.3 Desync and voiding

- Commitment/reveal verification failure, out-of-sequence block that never resolves, `state`
  mismatch, or budget exhaustion → the sub-game is **void** (technical loss handling): record
  evidence (ply, both state hashes, the offending block, your `prev`-chained transcript), notify
  the opponent in prose, **re-run** the sub-game — same `game` index `g`, next attempt `a`, starts
  re-derived deterministically via `index = g * 16 + a` (§6.4).
- Repeated failure of the same sub-game (default: 2 attempts) → humans decide; the series is not
  reportable as mutually agreed until resolved.

## 9. Series settlement — identical reports or nothing

1. After the last sub-game, each side independently builds the report from its own log. Totals and
   bonus/points claims MUST be **derived** from per-sub-game results by the scoring table — never
   hand-declared — so agreement on sub-games implies agreement on totals.
2. Canonicalize (§2) → `report_hash` (§6.5).
3. **Two-phase confirm** (EX06-proven mechanism, now a typed trailer): send a message to the
   opponent's cop mailbox whose trailer is
   `{"v":1,"type":"report_sha","match_id":"<id>","sha":"<hex64>"}`; poll for theirs. Email is sent
   **only** on byte-identical match, by both teams — to the `report_email` from the match card,
   subject to the `stage` interlock (§4.1).
4. On mismatch (PROPOSED escalation, replaces "humans stare at JSONs"):
   a. Exchange full canonical report bytes.
   b. Machine-diff; classify the first diverging field.
   c. Sub-game result divergence → that sub-game is void → re-run it (§8.3) → rebuild → re-confirm.
   d. Metadata divergence (names, ordering) → fix to the match card's `agreement` values →
      re-confirm.
   e. Nothing is ever emailed without a confirmed match (mismatched reports score 0 for both).
5. Both teams SHOULD commit their per-ply JSONL transcript (with the `prev` chain) alongside the
   emailed report — the chain makes each side's log self-authenticating evidence that the game
   actually happened as reported.

## 10. Conformance

A team is **league-conformant** when:

1. **Vectors pass** — its implementation reproduces every fixture in `vectors/`
   (`python verify_vectors.py` checks the fixtures against the reference constructions; port the
   checks into your own test suite against *your* implementation). This includes the **negative**
   vectors: your canonicalizer must *reject* the float cases.
2. **Wire discipline** — trailers constructed programmatically, parsed without LLM involvement;
   prose interpreted by LLM only; hold-don't-advance on unexpected input (§5.2).
3. **Handshake discipline** — refuses to start on protocol/config hash mismatch.
4. **Settlement discipline** — derived totals; never emails without a confirmed `report_sha` match;
   respects the `stage` interlock.

This repo's CI regenerates all vectors and the worked example on every push and fails on any drift.
Planned for v1.0: a record-replay reference transcript (drive your client against a recorded
conformant opponent, offline) and a public **sparring server** any team can play against at will.

## 11. Open questions — v1.0 blockers (await the official assignment PDF)

| # | Question | Impacts |
|---|---|---|
| 1 | Exact scent mechanic (what is observed, decay, who computes it) | §7 Mode B vs. a different observability model |
| 2 | Board size / rounds / scoring table / barrier rules | match card values, §6.4 `n`, report math |
| 3 | Official report JSON schema + destination email | §6.5, §9 |
| 4 | Does the assignment text constrain shared league services? | scope of Appendix B — the lecturer's general stance is that anything not explicitly specified is open to teams' own interpretation, so Appendix B assumes such services are fair game |
| 5 | Tournament structure (round-robin? scheduling windows? exact diminishing-returns formula?) | match card, fixture rounds (Appendix B), sparring server priority |
| 6 | Is the commit-reveal requirement per-ply, per-game, or both? | §6.2/§7 |

## Appendix A — provenance

The constructions in §2, §3, §5 (as a pipe-delimited precursor), §6.2/§6.3/§6.5, and §9 were
implemented independently by two teams in EX06 (course 203.3763, University of Haifa), played live
over Cloudflare tunnels, and settled with a byte-identical report hash confirmed by both sides
before emailing. The trailer format (§5), match card (§4.1), joint seed (§4.2), sequencing fields,
and mismatch escalation (§9 step 4) are draft improvements distilled from that experience — each
replaces a step that previously required live human debugging. The v0.2 revision incorporates the
EX06 post-mortem review contributed by the partner team (issue #1).

## Appendix B — league services (PROPOSED, non-normative)

The protocol above requires **no central party** — any two conformant teams can play peer-to-peer
with nothing but a match card. The services below are optional league infrastructure that make a
6–8-team season smoother. They are deliberately **passive**: none of them executes game logic, so
the peer topology and the trust model (§1) are unchanged, and an outage of any service never blocks
a match (fallback: direct peer play with a manually exchanged match card).

- **Lobby / registry.** Recommended implementation: a **league GitHub repository**, not a hosted
  service. The roster is one JSON file per team (group name, repo, MCP URLs, contact), maintained
  by PR; each scheduled match gets an Issue carrying its match card (§4.1); at settlement both
  teams post their report hash and links to their committed transcripts as comments; `transport`
  updates (fresh tunnel URLs) are posted as comments too. That yields registration, scheduling,
  notifications, and a public timestamped coordination trail with zero hosting and no single owner
  — and it degrades gracefully: any match can still run from a hand-exchanged match card. The
  lobby never holds bearer tokens — those stay pairwise and out of band. If the official scoring
  turns out to be order-dependent (class remarks hinted at diminishing returns per game played,
  coupled to how many games the *opponent* has played), the fixture table should run
  **synchronized rounds**, football-league style: a deterministic round-robin (circle method over
  the sorted roster) where in round `r` every team plays its `r`-th series — so no pairing is
  advantaged by scheduling luck, and the schedule is derivable by anyone from the roster alone.
- **Notary / witness (optional, deferred).** An append-only log where both sides of a live match
  POST each ply's `{match_id, game, ply, state}` hash as they play. Since both peers post
  independently, a desync is detected the moment two entries for the same ply disagree — with
  neutral, timestamped evidence of exactly where the divergence began. Verification-only; it never
  computes game state. Unlike the lobby this needs a real hosted service (an Issue thread cannot
  take per-ply traffic), and it is the most optional item here: the peers' own `state` comparison
  (§6.3) already detects desync instantly, the `prev` chain (§5.2) makes committed transcripts
  self-authenticating, and the void/re-run rules (§8.3) resolve disputes without third-party
  evidence — so this exists only if the league decides it wants live witnessing.
- **Sparring server.** An always-on conformant opponent any team can play against at will, for
  integration testing without needing a partner team online (the single biggest testing gap in
  EX06). We (ImreEyal) intend to host the first one once v1.0 exists.
- **Demo league + report sink.** Before the official season, run one or two full fixture rounds as
  a dress rehearsal: real servers, real tokens, real games, real settlement — identical to the real
  thing except `stage: "demo"` routes reports to a league test mailbox instead of the lecturer.
  The sink can run an automated checker on arriving mail (schema validation + byte-identity of the
  two teams' reports) and publish pass/fail per match, so every team's **full** pipeline — the
  email leg included — is certified before the first game that counts. Nothing reaches the
  lecturer's address until every team jointly declares the official season open. With
  order-dependent scoring this matters doubly: your first *counted* game should never be your
  first game ever.

Hosting model: any team can run any service; nothing about them is privileged. If the league wants
them, their APIs get specified in v1.0.

## Appendix C — transport field notes (non-normative, contributed)

Operational experience from the EX06 live runs (contributed by anrbj666 in issue #1; ours matched
where we tried the same things). Not protocol — just hours saved:

- **ngrok free tier is unfit for match traffic:** ~20 connections/min cap trips mid-sub-game; idle
  streams get dropped; a single free domain round-robining both cop and thief traffic confuses
  clients. Fine for a smoke test, not for a series.
- **Cloudflare quick tunnels** (`cloudflared tunnel --url`) worked for full EX06 series but the
  URL changes on every restart — with the v0.2 `agreement`/`transport` split this no longer breaks
  the handshake; just re-announce the new URL (lobby Issue comment or hello prose).
- **A named Cloudflare tunnel** (free, needs an account) keeps a stable hostname across restarts —
  the proven low-effort setup for a scheduled season. Path-route one hostname to both local
  servers (`/cop/mcp`, `/thief/mcp`) and keep the tunnel process persistent.
- Free-tier PaaS (Render et al.) sleeps on idle — wake both sides *before* `scheduled_utc`, and
  remember the co-location constraint: the key-holding orchestrator must sit next to its mailbox
  server, so a PaaS mailbox alone cannot host your side of a live match.
