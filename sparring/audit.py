"""The end-of-game mutual audit — the iron rule (book ch.5, App. E rules 19-20).

Each side reveals every record with its nonce; the **opponent** re-hashes them with its own
serializer and compares against the commit it was sent at the time. Any mismatch is tampering by
definition — "there is no room here for interpretation or a statistical margin" — and the sanction
is total, independent of what happened on the board.

Which is exactly why a serialization difference is so expensive. Two *honest* peers whose JSON
differs by one escaped character will each fail to reproduce the other's commits, each conclude
the other tampered, and both score zero. That is the failure this whole kit exists to prevent, and
it is the one a practice run should surface.

When a mismatch is found, the report names the step and prints **both canonical strings**, plus a
pointer to the kit's ``divergent_forms`` vector — because the most common cause is not tampering
at all but having built the commit from a different one of the release's three published
constructions.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sparring import kitref


@dataclass
class AuditResult:
    passed: bool
    verified_steps: int
    failed_steps: list[int] = field(default_factory=list)
    detail: str = ""
    skipped: bool = False
    #: The steps whose commit did not reproduce — the INTEGRITY failures, which are the ones
    #: rule 20 calls tampering. Kept apart from the physics failures because a caller that
    #: reports "does not reproduce its commitment" over a physics complaint sends an honest
    #: team hunting a serialization bug it does not have (see `replay.verify_log`).
    tampered_steps: list[int] = field(default_factory=list)

    def to_wire(self) -> dict:
        return {"passed": self.passed, "verified_steps": self.verified_steps,
                "failed_steps": list(self.failed_steps), "skipped": self.skipped}


#: The five legal wire actions, in THIS kit's spelling. Anything else in a revealed record — a
#: diagonal, a typo — is a move the physics forbid, revealed only now because moves are sealed
#: during play.
#:
#: The spelling is ours, and it is not an interop constraint. ``vectors/commit_reveal.json``
#: says so in its first line — "the canonical form must match cross-team even though the
#: payload does not" — and ``turnloop`` repeats it: each side reveals its own records in its
#: own schema. Two real league teams name their moves ``"E"``, and the pairing's own signed
#: config declared ``move_set: ["N", "S", "E", "W", "STAY"]``; the reference's five directions
#: under two spellings are the same five directions.
#:
#: So this set is only consulted when the caller ARMS the physics layer with the signed terms
#: (see ``audit_records``). Applied unconditionally it called an honest, sealed, counted bundle
#: TAMPERED — found by the reciprocal audit of anrbj666's counted artifacts, 2026-08-05, in the
#: copy of OUR OWN records they had sealed as ``opponent_records``.
_MOVE_DELTA = {"MOVE:N": (-1, 0), "MOVE:S": (1, 0), "MOVE:E": (0, 1), "MOVE:W": (0, -1),
               "STAY": (0, 0)}
_LEGAL_MOVES = frozenset(_MOVE_DELTA)


def audit_records(records: list[dict], *, played: dict[int, str] | None = None,
                  board_size: int | None = None, barriers_max: int | None = None,
                  max_steps: int | None = None) -> AuditResult:
    """Re-hash every revealed record with OUR serializer — and CLOSE the commit-reveal loop.

    Three layers, each optional args arm the next (anrbj666's audit, findings A1-A3, proved the
    first revision hollow: a wholly fabricated log — a game never played, with diagonal moves at
    off-board coordinates — passed, because the only check was re-hashing each record against
    the commit embedded in that same record):

    1. **Integrity** (always): every revealed record re-hashes to its own commit.
    2. **Binding** (``played`` given — the step→commit map of what actually arrived in play):
       for every step up to the last one we consumed, the revealed commit must EQUAL the commit
       received at the time, and every received step must be revealed. Steps past our consumed
       frontier are tolerated — the game legitimately ends before the receiver drains the
       sender's final messages. This is the comparison the docstring always promised.
    3. **Physics** (board/quota/ceiling given): revealed positions must be on the board, the
       position trail must advance by at most one orthogonal step (which is what makes a
       diagonal illegal, whatever the peer calls one), barrier placements must fit the signed
       quota, and steps must not exceed the ceiling (+1 for a terminal).

       The physics are judged from the POSITION TRAIL, never from the peer's spelling of a
       move. An earlier revision rejected any ``move`` token outside this kit's own
       ``MOVE:<D>`` vocabulary, unconditionally — and both real league teams name their moves
       ``"E"``, so it called an honest, sealed, counted series TAMPERED. A revealed payload's
       schema is not an interop constraint (``vectors/commit_reveal.json``, ``turnloop``); the
       trail it describes is. Where the token IS one this kit recognises, it is cross-checked
       against the delta the positions actually show — a free extra check that can never fire
       on a vocabulary we simply do not know.
    """
    failed: list[int] = []
    tampered: list[int] = []
    notes: list[str] = []
    revealed_by_step: dict[int, dict] = {}
    prev_pos: tuple[int, int] | None = None
    barriers_seen = 0
    for record in records:
        payload, nonce, claimed = record.get("payload"), record.get("nonce"), record.get("commit")
        if payload is None or nonce is None or claimed is None:
            failed.append(int((payload or {}).get("step", -1)))
            notes.append("a revealed record is missing payload, nonce or commit")
            continue
        recomputed = kitref.commit(payload, nonce)
        step = int(payload.get("step", -1))
        if recomputed != claimed:
            failed.append(step)
            tampered.append(step)
            if len(notes) < 3:      # enough to diagnose; not the whole log
                notes.append(
                    f"step {step}: they committed {claimed}, we recompute {recomputed}\n"
                    f"      our canonical form of their payload:\n"
                    f"      {kitref.canonical_str(payload)}")
            continue
        if step >= 1:
            revealed_by_step[step] = record
        # --- physics: only game-turn payloads (step-0 declarations carry no position) --------
        if step < 1 or "position" not in payload:
            continue
        pos = payload.get("position")
        move = payload.get("move")
        problems: list[str] = []
        try:
            r, c = int(pos[0]), int(pos[1])
        except (TypeError, ValueError, IndexError):
            problems.append(f"position {pos!r} is not a cell")
            r = c = -1
        if board_size is not None and not (0 <= r < board_size and 0 <= c < board_size):
            problems.append(f"position {pos} is off the {board_size}x{board_size} board")
        if prev_pos is not None and abs(r - prev_pos[0]) + abs(c - prev_pos[1]) > 1:
            problems.append(f"position jumps {prev_pos} -> {(r, c)}: more than one orthogonal "
                            f"step between consecutive revealed records")
        # Only where we RECOGNISE the token: does it describe the step the positions show?
        # Silence on an unrecognised vocabulary is deliberate — see the note on _LEGAL_MOVES.
        if move in _LEGAL_MOVES and prev_pos is not None:
            want = _MOVE_DELTA[move]
            got = (r - prev_pos[0], c - prev_pos[1])
            if got != want:
                problems.append(f"move {move!r} says {want} but the positions moved {got}")
        prev_pos = (r, c)
        if payload.get("verdict") == "placed_barrier":
            barriers_seen += 1
            if barriers_max is not None and barriers_seen > barriers_max:
                problems.append(f"barrier placement #{barriers_seen} exceeds the signed quota "
                                f"of {barriers_max}")
        if max_steps is not None and step > max_steps + 1:
            problems.append(f"step {step} is past the ceiling ({max_steps} + a terminal)")
        if problems:
            failed.append(step)
            if len(notes) < 6:
                notes.append(f"step {step} PHYSICS: " + "; ".join(problems))

    # --- binding: the revealed game must be the game we received --------------------------
    if played:
        frontier = max(played)
        for step in sorted(int(s) for s in played):
            received = played.get(step, played.get(str(step)))
            revealed = revealed_by_step.get(step)
            if revealed is None:
                failed.append(step)
                notes.append(f"step {step} BINDING: received in play (commit {received}) but "
                             f"missing from the reveal — a withheld turn")
            elif revealed.get("commit") != received:
                failed.append(step)
                notes.append(f"step {step} BINDING: revealed under commit "
                             f"{revealed.get('commit')} but PLAYED under {received} — the "
                             f"revealed log is a different game than the one on the wire")
        for step in sorted(revealed_by_step):
            if step <= frontier and step not in played and str(step) not in played:
                failed.append(step)
                notes.append(f"step {step} BINDING: revealed, inside our consumed range, but "
                             f"never received in play")
    failed = sorted(set(failed))
    result = AuditResult(passed=not failed, verified_steps=max(0, len(records) - len(failed)),
                         failed_steps=failed, tampered_steps=sorted(set(tampered)))
    if failed:
        result.detail = "\n    ".join(notes)
        # The three-constructions advice is for a HASH mismatch only. Printed under a physics
        # or binding failure it sends an honest team hunting a serialization bug it does not
        # have — which is exactly how a spelling complaint once read as tampering.
        if tampered:
            result.detail += (
                "\n    Before concluding tampering: the release publishes THREE different "
                "commit constructions, and building from the wrong one fails every audit in "
                "good faith. Hash one of their records under all three with the "
                "`divergent_forms` entry in vectors/commit_reveal.json — if one of the others "
                "matches, that is the bug. Otherwise compare the canonical strings for an "
                "escaped non-ASCII character (SPEC section 2).")
    return result


def skipped() -> AuditResult:
    """No audit is possible when a game never produced revealed records.

    The reference skips the audit on timeout and stop, and so do we — but it is recorded as
    skipped rather than passed. A hollow "verified" entry in an artifact is worse than an honest
    absence.
    """
    return AuditResult(passed=False, verified_steps=0, skipped=True,
                       detail="no revealed records — the game never reached settlement")
