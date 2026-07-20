# Cop–Thief League Interop Kit — for the official book v3.0.0

**Status:** aligned to the official assignment — *Distributed Cops-and-Robbers over a Peer-to-Peer
Network*, Dr. Yoram Reuven Segal, **book v3.0.0 / code v3.0.0** (University of Haifa, Orchestration
of AI Agents). This document tracks that release; if the book revises, this follows.

**This is not the game spec — the book is.** The book fixes the transport (MCP/FastMCP), the game
(hidden positions, the pheromone scent, capture, scoring), the commit-reveal, the `config/game.json`
constitution, and the Gmail-API reporting. What this kit adds is the one thing the book does not
ship: **conformance test vectors** for the byte-level constructions two independent implementations
must agree on. Plus a small set of clearly-marked **opt-in enhancements** (Appendix A) a pair of
teams may agree to and sign into their config.

**Why it matters (the one-line version):** the book says "hash the canonical JSON," but two
clean-room codebases that serialize even slightly differently — an escaped `א` vs a native
`א`, a `0.1` vs `0.10000000000000001` — will fail each other's audit, and both score a **technical
loss**. This kit lets you certify, alone and before match day, that your bytes match everyone
else's. Pass `python verify_vectors.py`, port the checks into your own suite, and you can finish a
clean game with any team that did the same.

---

## 0. Relationship to the book

The book is authoritative and self-contained. This kit only *pins bytes* and *proposes optional
extras*. Pointers into the release (chapter numbers are v3.0.0):

| The book fixes… | …so this kit does not restate it |
|---|---|
| MCP tool-call transport over FastMCP + tunneling (ch.2) | — |
| Hidden positions / Zero-Knowledge "local truth" (ch.1, ch.5) | — |
| Stigmergy scent field: emission + decay (ch.4) | pins the math with vectors (§5) |
| Commit-reveal SHA-256, per-step, revealed at audit (ch.5) | pins the serialization with vectors (§3) |
| Strategy is pure code; the LLM only writes the free-language hint (ch.6) | — |
| Fixed scoring + diversity + computational fairness (ch.9, App. F) | — |
| `config/game.json` as the signed shared "constitution" (ch.3, App. B) | pins the signature/id bytes (§4) |
| Gmail-API reporting, both teams send identical JSON (ch.9, App. A) | pins report canonicalization + the emailed-bytes rule (§6) |
| Two GitHub repos + academic README (ch.9, App. C) | — |

Nothing here weakens a mandatory rule. Per the book's own principle ("anything not explicitly
written is open to agreement, but the parameter-table minimums may only be raised, never lowered"),
this kit lives entirely in the "open to agreement" space and in self-certification.

## 1. The interop surface

These are the only places where two independent implementations must produce **byte-identical**
output, or the game cannot start / audit / settle. Each is backed by a vector:

1. **Canonical JSON** (§2) — the serialization under every hash. `vectors/canonical_json.json`.
2. **Commit-reveal** (§3) — your revealed log is re-hashed by the *opponent* at audit.
   `vectors/commit_reveal.json`.
3. **Agreement signature** (§4) — the pre-game gate; a byte difference means the peers refuse to
   play. `vectors/terms_signature.json`.
4. **`game_uid`** (§4) — both peers derive the same shared id with no round-trip.
   `vectors/game_uid.json`.
5. **Pheromone field** (§5) — each peer emits its own, but a wrong port breaks your belief map.
   `vectors/pheromone.json`.
6. **Report canonicalization + consensus signature** (§6) — both teams must email byte-identical
   report JSON, and the consensus signature inside it uses a **second (spaced) serialization**.
   `vectors/report_consensus.json`.
7. **Locked-model declarations** (§7) — where the signed terms cannot carry a choice, a pair
   declares the hash of a described model. The doc schema must match or the hashes are not
   comparable. `vectors/locked_model.json`.

Everything else (your strategy, your GUI, your prompts, your infra) is private and needs no
cross-team agreement.

## 2. Canonical JSON

Every hash in the protocol is `SHA-256` over the UTF-8 bytes of:

```python
json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
```

Three details are load-bearing, and each is where a clean-room port silently diverges:

