"""netplay's live-opponent paths, held to the same contract self-play implements.

Regression cases for anrbj666's B1/B2/B3 (2026-08-04 audit): the driver that meets strangers
crashed on inbound violations, moved on stale state under redelivery, and sealed past the step
ceiling. Each test drives `_play_one` with a scripted transport — no network, no fastmcp.
"""

import unittest

from sparring import kitref
from sparring.config import SparConfig
from sparring.deadlines import Budgets, FakeClock
from sparring.netplay import _play_one
from sparring.policies import REGISTRY
from sparring.proto.messages import TurnMessage
from sparring.rules.outcome import Outcome, Role
from sparring.turnloop import SubGamePeer


class ScriptedTransport:
    """Feeds a fixed inbound script; records everything sent."""

    def __init__(self, script: list[dict]) -> None:
        self.script = list(script)
        self.sent: list[dict] = []

    def send_turn(self, message: dict) -> dict:
        self.sent.append(message)
        return {"ok": True}

    def poll_turn(self):
        return self.script.pop(0) if self.script else None


def turn(step: int, sender: str = "police", **over) -> dict:
    payload = {"step": step, "who": sender}
    nonce = f"{step:032x}"
    base = TurnMessage(step=step, sender=sender, commit=kitref.commit(payload, nonce),
                      hint="", smell_grid={}).to_wire()
    base.update(over)
    return base


def make_peer(role: Role, cfg: SparConfig, transport, clock) -> SubGamePeer:
    return SubGamePeer(cfg=cfg, role=role, sub_game_number=1,
                       policy=REGISTRY[cfg.policy][role.value](), transport=transport,
                       clock=clock, budgets=cfg.budgets, seed=1234)


class TestInboundViolationsAreClassified(unittest.TestCase):
    def test_an_equivocation_settles_as_technical_loss_instead_of_crashing(self):
        # B1: same step, two different commits — tampering evidence. The first revision let
        # the exception unwind the whole series; a live opponent's fault became our crash.
        cfg = SparConfig(budgets=Budgets(turn_timeout=5.0, poll_interval=0.5, connect_timeout=2.0))
        first = turn(1)
        second = turn(1)
        second["commit"] = "0" * 64          # different commit for the played step
        transport = ScriptedTransport([first, second])
        clock = FakeClock()
        peer = make_peer(Role.THIEF, cfg, transport, clock)
        outcome = _play_one(peer, Role.THIEF, cfg, cfg.budgets, clock)
        self.assertIs(outcome, Outcome.TECHNICAL_LOSS)

    def test_a_thief_sent_barrier_settles_as_technical_loss(self):
        # A3's live half, reaching through netplay: only the cop places barriers.
        cfg = SparConfig(budgets=Budgets(turn_timeout=5.0, poll_interval=0.5, connect_timeout=2.0))
        bad = turn(1, sender="thief", barrier_placed=[0, 0])
        transport = ScriptedTransport([bad])
        clock = FakeClock()
        peer = make_peer(Role.POLICE, cfg, transport, clock)
        outcome = _play_one(peer, Role.POLICE, cfg, cfg.budgets, clock)
        self.assertIs(outcome, Outcome.TECHNICAL_LOSS)


class TestExpectedStepWait(unittest.TestCase):
    def test_a_redelivery_does_not_provoke_a_second_own_turn(self):
        # B2: the cop's poll used to be discharged by ANY raw message. A duplicate of the
        # thief's step-1 message (absorbed, nothing applied) let the cop fall through and take
        # a second consecutive turn on stale state. Now the wait is for the message we are
        # OWED: after one applied message the cop has taken exactly one own turn, and the
        # duplicate has renewed nothing.
        cfg = SparConfig(budgets=Budgets(turn_timeout=5.0, poll_interval=0.5, connect_timeout=2.0))
        original = turn(1)
        duplicate = dict(original)
        transport = ScriptedTransport([original, duplicate])
        clock = FakeClock()
        peer = make_peer(Role.POLICE, cfg, transport, clock)
        outcome = _play_one(peer, Role.POLICE, cfg, cfg.budgets, clock)
        # The script dries up, so the sub-game times out — the point is what happened first:
        self.assertIs(outcome, Outcome.TIMEOUT)
        own_steps = [m["step"] for m in transport.sent]
        self.assertEqual(own_steps, sorted(set(own_steps)),
                         "an own step was sealed twice — moved on stale state")
        self.assertEqual(peer.inbox.absorbed, 1, "the duplicate should be absorbed, once")

    def test_junk_never_renews_the_deadline(self):
        # A flood of duplicates must not hold us past our own budget (LEAGUE-OPS §5).
        cfg = SparConfig(budgets=Budgets(turn_timeout=3.0, poll_interval=0.5, connect_timeout=2.0))
        original = turn(1)
        flood = [dict(original) for _ in range(50)]
        transport = ScriptedTransport([original] + flood)
        clock = FakeClock()
        peer = make_peer(Role.POLICE, cfg, transport, clock)
        outcome = _play_one(peer, Role.POLICE, cfg, cfg.budgets, clock)
        self.assertIs(outcome, Outcome.TIMEOUT)
        self.assertLessEqual(clock.now(), 3.0 * 3,
                             "the flood held the deadline open far past the budget")


class TestStepCeiling(unittest.TestCase):
    def test_the_cop_never_seals_past_max_steps(self):
        # B3: a thief that never claims survival used to draw the cop into sealing steps
        # 36..70. The ceiling now binds both roles; the cop stops sealing and waits.
        cfg = SparConfig(max_steps=3, survival_threshold=3,
                         budgets=Budgets(turn_timeout=5.0, poll_interval=0.5, connect_timeout=2.0))
        # A thief that answers every step but never sends win_claim:
        script = [turn(s, sender="thief") for s in range(1, 10)]
        transport = ScriptedTransport(script)
        clock = FakeClock()
        peer = make_peer(Role.POLICE, cfg, transport, clock)
        _play_one(peer, Role.POLICE, cfg, cfg.budgets, clock)
        self.assertLessEqual(peer.step, cfg.max_steps,
                             f"sealed {peer.step} steps against a ceiling of {cfg.max_steps}")


if __name__ == "__main__":
    unittest.main()
