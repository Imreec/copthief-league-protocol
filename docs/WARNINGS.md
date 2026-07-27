# Warnings — the mistakes that cost points, including someone else's

Most of what can go wrong in this game costs you a game. A few things cost **both teams** a game,
including the one that did nothing wrong. Those are first.

Read this before you configure a recipient, and before you name a start time.

---

## 1. A failed series must send **nothing**

> **App. E rule 35** — each team sends its own final report; a missing report from one side, **or
> contradictory reports**, disqualifies the game and scores **0 for both teams**.

Read that sanction twice. It is not "you lose the points you would have won". It is *the opponent
loses theirs too*. So the dangerous instinct after a series that half-worked is the helpful one:
send what you have, note the gap, sort it out afterwards. That is precisely the contradictory
report the rule punishes, and the other team pays for it.

**Build the refusal into the settlement path**, not into your memory:

- **One sub-game that never settled refuses the whole series.** A report that quietly drops a game
  describes a different series from your opponent's report of the same match.
- **An aborted game has no honest summary.** No revealed records means no result; refuse loudly
  rather than writing a hollow entry.
- **Derive, never declare.** Totals come from the per-sub-game results by the fixed scoring table
  (book ch.9), so agreement on the sub-games *is* agreement on the totals. A separately declared
  total is a second source of truth and will eventually disagree with the first.
- **Decide before you start.** A run that owes a report should refuse to *begin* if it could not
  deliver one — an empty recipient or a stale token is cheap to discover before six sub-games and
  expensive after the sixth settles.

**Make the failure legible to whatever runs you.** Distinguish, by exit code, "I refused to report
a series that never settled" from "the report exists but did not reach anyone". They need different
next actions: the first is over, the second still owes an artifact to your opponent.

Finish every sub-game even after one fails, though. A series is six games; quitting early leaves
the other team playing a match you have abandoned.

---

## 2. Derive the `game_uid` from the **flat negotiated terms** — not from your config

The `game_uid` is a pure function of two things: the **flat negotiated terms** and the two sorted
group ids (SPEC §4). It is the only key that joins your report to your own sealed logs *and* to
your opponent's report.

So there are two ways to get it wrong, and **the second is much harder to catch than the first**:

| | What it looks like |
|---|---|
| **A fresh id** | Obvious once anyone looks: the uid appears nowhere in your logs. |
| **A deterministic id from the wrong input** | **Everything looks healthy.** The uid is stable, reproducible, and identical across all four of your artifacts — they join to each other perfectly. Only the *cross-team* join fails. |

The correct input is the flat 14-key set that was signed and exchanged — the reference computes
`derive_game_ids(terms_from_config(...), ...)`, where `terms_from_config` **extracts** those keys.
Feeding the whole `game.json`, or any wider configuration object, produces a uid that is wrong in a
way nothing on your side can see.

**This is the one that actually happened.** In the 2026-07-25 cross-team series, one side's uid was
derived from its whole config rather than from the flat negotiated terms. Its four artifacts were
internally self-consistent on that uid and looked entirely correct; every game *value* in the two
teams' reports agreed exactly — same winner, same totals, same per-sub-game outcomes. Nothing in
either implementation noticed, because nothing on either side had reason to look.

*(Our first published account of this said the uid had been "freshly minted". That was wrong, and
the correction is anrbj666's — the true mechanism is more instructive than the one we guessed,
because a minted id announces itself and a wrongly-derived one does not.)*

**Why it stayed silent for six sub-games:** the uid never crosses the wire. Each side derives it
independently and neither has anything to compare against, so a divergence surfaces only when two
reports are diffed — which happens *after* the games are over. See §2a.

Keep a fresh id for internal attempt bookkeeping if you want one. The **emitted** uid is derived,
from the terms.

```
python tools/check_artifacts.py <your artifact dir> --terms terms.json
```

catches both classes in one second. Note the `--terms`: without it the tool can only check that
your uid is *consistent*, which the wrong-input case already is. Pass the flat signed terms and it
**re-derives** the uid and compares — which is the only check that catches the sneaky one.

---

## 2a. Declare your derived `game_uid` at the handshake (PROPOSED)

The reason §2 stayed invisible for a whole series is structural: **the uid never crosses the wire.**
Both peers derive it independently, so neither has anything to compare, and the first moment a
disagreement can surface is a post-game report diff.

The proposed closure — SPEC §7.3, and deliberately the same shape as the pairing declaration in
§7.2 — is for each peer to declare its derived uid top-level in the negotiate extras:

- both declare and the values **differ** → refuse, before a single move is played;
- either side omits it → **play**. Omission never refuses, in either direction; the unmodified
  reference peer declares nothing at all, and a guard that fail-fasts on silence forfeits that game
  to itself.

Status is **PROPOSED**: one implementation intends it and the other is invited, so under
[`GOVERNANCE.md`](GOVERNANCE.md) it has one implementation behind it until a cross-team run
reproduces it. Do not assume an opponent implements it — but if you do, a wrong-input uid becomes a
refusal at the handshake instead of a contradiction in two reports the next morning.

*Finding credited to both teams: imreeyal observed that the divergence was silent for the entire
series; anrbj666's root-cause analysis made the mechanism precise.*

---

## 3. Make the lecturer's address unreachable, not merely unconfigured

An address you have configured is one flag away from being used. An address the run *cannot*
reach is not.

- **Authorization is the configuration, and the recipient is the switch.** A generic "sending is
  allowed" boolean says only that sending may happen; a recipient says who receives it — and
  nobody types the lecturer's address by accident.