- **`ensure_ascii=False` (native UTF-8).** Non-ASCII — Hebrew hints, emoji, non-English map areas —
  is emitted as raw UTF-8, **not** `\uXXXX`-escaped. This is the single most important fact in the
  kit, because of §3: the opponent re-hashes your revealed `hint` text at audit. Escape it and every
  non-ASCII step fails, costing both sides the match. `vectors/canonical_json.json` pins a Hebrew
  string and an astral-plane emoji.
- **Floats are permitted, and must be shortest round-trip repr.** The protocol carries floats
  (`decay_per_step: 0.1`, `emit_intensity: 0.9`, hardware `ram_gb: 31.8`). Python's `json` emits
  the shortest round-trip form (`0.1`, not `0.10000000000000001`); any conforming implementation
  must do the same, or the terms signature (§4) fails. The kit does **not** forbid floats (an
  earlier draft did — that was wrong for this game). It pins the expected canonical strings so you
  can check your language.
- **Sorted keys, no whitespace** (`separators=(",", ":")`). Construction order in your code is
  irrelevant; canonicalization sorts.

Reference: `verify_vectors.py:_canonical_str`.

## 3. Commit-reveal conformance

Each step, a peer seals its own turn record and sends **only** the commit; nonces are revealed at
the end-of-game audit, where both peers re-hash every revealed record. The construction:

```
commit = SHA256( canonical_json(payload) + "|" + nonce )
```

Note the nonce is **pipe-appended to the canonical string**, not placed inside the hashed object.
`vectors/commit_reveal.json`.

> **A contradiction in the book, resolved here** (documented per the book's own academic-freedom
> clause, which requires naming the contradiction and the choice). The v3.0.0 release publishes
> three inconsistent commit constructions: the ch.5 listing seals the nonce **inside** the
> canonical JSON object; the audit-chapter snippet re-hashes `f"{nonce}|{move}"`; and the official
> reference implementation (`domain/crypto.py`) computes `SHA256(canonical(payload)|nonce)`. The
> book's clarification page makes printed listings illustrative and non-binding, and the
> binding-rules layer mandates the *mechanism* (commit-reveal over SHA-256 per step), not the
> preimage — so the choice is formally open. But it is an **interop constraint**: the opponent's
> audit re-hashes your revealed records, so both sides must use the same form or the audit voids
> the match. This kit pins the **reference form** — it is what the lecturer's own tooling runs and
> what most teams will build against. It is also the only one of the three that is
> cryptographically sufficient: the audit-snippet form consumes only `nonce` and `move`, so it
> binds neither `state` nor `intent` — a record's position or bluff verdict could be rewritten
> after the fact without changing that hash. If your commits don't verify, the `divergent_forms`
> entry in `vectors/commit_reveal.json` hashes the same sealed record under all three
> constructions (the audit-snippet form, by its nature, over just the record's `nonce` and
> `move`), so you can identify which one you implemented. A pair that knowingly prefers a
> different form must sign it into `config/game.json` and document it.

- **Self-verify** needs no cross-team agreement — you re-hash your own payloads. **Audit is
  cross-team**: your opponent runs `verify(payload, nonce, commit)` over *your* revealed records,
  canonicalizing them with *their* serializer. If your serializers disagree on any record — and
  records contain your free-language `hint`, which may be Hebrew — their recompute misses your
  commit, the audit flags it as tampering, and the sub-game is a technical loss for both. §2's
  `ensure_ascii=False` is what prevents this.
- **The payload schema itself is not an interop constraint.** Each peer reveals its own full record
  and the other just re-hashes it; you do not reconstruct your opponent's payload. So the exact key
  set (the book's core `{state, move, intent, nonce}` vs. the reference's richer record that also
  carries `verdict`, `hint`, `step`, `sub_game`, `role`, timing, tokens) does not need to match
  across teams — only each side's own seal↔reveal must be self-consistent, and your canonical form
  must be §2. Order enforcement and replay resistance come from `step` (and `sub_game`, `role`)
  being inside the signed payload, not from any transcript chain.
- **`state` is a string, self-only.** The reference encodes it as
  `f"grid={n}x{n};self={[row, col]};barriers={sorted_barriers}"` (Python list repr, note the space
  after the comma). It carries *your own* position only — never the opponent's (hidden-position
  model) — so there is no shared board frame both sides must reproduce.

## 4. Agreement signature and `game_uid`

Before play, each peer signs the agreed terms and both derive a shared id — the pre-game gate that
refuses to start on any mismatch.

