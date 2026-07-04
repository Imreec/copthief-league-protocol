# Cop–Thief League Protocol — SPEC v0.1-draft

**Status:** DRAFT for league review — written *before* the official final-project assignment
publishes. Everything here is either (a) battle-tested in the EX06 inter-group bonus (played live,
hash-confirmed byte-identical between two independent implementations), or (b) explicitly marked
**PROPOSED**. Version **1.0** will be cut only after the official assignment PDF drops; §11 lists
what it must resolve.

**Goal:** let any two conforming teams play a full cross-team series — connection, game, result
agreement, identical report emails — with **zero pairwise negotiation**. Conformance is self-serve:
implement to this spec, pass the test vectors in `vectors/`, and you can play anyone who did the same.

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
   protocol. Two implementations that agree on the data agree on the bytes.

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
- Encode the resulting string as **UTF-8** (after escaping it is pure ASCII).
- Numbers: **integers only** — no floats anywhere in hashed objects (float repr differs across
  languages). Booleans/null are JSON literals; strings are JSON-escaped.

Python reference: `json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()`.
Edge-case fixtures (nesting, key order, unicode escaping, empty containers): `vectors/canonical_json.json`.

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

## 4. Match setup

### 4.1 Match card (PROPOSED)

A match is defined by one small JSON document both teams hold byte-identically. Its canonical hash
(§2) is the `config_sha256` checked in the handshake (§4.3).

```json
{
  "protocol": "league/0.1",
  "match_id": "2026-08-01-teamA-vs-teamB",
  "groups": {"group_1": "Team-A", "group_2": "Team-B"},
  "urls": {
    "group_1_cop": "https://...", "group_1_thief": "https://...",
    "group_2_cop": "https://...", "group_2_thief": "https://..."
  },
  "grid": [10, 10],
  "rounds": 25,
  "num_games": 6,
  "swap_at": 3,
  "max_barriers": 0,
  "disclosure": "A",
  "scent_k": null,
  "seed": "<joint seed, §4.2>",
  "scheduled_utc": "2026-08-01T18:00:00Z",
  "timeouts": {"per_ply_seconds": 120, "per_subgame_seconds": 1800, "max_messages": 200}
}
```

Notes: `rounds` counts **rounds** (thief ply + cop ply), so a sub-game is at most `2*rounds` plies.
Role-swap: sub-games `0..swap_at-1` = group_1 cop vs group_2 thief; the rest swap. Game-rule values
(`grid`, `rounds`, scoring) are placeholders until the official assignment fixes them — the *shape*
of the card is what this spec pins. Bearer tokens are exchanged out of band, never in the card.

### 4.2 Joint seed (PROPOSED — trustless coin flip)

Per-sub-game start cells derive from a shared seed (§6.4). So neither team can pick a favorable
seed, generate it jointly by commit-reveal:

1. Each team picks a private random hex string `r` and publishes `canonical_hash({"seed_share": r})`.
2. After both commitments are exchanged, both reveal `r`.
3. `seed = canonical_hash({"shares": [r_group_1, r_group_2]})` (group_1's share first).

Either side can verify the other's share against its commitment. A simpler fallback (used in EX06):
seed = the SHA-256 report hash of a previous agreed game.

### 4.3 Ply-zero handshake

Before any move of sub-game 0, each orchestrator sends one greeting message whose trailer (§5) is:

```json
{"v": 1, "hello": {"protocol": "league/0.1", "config_sha256": "<hex64>", "group": "Team-A"}}
```

- `config_sha256` = canonical hash of the match card.
- If the two sides' `protocol` or `config_sha256` differ, the match **MUST NOT start**. Report the
  mismatch to the humans; nothing is void because nothing began.
- The greeting prose is a natural place to present the bearer token context and confirm readiness
  (in EX06 the token was presented in-conversation; that convention stays legal but tokens should
  already be configured before the handshake).

## 5. In-game wire format

Every in-game message is **one string** passed to `deliver_message`, with two parts:

```
Your scent trail is getting colder toward the north-east, so I'm
sweeping back along the west wall. Committing my move below, and
revealing where I was three plies ago, as agreed.
---LEAGUE-v1---
{"v":1,"game":2,"ply":14,"ack":13,"move":[3,4],"commit":"<hex64>","nonce":"8f2c01ab","reveal":null,"state":"<hex64>"}
```

### 5.1 The prose body (above the fence)

Free natural language — the *actual* agent-to-agent communication (intent, observation, deception,
negotiation). The receiving side interprets it with its LLM. It MUST NOT be required for mechanical
correctness: a conforming implementation can verify and apply the ply from the trailer alone.

### 5.2 The trailer (below the fence)

- Fence line: exactly `---LEAGUE-v1---` on its own line. Everything after the **last** fence line
  must parse as a single JSON object. The sender constructs the trailer **programmatically** and
  appends it verbatim; LLM output MUST NOT be able to alter it.
- Fields:

| Field | Type | Meaning |
|---|---|---|
| `v` | int | trailer schema version (this spec: `1`) |
| `game` | int | 0-based sub-game index in the series (kills cross-game misattribution) |
| `ply` | int | 0-based ply number of **this** move within the sub-game |
| `ack` | int | highest opponent `ply` applied so far; `-1` if none |
| `move` | `[row,col]` \| null | this ply's destination — cleartext in Mode A; `null` in Mode B |
| `commit` | hex64 | `commit(move_pos, nonce)` for this ply (§6.2) |
| `nonce` | string \| null | revealed immediately in Mode A (audit); `null` in Mode B |
| `reveal` | object \| null | Mode B delayed reveal: `{"ply": t-k, "pos": [row,col], "nonce": "..."}` |
| `state` | hex64 | common-state hash **after** applying this ply (§6.3) |

- Unknown fields: receivers MUST ignore unknown keys (forward compatibility within a major `v`).
- Coordinate frame (normative, as in EX06): **0-based, top-left origin, `[row, col]`, row-major**.
- Sequencing: `game`/`ply`/`ack` subsume EX06's `SG:` prefix and hold/skip patch. Plies are
  numbered globally within a sub-game (thief-first ⇒ one role owns the even plies, the other the
  odd), so the opponent's expected next `ply` is always known: their first ply by role, then
  `last_applied_opponent_ply + 2`. A receiver holds a future-`ply` block, discards an
  already-applied one (idempotent by `commit`), and applies only the expected same-`game` block.

## 6. Hash constructions (normative — pinned by `vectors/`)

### 6.1 One rule for all

All constructions are `SHA-256(canonical_bytes(obj))` per §2. The fixtures in `vectors/` are
generated by the EX06 reference implementation that played the live hash-confirmed game.

### 6.2 Position commitment — `vectors/position_commit.json`

`commit(pos, nonce) = sha256_canonical({"nonce": nonce, "pos": [row, col]})`

Binding: changing position **or** nonce changes the hash. Nonce is any string chosen by the mover
(length free; 16–32 hex chars typical). Example: pos `[2,3]`, nonce `"abc123"` →
`3b37bed7b664a8aa96e14072f885fee2cb617bfb57cd42c1fa7430c8d98f2d22`.

### 6.3 Common-state hash — `vectors/state_hash.json`

`state_hash(barriers, turn, move_count) = sha256_canonical({"barriers": sorted [row,col] pairs (deduped), "move_count": N, "turn": "cop"|"thief"})`

- `move_count` = plies completed (0 before the first ply; +1 per ply).
- `turn` = the role **to move next**.
- The sender computes it **after** applying its own ply; the receiver applies the received move to
  its replica, recomputes, compares. Any mismatch = desync (§8.3).

### 6.4 Seed → start cells — `vectors/derive_starts.json`

For sub-game `index` on an `n×n` board:
`digest = SHA-256(f"{seed}:{index}")` (raw bytes); `cop = digest[0] mod n²`; `thief = digest[1] mod n²`;
if equal, `thief = (thief + 1) mod n²`; map `i → [i // n, i mod n]`.

Purpose: per-game asymmetric geometry from a seed neither side controls — this is the proven fix
for structural role-swap ties (EX06 went 75/75 with mirrored corners; decisive with seeded starts).

### 6.5 Report hash

`report_hash = SHA-256(canonical report bytes)` — the subject of the two-phase confirm (§9). The
report schema itself is fixed by the assignment (see §11); the canonicalization is §2, no `version`
key inside the hashed body.

## 7. Disclosure modes

### Mode A — full disclosure + commit audit (EX06-proven, default)

Every ply carries cleartext `move` plus `commit` + `nonce`. Both engines apply the move and stay in
lockstep; the commitment is a per-ply integrity/audit trail. Capture (`cop == thief`) and the round
cap are derived independently and identically by both engines — never declared.

### Mode B — delayed reveal (PROPOSED — the "scent" candidate)

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
  lagged trail). **Blocked on the official rules — do not implement yet.**

## 8. Turn loop, sequencing, failure

### 8.1 Per-ply loop (mover's client)

1. Poll own inbox → take the opponent's latest block (per §5.2 sequencing rules).
2. Verify: `game`/`ply` in sequence → commitment (and reveal, Mode B) → apply to local engine →
   recompute `state_hash` and compare with the block's `state`.
3. Decide own move (LLM + policy). Build commit/nonce; apply locally; compute new `state`.
4. Compose prose + trailer; `deliver_message` to the opponent. Wait (poll) for their reply.

### 8.2 Timeouts and budgets (defaults; match card may override)