- **Authorize before the match, never inside it.** By the time a series is running there is no
  human step left (book §9.3), so every decision about where mail goes has already been made.
- **A non-counted run should refuse the lecturer structurally** — matched case- and
  whitespace-insensitively, including when hidden inside a list of recipients.
- **Practising? Point your mail at yourselves, or at nothing.** Never at the lecturer. A warm-up is
  not a counted game (App. E rule 52 permits uncounted warm-ups explicitly), so nothing is owed and
  nothing should be sent onward.
- **Rate-limit the sender.** The book's own answer to a runaway loop is not human review; it is the
  gatekeeper of rule 28 — quota, then token bucket, then a breaker on repeated failure.

**Only one counted game per opponent** (App. E rule 52). An accidental early send can burn the one
meeting that scores, so the cost of being casual here is not symmetric.

---

## 4. Two teams, one match, two names for it

**`game_id` is the sorted pair**: `"-vs-".join(sorted([g_a, g_b]))` — see SPEC §4. A peer that
names *itself* first produces a different `game_id` on each side, so one match yields two sets of
artifact filenames and two reports that cannot be joined by `game_id` at all.

Both sides of the 2026-07-25 series did exactly this — **and the `game_uid` diverged in the same
run** (§2). Two reports that agreed on every game value could be joined by neither key. If you are
tempted to treat `game_id` as cosmetic because the uid will save you: in the one run where this has
actually been observed, it did not.

*(Both implementations now sort the pair — anrbj666's did so already, and imreeyal adopted it on
2026-07-27.)*

If you and your opponent cannot agree, agree to join on `game_uid` alone — and then be certain
yours is derived from the flat negotiated terms (§2).

---

## 5. Stale state does not announce itself

**Attempts share a deterministic `game_uid`.** That is the point of deriving it — but it means a
burned attempt and the real series produce the *same* artifact names and the same uid. If your
logger appends, a dead attempt leaves records at the top of the very files your settlement reads.

**Archive between attempts; never delete.** Move the previous attempt's logs aside before you start
a new one. The evidence may matter later, and the aggregation must not see it now.

**An orphaned peer will play a game for you.** A peer left alive from an earlier attempt still holds
the port. It will catch a sub-game, play it to a clean mutual audit, and settle it — while your
*real* peer for that sub-game starts a second later, starves behind it, and honestly reports a
timeout it did not cause. One game, two indices, and nothing anywhere notices that two of your peers
were alive at once. **Killing a shell does not kill what it spawned.**

```
python tools/netcheck.py --loopback <series port> <your public hostnames>
```

refuses to run if anything already holds the port, and tells you why.

**A settled peer should stop accepting.** Between settlement and process exit, your opponent's
*next* sub-game peer will greet you. Accepting there swallows the greeting into a queue nobody will
drain: they burn their whole connect budget on a message you acknowledged, and run ahead of you for
the rest of the series. Refusing makes it an ordinary transport failure, which their retry resolves
by delivering to your next peer.

---

## 6. Report format traps

- **Rule 34 says JSON attachment; the book's own listing sends a text body.** The rule requires the
  final report as an attached JSON file and refuses free text, but the book's Appendix A listing and
  the reference implementation send a plain body with no attachment. Sending **both** satisfies the
  rule literally and whatever the grader's tooling actually reads. Over-satisfying a contradiction
  is cheaper than picking the wrong side of it — and per the book's academic-freedom clause, say so
  in your documentation rather than choosing silently.
- **The emailed bytes must be the exact canonical bytes that were hashed** — never a pretty-printed
  re-serialization. Two teams once matched on every hash while one team's *email* was a
  re-serialization, and it nearly scored zero (SPEC §6).
- **Check your OAuth token before a counted series.** A Google Cloud project left in Testing mode
  expires refresh tokens after **seven days**, so a token that worked last week fails silently at
  the one moment you cannot retry.
- **Send-only scope** (rule 30). Note that a send-only scope cannot create drafts — if your safety
  gate depends on drafting, it depends on a broader permission than the rules allow.

---

## 7. If you are practising

Warm-ups are explicitly permitted and encouraged (App. E rule 52) — *"warm-up games that are not
counted are permitted and even recommended, for testing and calibration before the counted game."*
That permission comes with a shape:

- **Nothing is owed.** A practice game is not a game under rules 32/35, so no report is due from
  either side. Do not expect one from a practice peer, and do not send one.
- **Point your own mail at yourselves or disable it.** See §3.
- **Mark practice artifacts so they can never be mistaken for a league pairing** — a distinct group
  id is enough, since `game_id` is built from the group ids.
- **A practice partner cannot certify you.** Passing against one implementation proves you agree
  with *that* implementation. `python verify_vectors.py` is what proves you agree with the pinned
  bytes; the behaviour tables (SPEC §7, §7.1, §7.2) are what prove you agree on the decisions.

---

## The short version

| Do not | Because |
|---|---|
| send a report for a series that did not fully settle | rule 35 zeroes **both** teams |
| derive the `game_uid` from anything but the flat negotiated terms | your four artifacts still join each other perfectly; only the cross-team join fails, and nothing on your side can see it |
| configure the lecturer's address in a non-counted run | it is then one flag from being used |
| name the pair self-first in `game_id` | one match, two names, two sets of files |
| reuse a log directory between attempts | attempts share a deterministic uid; appended dead records reach settlement |
| assume the shell you killed took its children | an orphan will play a sub-game and settle it |
| trust a bare `502` check | it cannot tell a healthy idle tunnel from one with no ingress ([LEAGUE-OPS](LEAGUE-OPS.md)) |
