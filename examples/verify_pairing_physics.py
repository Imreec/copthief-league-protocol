"""Verify examples/pairing-artifacts/ is a set of games that could actually be PLAYED.

    python examples/verify_pairing_physics.py

`tools/check_artifacts.py` checks names, ids, required keys and score arithmetic — by
design it never opens a sealed payload, so it cannot see a log whose records contradict
its own summary. This does: it re-hashes every sealed record, walks both sides' moves
under the book's physics, and requires each sub-game to actually REACH the outcome its
row declares.

It exists because an earlier revision of this bundle shipped one-step logs declaring
`capture` (with the cop three cells from the thief) and `survival` (against a threshold of
35) — each row asserting `log_verified: true` over a game that could not produce its own
result. `check_artifacts` passed it. Found by anrbj666 auditing anrbj666's contribution,
2026-08-04; this checker is the regression gate for that class.

Exit 0 = every game is legal and reaches its declared outcome.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import verify_vectors as ref  # noqa: E402

BUNDLE = Path(__file__).resolve().parent / "pairing-artifacts"
DELTAS = {"MOVE:N": (-1, 0), "MOVE:S": (1, 0), "MOVE:E": (0, 1), "MOVE:W": (0, -1),
          "STAY": (0, 0)}          # the book's move set: orthogonal or stay, never diagonal

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    if not ok:
        failures.append(f"{label}{('  ' + detail) if detail else ''}")
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{('  ' + detail) if detail and not ok else ''}")


def walk(records: list[dict], start: tuple[int, int], board: int,
         label: str) -> tuple[int, int]:
    """Replay one side's revealed moves; every step must be legal and on the board."""
    pos = start
    for rec in records:
        payload = rec["payload"]
        if payload.get("step") == 0:
            continue
        move = payload.get("move")
        if move not in DELTAS:
            failures.append(f"{label}: step {payload.get('step')} move {move!r} is not in the "
                            f"book's move set (no diagonals)")
            continue
        delta = DELTAS[move]
        nxt = (pos[0] + delta[0], pos[1] + delta[1])
        if not (0 <= nxt[0] < board and 0 <= nxt[1] < board):
            failures.append(f"{label}: step {payload['step']} leaves the board at {nxt}")
        if list(nxt) != payload.get("position"):
            failures.append(f"{label}: step {payload['step']} declares position "
                            f"{payload.get('position')} but {move} from {list(pos)} lands {list(nxt)}")
        if payload.get("state", "").split("self=")[-1].split(";")[0] != f"[{nxt[0]}, {nxt[1]}]":
            failures.append(f"{label}: step {payload['step']} state disagrees with position")
        pos = nxt
    return pos


def main() -> int:
    result = json.loads((BUNDLE / [p.name for p in BUNDLE.glob("result_*.json")][0])
                        .read_text(encoding="utf-8"))
    rows = {row["sub_game_number"]: row for row in result["sub_games"]}

    for log_path in sorted(BUNDLE.glob("log_*_g*.json")):
        doc = json.loads(log_path.read_text(encoding="utf-8"))
        n = doc["sub_game_number"]
        cfg = json.loads((BUNDLE / f"config_{doc['game_id']}_g{n:02d}.json")
                         .read_text(encoding="utf-8"))
        terms, row = cfg["terms"], rows[n]
        board, max_steps = terms["board_size"], terms["max_steps"]
        print(f"{log_path.name}  ({row['result']}, {row['steps']} steps)")

        # 1. every sealed record re-hashes
        bad = [r["payload"].get("step") for r in doc["records"] + doc["opponent_records"]
               if ref.ref_commit(r["payload"], r["nonce"]) != r["commit"]]
        check("every sealed record re-hashes to its commit", not bad, f"failed steps {bad}")

        # 2. both sides' walks are legal, from the START CELLS THE TERMS DECLARE
        mine_is_cop = doc["summary"]["role"] == "police"
        my_start = tuple(terms["cop_start"] if mine_is_cop else terms["thief_start"])
        their_start = tuple(terms["thief_start"] if mine_is_cop else terms["cop_start"])
        before = len(failures)
        my_end = walk(doc["records"], my_start, board, f"g{n:02d} own")
        their_end = walk(doc["opponent_records"], their_start, board, f"g{n:02d} opponent")
        check("both sides' moves are legal and on the board", len(failures) == before,
              "; ".join(failures[before:]))

        # 3. the declared step count matches the records
        played = max(r["payload"]["step"] for r in doc["records"])
        check("summary.steps matches the sealed records", played == row["steps"] == doc["summary"]["steps"],
              f"records reach {played}, summary says {doc['summary']['steps']}, row says {row['steps']}")

        # 4. THE OUTCOME IS ACTUALLY REACHED
        cop_end, thief_end = (my_end, their_end) if mine_is_cop else (their_end, my_end)
        if row["result"] == "capture":
            check("a capture is on the board: the cop ends on the thief's cell",
                  cop_end == thief_end, f"cop {cop_end}, thief {thief_end}")
        elif row["result"] == "survival":
            check(f"a survival reaches the threshold ({max_steps} steps)", played >= max_steps,
                  f"played {played}")
            check("the thief was never caught along the way", cop_end != thief_end,
                  f"both ended on {cop_end}")
        print()

    print("BUNDLE PHYSICS OK" if not failures else f"{len(failures)} PHYSICS FAILURE(S)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