- `per_ply_seconds` (default 120): max wait for the opponent's next valid block.
- `per_subgame_seconds` (default 1800) and `max_messages` (default 200): livelock guards.
- While waiting, a client MUST bound its own reads and keep checking the wall clock — a silent
  opponent becomes a timeout, never an infinite hang.

### 8.3 Desync and voiding

- Commitment/reveal verification failure, out-of-sequence block that never resolves, `state`
  mismatch, or budget exhaustion → the sub-game is **void** (technical loss handling): record
  evidence (ply, both state hashes, the offending block), notify the opponent in prose, **re-run**
  the sub-game (fresh sub-game, same `game` index, new starts derivation index MAY be bumped by
  agreement) so the series completes its quota.
- Repeated failure of the same sub-game (default: 2 attempts) → humans decide; the series is not
  reportable as mutually agreed until resolved.

## 9. Series settlement — identical reports or nothing

1. After the last sub-game, each side independently builds the report from its own log. Totals and
   bonus/points claims MUST be **derived** from per-sub-game results by the scoring table — never
   hand-declared — so agreement on sub-games implies agreement on totals.
2. Canonicalize (§2) → `report_hash` (§6.5).
3. **Two-phase confirm** (EX06-proven): send `REPORT_SHA:<hex64>` to the opponent's cop mailbox;
   poll for theirs. Email is sent **only** on byte-identical match, by both teams.
4. On mismatch (PROPOSED escalation, replaces "humans stare at JSONs"):
   a. Exchange full canonical report bytes.
   b. Machine-diff; classify the first diverging field.
   c. Sub-game result divergence → that sub-game is void → re-run it → rebuild → re-confirm.
   d. Metadata divergence (names, URLs, ordering) → fix to the match card's values → re-confirm.
   e. Nothing is ever emailed without a confirmed match (mismatched reports score 0 for both).

## 10. Conformance

A team is **league-conformant** when:

1. **Vectors pass** — its implementation reproduces every fixture in `vectors/`
   (`python verify_vectors.py` checks the fixtures against the reference constructions; port the
   checks into your own test suite against *your* implementation).
2. **Wire discipline** — trailers constructed programmatically, parsed without LLM involvement;
   prose interpreted by LLM only.
3. **Handshake discipline** — refuses to start on protocol/config hash mismatch.
4. **Settlement discipline** — derived totals; never emails without a confirmed `REPORT_SHA` match.

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

The constructions in §2, §3, §5 (as a pipe-delimited precursor), §6, and §9 were implemented
independently by two teams in EX06 (course 203.3763, University of Haifa), played live over
Cloudflare tunnels, and settled with a byte-identical report hash confirmed by both sides before
emailing. The trailer format (§5), match card (§4.1), joint seed (§4.2), sequencing fields, and
mismatch escalation (§9 step 4) are v0.1 improvements distilled from that experience — each replaces a
step that previously required live human debugging.

## Appendix B — league services (PROPOSED, non-normative)

The protocol above requires **no central party** — any two conformant teams can play peer-to-peer
with nothing but a match card. The services below are optional league infrastructure that make a
6–8-team season smoother. They are deliberately **passive**: none of them executes game logic, so
the peer topology and the trust model (§1) are unchanged, and an outage of any service never blocks
a match (fallback: direct peer play with a manually exchanged match card).

- **Lobby / registry.** A small shared service (or even just a repo with JSON files) holding the
  team roster (group name, repo, MCP URLs, contact), issuing match cards (§4.1), and tracking the
  schedule. Kills the "URLs exchanged by hand minutes before the game" failure mode. Never holds
  bearer tokens — those stay pairwise and out of band. If the official scoring turns out to be
  order-dependent (class remarks hinted at diminishing returns per game played, coupled to how many
  games the *opponent* has played), the fixture table should run **synchronized rounds**,
  football-league style: a deterministic round-robin (circle method over the sorted roster) where
  in round `r` every team plays its `r`-th series — so no pairing is advantaged by scheduling luck,
  and the schedule is derivable by anyone from the roster alone.
- **Notary / witness.** An append-only log where both sides of a live match POST each ply's
  `{match_id, game, ply, state}` hash as they play. Since both peers post independently, a desync
  is detected the moment two entries for the same ply disagree — with neutral, timestamped evidence
  of exactly where the divergence began (vs. EX06, where desyncs were diagnosed by two humans
  reading their own logs to each other). Verification-only; it never computes game state.
- **Sparring server.** An always-on conformant opponent any team can play against at will, for
  integration testing without needing a partner team online (the single biggest testing gap in
  EX06). We (ImreEyal) intend to host the first one once v1.0 exists.

Hosting model: any team can run any service; nothing about them is privileged. If the league wants
them, their APIs get specified in v1.0.
