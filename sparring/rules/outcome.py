"""How a sub-game ends, and what it is worth (book ch.3 table 2; App. F table 17).

Every value here is `קבוע` — permanent in the binding table, not negotiable in either direction.
They live in one place so that nothing else in the package can quietly hold a second copy.
"""

from __future__ import annotations

from enum import Enum


class Role(str, Enum):
    POLICE = "police"
    THIEF = "thief"

    @property
    def other(self) -> "Role":
        return Role.THIEF if self is Role.POLICE else Role.POLICE


class Outcome(str, Enum):
    CAPTURE = "capture"                  # the cop took the thief, by claim or by barrier or by trap
    SURVIVAL = "survival"                # the thief reached the survival threshold uncaught
    TIMEOUT = "timeout"                  # a side went silent past its budget — App. E, technical
    TECHNICAL_LOSS = "technical_loss"    # a crash, an illegal move, an illegal state transition
    TAMPER_FORFEIT = "tamper_forfeit"    # an audit re-hash missed: the iron rule, book ch.5


#: (police, thief) points. Technical loss and tamper forfeit deliberately zero BOTH sides — the
#: book's stated reason is to make protocol correctness worth more to each side than a win on
#: time. It also means an honest peer can be zeroed by its opponent's failure, which is why the
#: refusals elsewhere in this package are loud rather than forgiving.
SCORES: dict[Outcome, tuple[int, int]] = {
    Outcome.CAPTURE: (20, 5),
    Outcome.SURVIVAL: (5, 10),
    Outcome.TIMEOUT: (0, 0),
    Outcome.TECHNICAL_LOSS: (0, 0),
    Outcome.TAMPER_FORFEIT: (0, 0),
}

#: Points to each side when the CUMULATIVE score across a whole series ends level (App. F).
TIE_SCORE = 2

#: Sub-games in a series against one opponent (App. F table 18, permanent).
SUB_GAMES_PER_SERIES = 6


def score_for(outcome: Outcome, role: Role) -> int:
    police, thief = SCORES[outcome]
    return police if role is Role.POLICE else thief


def role_for(natural: Role, sub_game_number: int) -> Role:
    """Odd sub-games play your natural role; even ones play the opposite.

    Worth knowing where this comes from: **role alternation is not stated anywhere in the book's
    body.** It appears only in the reference implementation and in the sample artifacts' own
    schema text ("roles switch across the sub-games, so no role and no sub_game_number appear
    here"). It is followed because both sides of a real series followed it and because the
    reference defines it — but a pair that has not agreed it explicitly should, since nothing in
    the binding table would settle an argument about it.
    """
    return natural if sub_game_number % 2 == 1 else natural.other