- **Signature** = the §3 construction over the terms: `SHA256(canonical_json(terms)|nonce)`. Each
  peer signs the terms with its own nonce; the opponent re-verifies over the terms it received
  (which must value-equal its own) using the signer's nonce. `vectors/terms_signature.json`. The
  `terms` are the subset of `config/game.json` both sides must match on (board, scent params,
  scoring bounds, starts, step cap, setting, axes) — the book's App. F table; the exact extraction
  is the reference's `terms_from_config`.
- **`game_uid`** = `UUID( SHA256( canonical(terms) + "|" + "|".join(sorted([g_a, g_b])) )[:16] )`,
  identical for both peers because it is a pure function of shared inputs (sorted group ids →
  order-independent). `vectors/game_uid.json`. It names the four submission artifacts —
  `declaration_<game_id>.json`, `config_<game_id>_g<NN>.json`, `log_<game_id>_g<NN>.json`,
  `result_<game_id>.json` (the per-mini-game files carry the `_g<NN>` suffix, per the book's
  App F files table and the reference's own `docs/sample-run/`) — keeping files from different
  matches from ever mixing.

## 5. Pheromone field

The scent (book ch.4) is each peer's own emission, transmitted as `{"r,c": intensity}` and absorbed
by the opponent — so it is not re-derived cross-team. But a wrong port makes your belief map behave
unlike the book's, so the kit pins the math as a self-test. `vectors/pheromone.json`.

- **Radial emission** around a cell: `half = grid_size // 2`, `falloff = intensity / (half + 1)`,
  and each in-bounds cell gets `round(max(0, intensity - falloff * chebyshev(cell, center)), 3)`.
  Only cells with value > 0 cross the wire. On the default `grid_size=5`, centre `0.9`, falloff is
  `0.3` per Chebyshev ring (`0.9 → 0.6 → 0.3`).
- **Decay per game-step**: every known intensity drops by the constant, clamped at 0 and rounded to
  3 places: `round(max(0, v - decay), 3)`.
- **Emission requires the centre to meet `min_center_intensity`** (default `0.5`); the field is
  merged into the trail by max, and decays each step, producing the fading trail the book's
  heatmap visualizes.

> **Book-vs-reference divergence, documented:** the book's ch.4 prose gives *multiplicative* decay
> (`τ ← max(0, (1−ρ)·τ + Δτ)`, ρ = 0.10) and its emission figure traces a smooth (Gaussian-like)
> radial surface; the reference implements **subtractive** decay (`v − decay`, clamped, rounded)
> and **linear** Chebyshev falloff. Both are now **named registrations** (§7) rather than one
> pinned form and one footnote: this section is `subtractive_chebyshev_v1`, the book's model is
> `multiplicative_book_v1` (§5.1). Unlike §3 this cannot void a game *under this section's wire*
> — scent maps are transmitted, not re-derived cross-team — but the two produce visibly different
> trails, so a pair that wants the book's physics locks it explicitly and both sides declare it.

### 5.1 `multiplicative_book_v1` — the book's own model (PROMOTED)

The book's ch.4 model, registered as a named alternative. `vectors/scent_book_v3.json`. Status is
**PROMOTED** (2026-07-20): the kit's bar — a second independent implementation reproducing the
fixtures — was met by **anrbj666**'s clean-room reproduction (issue #6): byte-exact on the kernel,
both emit cases, all three walk turns, both scalar traces, and every ordering-probe case with
zero tolerance, from an implementation built from the book alone, predating these vectors. The spec facts were
contributed by **anrbj666 (Alon Engel, Renat Karimov)**, whose implementation follows the book
rather than the reference; every value in the fixture is re-derived here from book v3.0.0 ch.4 and
the App. F binding table.

- **Update**, once per cell per **full turn** — after *both* agents have moved, which is the book's
  own cadence (ch.4: the systemic decay runs "at the end of every full turn"), not once per
  half-turn step:
  `τ′ = clamp((1 − ρ)·τ + Δτ, 0, center_intensity)`, with ρ = 0.10 and `center_intensity` = 0.9.
- **`Δτ` is a verbatim 5×5 lookup** — the printed figure-4 kernel, centre `0.90`, orthogonal `0.62`,
  diagonal `0.42`, then `0.20 / 0.14 / 0.04`. See the note below on why it is not a formula.
- **The upper clamp is not in the printed formula.** The book prints only `max(0, ·)`, but also
  declares τ to be a continuous value in `[0, 0.9]`; without the upper bound a saturated cell that
  decays and is deposited on again reaches `0.9·0.9 + 0.62 = 1.43`, outside the book's own range.
  The fixture pins that case.
- **No rounding**, an empty starting field, decay-then-deposit within the single expression, and
  **no receiver-side pass** — each side recomputes the rival's field from revealed actions rather
  than receiving it. The reference model differs on every one of those four: it rounds to 3 places,
  deposits before decaying, and decays a received copy on receipt.
- **App. F fixes all three parameters** (`קבוע`): centre intensity `0.9`, decay rate `0.10`, field
  size `5×5`. So what a scent registration selects is the *model form*, never the numbers — a doc
  that alters one of those three is refused by the binding table, not by the lock.

> **Why the kernel is pinned verbatim, and an open question settled.** Figure 4 *is* an exact radial
> Gaussian at printed precision — but only for σ² inside a narrow window the book never prints, and
> the window that reproduces the table under round-to-2dp (`[1.3178, 1.3327]`) is **disjoint** from
> the one that works under truncation (`[1.3436, 1.3538]`). Two teams that each "use a Gaussian"
> in good faith can therefore produce different fields, silently. The 25 printed values are the only
> thing both can reach, so the kit pins them and treats the closed form as commentary.
> `closed_form_probe` in the fixture carries both quantizations and both windows. (This reconciles
> a genuine disagreement between the two teams building this registration: anrbj666 read the figure
> as an exact Gaussian and were right about the shape; we read it as matching no clean formula and
> were right about the reproducibility. The pinning follows from theirs *and* ours.)

> **Evaluation order is load-bearing here in a way it is not elsewhere in the kit.** Because this
> model rounds nothing *and* each side recomputes the other's field instead of receiving it, two
> implementations that agree on every parameter can still disagree in the last bit: `(1−ρ)·τ + Δτ`
> and `τ − ρ·τ + Δτ` are the same algebra and different IEEE-754 doubles (75 of 534 probed inputs).
> A byte-comparison of two recomputed fields will then false-flag. Pin the order as written, or
> compare fields with a tolerance — `ordering_probe` in the fixture shows the divergence.

## 6. Report canonicalization and settlement

Both teams independently build the final result JSON, and both email it — the grader compares the
**emails**, not just the hashes. Two rules carry over from EX06 and cost real points when ignored:

- **The emailed body must be the exact canonical bytes** (§2) — never a pretty-printed
  re-serialization. In EX06 two teams' report hashes matched but one team's *email* was a
  re-serialization, and it nearly scored 0.
- **Derived, not declared.** Totals and the diversity flag are derived from the per-sub-game
  results and the game-count declarations by the fixed scoring table (book ch.9), so agreement on
  sub-games implies agreement on totals.
- **Stage / draft interlock.** The reference's `email.mode = "draft"` is the safety gate: nothing
  reaches the lecturer's real inbox until intended. Under the diversity rule (only the *first*
  meeting with an opponent counts), an accidental early real send can burn your one counted game —
  so keep drafts until a deliberate human send.

