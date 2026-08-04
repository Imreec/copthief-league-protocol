"""Playing a real opponent over MCP — our side only.

``series.py`` drives both sides for self-play. Against a real peer we drive exactly one, which
changes the shape in ways worth naming, because each one cost a real team a window:

* **We wait, bounded by our own budget.** A silent opponent is classified by rule (App. E) and
  never by self-termination — so the deadline that ends a sub-game is ours, and the transport's
  give-up must outlast it (``deadlines.Budgets``).
* **The handshake runs per sub-game**, and a greeting that fails the pairing check is refused *on
  the record* rather than accepted. On a role-split wire the opponent's other window can push at
  our port carrying identical signed terms; it belongs to a different game.
* **A settled peer stops accepting.** Between settlement and the next sub-game the opponent's next
  peer greets us; swallowing that greeting into a queue nobody drains makes them burn their whole
  connect budget on a message we acknowledged.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from sparring import KIT_REPO_URL, kitref
from sparring.artifacts import ArtifactSet, assert_uncounted_group
from sparring.config import SparConfig
from sparring.deadlines import MonotonicClock, poll_until
from sparring.identity import locks
from sparring.negotiate import Refused, our_greeting, verify_peer
from sparring.policies import REGISTRY
from sparring.preflight import assert_sparring_ready
from sparring.rules.outcome import Outcome, Role, role_for, score_for
from sparring.state import PeerState
from sparring.turnloop import SubGamePeer


class NetworkTransport:
    """Sends through an MCP client; receives from the server's inboxes."""

    def __init__(self, client, inboxes) -> None:
        self.client = client
        self.inboxes = inboxes

    def send_turn(self, message: dict) -> dict:
        return self.client.receive_turn(message)

    def send_agreement(self, message: dict) -> dict:
        return self.client.negotiate(message)

    def send_audit(self, payload: dict) -> dict:
        return self.client.submit_audit(payload)

    def send_control(self, message: dict) -> dict:
        return self.client.receive_control(message)

    def poll_turn(self):
        return self.inboxes.turns.popleft() if self.inboxes.turns else None

    def poll_agreement(self):
        return self.inboxes.agreements.popleft() if self.inboxes.agreements else None

    def poll_audit(self):
        return self.inboxes.audits.popleft() if self.inboxes.audits else None


@dataclass
class NetResult:
    game_id: str = ""
    game_uid: str = ""
    ledger: list[dict] = field(default_factory=list)
    settled: bool = True
    artifacts: list[Path] = field(default_factory=list)
    note: str = ""


def handshake(cfg: SparConfig, transport, role: Role, n: int, lock_hashes,
              budget: float, poll: float, clock, opponent_group: str | None = None):
    """Exchange greetings for one sub-game. Refuses a bystander on the record and keeps waiting."""
    mine = our_greeting(cfg, role.value, n, f"{n:032x}", lock_hashes, opponent_group)
    transport.send_agreement(mine.to_wire())

    deadline = clock.now() + budget
    last: Refused | None = None
    while clock.now() < deadline:
        raw = transport.poll_agreement()
        if raw is None:
            clock.sleep(poll)
            continue
        try:
            return verify_peer(cfg, mine, raw)
        except Refused as exc:
            # A bystander's agreement carries identical signed terms and fails only the pairing
            # check — it belongs to a different game. Say so and keep waiting for our counterpart,
            # bounded by the same budget. Terms drift and bad signatures still raise at once.
            last = exc
            print(f"  refused a greeting: {exc}")
            if exc.code not in ("SPAR-N06", "SPAR-N07"):
                raise
    raise Refused("SPAR-N09",
                  "handshake budget exhausted; our counterpart never arrived"
                  + (f" (last refusal {last.code})" if last else ""))


