# Role conventions and the sub-game index (PROPOSED)

**Status: PROPOSED.** Two implementations play the constructions below and one pairing has
settled a counted series under them. No fixture is proposed here — see
[What a fixture would pin](#what-a-fixture-would-pin) for what one should assert if the kit
wants it.

*Proposed by best2934 (Krayz1a) from the best2934 ↔ gal-roy1 and best2934 ↔ imreeyal pairings,
2026-08-09 → 2026-08-15. Co-signed by imreeyal (Imreec), league issue #45.*

[SPEC §7.2](../SPEC.md) pins the *handshake* declaration: both peers put `sub_game_number` and
`role` in the negotiate extras, and a mismatch refuses to play. This page is the other half of the
same question — **where those two values come from before anyone declares them**, and what the
report has to say afterwards. §7.2 catches a disagreement at the door. Neither of the failures
below reaches the door.

---

## 1. Name the role convention; it is a pairing term, not a constant

The rulebook assigns no roles across a series. Two conventions are in live use, both giving each
team three sub-games of each role, both order-independent, and **neither more correct than the
other**:

| Name | Cop in sub-games | Notes |
|---|---|---|
| `first_half` | `sorted(group_ids)[0]` cops 1, 2, 3; the other cops 4, 5, 6 | The role swaps once, at half time |
| `odd_even` | `sorted(group_ids)[0]` cops 1, 3, 5; the other cops 2, 4, 6 | The role swaps every sub-game |

Sorting is what makes either safe: both peers compute the same answer from the two group ids and
the sub-game number alone, with nothing to exchange.

**They disagree on sub-games 2 and 5.** Under `first_half` the first-sorted group cops sub-game 2;
under `odd_even` it plays thief. So two teams that have each implemented a convention correctly,
and each believe they are conformant, produce **two cops on sub-game 2 and two thieves on
sub-game 5**. Two cops chase nobody. The sub-game cannot start, and rule 6 charges *both* teams
for the stall.

This is exactly the bar CONTRIBUTING sets for a proposal: two independent implementations silently
disagreeing and losing a game as a result. The fix is not to pick one — it is to make the choice
**named and declared**, the way the kit already treats the scent model.

> **Proposed:** register `first_half` and `odd_even` as named role conventions. A pairing declares
> one in its planning message; absent a declaration, a pairing has not agreed roles and should not
> schedule a T.

A team that supports only one should say so in first contact. We support both, selected per
opponent, because our two pairings wanted different ones — `gal-roy1` pinned `first_half`,
`imreeyal` play `odd_even`.

---

## 2. The sub-game index must be derivable, and global across a team's repositories

Rule 41 splits a team's cop and thief into **two repositories**. A six-sub-game series is therefore
split across two artifact trees, and the series result has to be assembled from both.

Our assembler merged the two trees keyed on the artifact **filename**. Against `imreeyal` the
numbering happened to be globally disjoint — our cop wrote 1/3/5, our thief wrote 2/4/6 — so no two
files ever shared a name and the merge was correct. **That was luck, not design.**

Against `gal-roy1`, both of our repositories numbered their own sub-games from `g01`. So
`log_<game_id>_g01.json` existed in each, naming two *different* sub-games. The merge collapsed
them: one repository's logs silently overwrote the other's. The result artifact then declared that
we had played police in **all eight** sub-games of a series whose roles must swap — impossible on
its face, internally consistent, signed, and produced without one warning.

Two properties would each have prevented it, and they are worth stating separately:

**(a) The index is derived, not counted.** A team's local numbering is not a series index. The
index is a function of the pairing's declared role convention and the sorted group ids:

```
cop_group(a, b, n, convention)  →  which team cops sub-game n
```

Run backwards, it assigns positions: a team's cop-side logs take the slots where that team cops,
its thief-side logs take the rest. Both peers reach the same mapping from the two group ids and
the convention alone — the same property that makes the role assignment safe in the first place.

**(b) The index is global across the team, not per-repository.** Whatever a team's internal layout,
the sub-game recorded as `n` in its report is the *series* position `n`. A merge that can put two
different sub-games under one key is a merge that will, and rule 41 guarantees every team has one.

> **Proposed:** the per-sub-game index in a report must be derivable from the pairing's declared
> role convention and the sorted group ids alone, and must be global across a team's series
> regardless of how many repositories that team splits its code into.

### Why the digest does not catch this

`mutual_agreement` scope covers the per-sub-game rows. So a numbering disagreement *does* move the
digest — which sounds like it is already caught, and is not:

- Two teams can agree on `total_score`, `sub_games_won` and the winner while disagreeing row by
  row, because sums do not care about labels. The settlement then shows one digest mismatch and no
  obvious cause, at the worst possible moment.
- In our gal-roy1 case the collapsed result reproduced the **correct** digest of a *previous*
  series, because the discarded and retained openers happened to have the same role and outcome. A
  wrong artifact that reproduces a known-good digest is the only kind that survives a settlement.

---

## What a fixture would pin

We are not proposing a fixture, because we have not run this repo's generators and CONTRIBUTING is
explicit that fixtures are generated rather than hand-written. If the kit wants one, these are the
assertions that carry the weight:

1. For each convention and each `n` in 1..6, `cop_group(a, b, n, convention)` — order-independent,
   asserted with the pair given both ways round.
2. `first_half` and `odd_even` **differ** at `n = 2` and `n = 5` and agree elsewhere. A fixture
   that only checks one convention proves nothing about the clash that costs the game.
3. The inverse mapping: given a team's role per sub-game, the derived index is a permutation of
   1..N with no repeats — the property whose absence produced `1, 1, 2, 2, 3, 3`.

---

## Evidence

- **Role-convention clash** — best2934 supports both conventions per-opponent
  (`config/<role>/setup.json`, `role_convention`), after `gal-roy1` pinned `first_half` and
  `imreeyal` play the kit's `odd_even`. The sub-game 2 / 5 disagreement is arithmetic, not
  observed: we implemented the selector rather than play the clash.
- **Filename-collision merge** — observed on our own artifacts, 2026-08-15, and disclosed on
  league issue #45 before it reached a counted report. Two result artifacts for one `game_id` and
  one `game_uid`, reading 115–55 over 8 sub-games and 95–55 over 10, against a series both teams
  had settled at 75–35 over 6.
- **Counted series settled under these constructions** — best2934 ↔ imreeyal, 2026-08-15, six
  sub-games, both reports filed and cross-diffed key by key with an identical
  `games_played_including_this`, per-sub-game rows and audits. imreeyal recorded the verdict as
  settled on issue #45.

*Rules 46/47 under the movement reading were co-signed in the same exchange and are deliberately
**not** in this PR: imreeyal found that one and hold the book citations, so the wording should be
theirs rather than our paraphrase.*