> **The consensus signature uses a second canonical form** (found by Alon's team —
> alonengel / anrbj666 — and verified against the reference at sha `960499fd`,
> `report_writer.py`). `consensus_signature` serializes with `sort_keys=True,
> ensure_ascii=False` and **default (spaced) separators** — unlike every other hash in the
> release, which uses the compact §2 form. And the signature is computed over the report
> **before** the `חתימת_קונסנזוס_משותפת` key is inserted (sign-then-insert), so the field is
> excluded from its own preimage; verification = pop the signature key, re-serialize spaced,
> re-hash. Two teams that disagree on either detail fail settlement at the exact moment they
> must agree on the result. `vectors/report_consensus.json` pins both details and includes a
> compact-form contrast hash. Counting the three commit constructions (§3), this is the
> release's fourth serialization variant — pinned as-is because it is what the lecturer's own
> tooling computes.

## 7. Locked-model declarations

The book leaves several choices to inter-team agreement but freezes the signed terms as a flat
14-key set — so a pair cannot record a choice by adding a key to `config/game.json` without
breaking the terms signature (§4). Teams have independently converged on the same workaround:
publish a description of the choice, hash it, and declare **only the hash** in the negotiate
extras. This section pins the document underneath that hash. `vectors/locked_model.json`.

**Without a pinned schema the mechanism backfires.** A bare hash over an ad-hoc dict means two
teams that implement the *same* model from the *same* spec still declare different hashes — they
serialized different field sets — and refuse each other for no reason at all. The hash is only as
useful as the agreement on what goes into it.