def play_series(cfg: SparConfig, client, inboxes, artifacts_dir: Path,
                sub_games: int = 6) -> NetResult:
    """Play our side of a whole series against a real opponent."""
    assert_uncounted_group(cfg.group_id)
    report = assert_sparring_ready(cfg)
    transport = NetworkTransport(client, inboxes)
    budgets = cfg.budgets
    clock = MonotonicClock()
    natural = Role(cfg.natural_role)
    lock_hashes = locks(cfg.scent_model)
    result = NetResult()
    artifacts: ArtifactSet | None = None

    known_opponent: str | None = None
    for n in range(1, sub_games + 1):
        role = role_for(natural, n)
        print(f"\n  sub-game {n}: we are {role.value}")
        try:
            # From sub-game 2 onward the opponent is known, so the greeting declares the derived
            # game_uid (SPEC section 7.3). Sub-game 1 declares none — omission never refuses.
            agreed = handshake(cfg, transport, role, n, lock_hashes,
                               budgets.turn_timeout, budgets.poll_interval, clock,
                               opponent_group=known_opponent)
        except Refused as exc:
            print(f"  {exc}")
            result.settled = False
            result.note = str(exc)
            break

        known_opponent = agreed.opponent_group
        if artifacts is None:
            result.game_id, result.game_uid = agreed.game_id, agreed.game_uid
            artifacts = ArtifactSet(artifacts_dir, agreed.game_id, agreed.game_uid,
                                    report.mail_scan_sha256)
            result.artifacts.append(artifacts.declaration(
                [{"group_id": cfg.group_id, "group_name": cfg.group_name,
                  "llm_model": "template", "members": [],
                  "repos": {"cop": KIT_REPO_URL, "thief": KIT_REPO_URL}, "mcp_servers": {}},
                 {"group_id": agreed.opponent_group, "group_name": "", "llm_model": "",
                  "members": [], "repos": {}, "mcp_servers": {}}], sub_games))

        peer = SubGamePeer(cfg=cfg, role=role, sub_game_number=n,
                           policy=REGISTRY[cfg.policy][role.value](), transport=transport,
                           clock=clock, budgets=budgets, seed=cfg.seed)
        peer.seal_step_zero(cfg.group_name)
        outcome = _play_one(peer, role, cfg, budgets, clock)

        peer.send_audit(outcome.value)
        audit = poll_until(peer.verify_audit_if_ready, budgets.turn_timeout,
                           budgets.poll_interval, clock)
        verified = bool(audit and audit.passed)
        print(f"  settled: {outcome.value} after {peer.step} steps; "
              f"opponent audit {'Verified OK' if verified else 'NOT verified'}")

        result.artifacts.append(artifacts.config(n, cfg.terms()))
        result.artifacts.append(artifacts.log(n, {
            "sub_game_number": n, "group_id": cfg.group_id, "role": role.value,
            "result": outcome.value, "steps": peer.step,
            "audit": audit.to_wire() if audit else {},
        }, peer.records, {"opponent_group_id": agreed.opponent_group,
                          "sha256": kitref.canonical_hash({"sub_game": n,
                                                           "result": outcome.value}),
                          "confirmed": verified}))
        result.ledger.append({"sub_game_number": n, "role": role.value,
                              "outcome": outcome.value, "steps": peer.step,
                              "score": score_for(outcome, role), "audit_ok": verified})
        if not verified:
            result.settled = False

        # Drain anything the opponent's NEXT peer pushed while we were settling: it belongs to
        # the next sub-game's handshake, not this one.
        inboxes.turns.clear()

    # The result artifact is written only when every sub-game settled. That is the settlement
    # guard from docs/WARNINGS.md §1: a report that quietly drops a game is precisely what App. E
    # rule 35 punishes — on BOTH teams. Nothing is owed for a sparring run, which is exactly why
    # it costs nothing to keep the habit here.
    if artifacts is not None and result.settled and len(result.ledger) == sub_games:
        ours, theirs = cfg.group_id, result.ledger and agreed.opponent_group
        totals = {ours: sum(row["score"] for row in result.ledger)}
        sub_games_block = [{
            "sub_game_number": row["sub_game_number"],
            "roles": {ours: row["role"]},
            "result": row["outcome"],
            "score": {ours: row["score"]},
            "tokens": {ours: 0},
            "audit": {"log_verified": row["audit_ok"], "tampered": not row["audit_ok"]},
        } for row in result.ledger]
        result.artifacts.append(artifacts.result(
            [{"group_id": ours, "group_name": cfg.group_name,
              "repos": {"cop": KIT_REPO_URL, "thief": KIT_REPO_URL}},
             {"group_id": theirs, "group_name": ""}],
            sub_games_block,
            {"total_score": totals,
             "sub_games_won": {ours: sum(1 for r in result.ledger if r["score"] > 5)},
             "ties": 0, "winner_group": None, "series_tie": False,
             "tokens_total_series": {ours: 0},
             "_remark": "one side's view. A counted series settles the result WITH the opponent "
                        "before either reports; this is a practice run and reports nothing."}))
    elif artifacts is not None:
        print("\n  no result artifact: a sub-game did not settle. A report that quietly drops a "
              "game\n  is what rule 35 punishes, on both teams — so the guard refuses the whole "
              "series.")

    return result


def _play_one(peer: SubGamePeer, role: Role, cfg: SparConfig, budgets, clock) -> Outcome:
    """One sub-game against a live opponent. Police move first."""
    our_move_first = role is Role.POLICE
    for _ in range(cfg.max_steps * 2):
        if our_move_first:
            message = peer.take_turn()
            peer.transport.send_turn(message.to_wire())
            peer.machine.to(PeerState.VERIFYING)
            peer.machine.to(PeerState.WAITING_FOR_OPPONENT)

        raw = poll_until(peer.transport.poll_turn, budgets.turn_timeout,
                         budgets.poll_interval, clock)
        if raw is None:
            return Outcome.TIMEOUT
        for applied in peer.receive(raw):
            answer = peer.answer(applied)
            verdict = peer.adjudicate(applied, answer)
            if verdict is not None:
                # Deliver what we owe before we stop talking. The opponent cannot see the board;
                # if we walk away holding the answer, it waits out its budget and settles a game
                # it won as a timeout.
                final = peer.terminal_message()
                if final is not None:
                    peer.transport.send_turn(final.to_wire())
                return verdict

        if not our_move_first:
            message = peer.take_turn()
            peer.transport.send_turn(message.to_wire())
            peer.machine.to(PeerState.VERIFYING)
            peer.machine.to(PeerState.WAITING_FOR_OPPONENT)
            own = peer.engine.self_captured()
            if own is not None:
                final = peer.terminal_message()
                if final is not None:
                    peer.transport.send_turn(final.to_wire())
                return own
            if peer.engine.survived():
                # The survival claim already rode out on the message just sent.
                return Outcome.SURVIVAL
    return Outcome.SURVIVAL