**One schema, three families.** A locked-model doc has exactly four keys:

```json
{"family": "scent_model", "name": "multiplicative_book_v1", "params": {...}, "example": {...}}
```

`family` ∈ `scent_model` | `wire_shape` | `info_mode`; `name` is the registered name; `params`
carries the model-specific values; `example` carries a worked case. Everything variable lives in
the last two, so the envelope never changes as families are added.

- **Hash:** `sha256(canonical_json(doc))` — the compact §2 form, the same construction anrbj666's
  team already ships for `scent_model_sha256`. Adopting the schema changes the *bytes hashed*,
  not the mechanism.
- **Declaration:** the doc never crosses the wire; only `"<family>_sha256"` does, in the negotiate
  extras. The kit registers six docs: two scent models (§5, §5.1), two wire shapes, two info modes.
- **Refusal rule: refuse only when BOTH peers declare a family and the hashes differ.** Omission is
  never refusal — in either direction. A lock that fail-fasts on a *missing* declaration cannot
  start a game against the unmodified reference peer, which declares nothing at all; that is a
  self-inflicted forfeit, not a safeguard. The fixture pins the rule as a five-row truth table
  because it is behaviour, not bytes, and it is the part implementations get wrong.
- **A declaration binds a choice; it does not widen what may be chosen.** App. F's fixed values and
  minimums are unaffected — a doc that lowers a minimum is refused by the binding table regardless
  of what the peers agreed.

**`info_mode` needs one honest annotation.** The mode (`belief` — the rival's position is outside
the observation space — versus `exact`) is a negotiated term like the others, but its enforceability
is asymmetric, and the registration says so. A **mismatch** is provable from the two negotiate
records. A **violation** — a brain consuming exact positions while declaring `belief` — is *not*
provable from any artifact, because a decision record does not disclose which information produced
it. Under wire shape `reference-v3` the belief mode is enforced **structurally**, since the rival's
position never crosses the wire; under `bookletter-v3`, which puts it on the wire, the same words
are an **honor term**. Declaring the mode is still worth doing — it makes the intent explicit and a
mismatch catchable before the game — but a pair should know which of the two it is relying on.

> **Status.** The scent registrations are backed by fixtures (§5 CORE, §5.1 PROMOTED 2026-07-20). The wire
> shapes are registered per issue #6 with **asymmetric status**: `reference-v3` matches the
> reference implementation and the book's Dec-POMDP observation space; `bookletter-v3` is a
> **documented deviation** from the book's formal model that a pair may lock by explicit mutual
> sign-off. Its commit layer reproduces under §3 over the full 7-field payload, but four preimages
> — `state_digest`, `end_state_digest`, `config_sha256`, and whether a signed 14-key
> `terms_signature` accompanies it — are not yet pinned, so its `params` record them as
> `unpinned_preimages` and its hash will change when they are settled. That is the intended
> behaviour: a lock should not claim to bind what it does not.

## 8. Conformance

A team is **interop-ready** when:

1. **Core vectors pass** — `python verify_vectors.py` reproduces every `[CORE]` fixture, and your
   own implementation reproduces them too (port the checks into your suite): canonical JSON with
   `ensure_ascii=False`, the commit construction, the terms signature, `game_uid`, the pheromone
   math, and — if you declare any locked model — the doc schema and the refusal rule.
2. **Cross-team audit is clean** — feed your opponent's revealed log to your verifier and your log
   to theirs; both audits pass with zero `tamper_forfeit`. This is the real test §1 exists for.
3. **Report bytes match** — the emailed body equals the canonical bytes that were hashed.

The `[ENH]` vectors (Appendix A) are separate: a pair conforms to an enhancement only if both
opted in and signed it into `config/game.json`. `[PROPOSED]` fixtures (§5.1) are a third tier —
published so a second implementation can reproduce them, and promoted only once one has.

CI regenerates all vectors and the worked example on every push and fails on any drift.

## Appendix A — agreed enhancements (opt-in, not required by the book)

The book's default rule is "no rule unless written," and it invites teams to agree on extras and to
exploit undefined gaps — provided the agreement is signed into `config/game.json` and does not
weaken any mandatory minimum. These are ours; a pair uses one only if both sign it in.

- **Transcript interlock DAG (`prev` / `prev_recv`).** The book's commits are independent per step —
  strong against *editing* one step, but a full log can be re-forged offline (there is no
  cross-link). Optionally add to each sealed record `prev` = SHA-256 of your previous sent record's
  exact bytes and `prev_recv` = SHA-256 of the last opponent record you accepted. The two logs
  interlock into one DAG: a re-forged history contradicts the opponent's later records that
  acknowledged it, so earliest divergence is provable from the two committed logs. Requires storing
  verbatim record bytes. (Design credit: anrbj666, issue #1.)
- **Seeded asymmetric starts + joint-seed coin flip.** The book fixes `cop_start`/`thief_start` in
  the config. A pair that prefers randomized-but-fair starts can instead derive them from a joint
  seed generated by commit-reveal so neither side picks a favorable one:
  `share_commit = SHA256(canonical({"seed_share": r}))`, reveal, `seed = SHA256(canonical({"shares":
  [r1, r2]}))`; then `derive_starts(seed, index=game*16+attempt, n)` with a minimum-Chebyshev
  distance (no instant captures) and a deterministic re-draw. `vectors/joint_seed.json`,
  `vectors/derive_starts.json`.
- **Synchronized fixture scheduling.** The league is self-organized (book ch.9), and only the first
  meeting with each opponent counts. To keep scheduling luck out of it, a group of teams can agree a
  deterministic round-robin (circle method over the sorted roster) so round `r` fixes everyone's
  `r`-th opponent, derivable by anyone from the roster.
- **Demo staging beyond `draft`.** Run one or two full fixture rounds as a dress rehearsal with
  reports routed to a league test mailbox (schema + byte-identity auto-checked) before anyone's
  first counted game. Complements the reference's `email.mode = "draft"`.

## Appendix B — league services (optional, passive)

None of these run game logic, so the peer topology and trust model are unchanged and any outage
falls back to direct peer play.

- **Sparring server.** An always-on conformant opponent any team can test against without needing a
  partner online — the biggest testing gap in EX06, and the league's adoption engine. We (ImreEyal)
  intend to host one.
- **Lobby via a league GitHub repo.** Roster as one JSON file per team (maintained by PR); each
  scheduled match gets an Issue carrying its `config/game.json` and, at settlement, both teams'
  report hashes and links to their committed artifacts. Registration + scheduling + a public
  coordination trail, zero hosting, no single owner, graceful fallback to a hand-exchanged config.

## Appendix C — provenance, and the relationship to the book

This kit was born (as a full protocol draft, v0.1–v0.3) from the EX06 inter-group bonus, where two
independent implementations played live over Cloudflare tunnels and settled on a byte-identical
report hash. Issue #1 (partner team anrbj666) contributed two review passes, including the
transcript-DAG idea now in Appendix A. When the official book v3.0.0 published, the game's actual
rules and transport were fixed by the book, so this repo re-scoped from "a candidate standard" to
"a conformance kit + agreed-enhancements layer on top of the book."

The constructions here were confirmed byte-for-byte against the official reference implementation
(`github.com/rmisegal/Game-P2P-Cop-Chase`, code v3.0.0): the canonical form, the
`SHA256(canonical|nonce)` commit, the terms signature, the `game_uid` derivation, and the pheromone
math. The book (© Dr. Segal) and the reference code (Educational-Use-only) are cited and linked,
never copied — every vector in this repo is generated from our own synthetic inputs by
`gen_vectors.py`. Hash outputs are facts; the algorithms are the book's; the words here are ours.

## Appendix D — deployment notes (observed in live cross-implementation runs)

- **fastmcp peers return HTTP 421 behind tunnels unless the tunnel rewrites the Host header**
  (issue #4). The MCP streamable-HTTP server's DNS-rebinding protection rejects requests whose
  `Host` is not the bind address — which is every request arriving through a tunnel. Fix at the
  tunnel, no code changes: Cloudflare named tunnel → `originRequest.httpHostHeader:
  127.0.0.1:<port>`; ngrok → `--host-header=rewrite`. Verified by full mini-games against the
  unmodified reference peer over public URLs in both role pairings (mutual audits Verified OK).
  Pre-match checklist probe: "does your public URL answer a tool call?" catches it in seconds.
