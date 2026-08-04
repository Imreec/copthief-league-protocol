"""Regenerate examples/pairing-artifacts/ — a full six-sub-game artifact bundle in the
format the PAIRING-PLAYBOOK campaign actually played (2026-08-04 counted series shape).

    python examples/gen_pairing_artifacts.py          # rewrites the bundle in place
    python tools/check_artifacts.py examples/pairing-artifacts

Deterministic and stdlib-only, like every generator in this kit: teams are synthetic
(team-aleph / team-bet), nonces are fixed, and every hash is computed by the reference
constructions in verify_vectors.py — nothing is hand-typed, so the bundle cannot drift
from the constructions it demonstrates. The bundle passes tools/check_artifacts.py
including uid re-derivation (the configs carry the flat 14-key terms inline).

What it demonstrates beyond the checker's floor:
- the role convention (first-sorted group cops the odd sub-games),
- BOTH conformant step-0 spellings in one log (own records: slim `step_zero` with a
  declaration_ref; opponent records: `system_spec` with the hardware inline),
- hardware's home in the declaration (both teams' specs, sign-then-insert block hashes),
- bare resolvable-form github_commit values, per role, per sub-game,
- the counted league fields (games_played bump, first_meeting, diversity to the winner),
- a mutual_agreement computed by the settlement consensus serialization
  (vectors/report_consensus.json) over the pairing-agreed trimmed scope.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import verify_vectors as ref  # noqa: E402

OUT = Path(__file__).resolve().parent / "pairing-artifacts"

A, B = "team-aleph", "team-bet"  # sorted: A first -> A cops the odd sub-games
TERMS = {
    "board_size": 7, "smell_grid_size": 5, "decay_per_step": 0.1, "emit_intensity": 0.9,
    "min_center_intensity": 0.5, "max_steps": 35, "barriers_max": 14, "setting": "New York",
    "hint_max_words": 15, "axis_origin_corner": "top-left", "axis_start_index": 0,
    "thief_start": [3, 3], "cop_start": [0, 0], "num_games": 6,
}
GID = ref.ref_game_id(A, B)
GUID = ref.ref_game_uid(TERMS, A, B)
LINKS = {
    "declaration": f"declaration_{GID}.json", "config": f"config_{GID}_g<NN>.json",
    "log": f"log_{GID}_g<NN>.json", "result": f"result_{GID}.json",
}
# Synthetic but resolvable-FORM commit ids: 40 hex chars, bare, one per role repo per team.
COMMITS = {A: {"cop": "a1ef0000" + "c0f" * 10 + "5c", "thief": "a1ef0001" + "7f1" * 10 + "3e"},
           B: {"cop": "b2e70000" + "abc" * 10 + "90", "thief": "b2e70001" + "de2" * 10 + "71"}}
HARDWARE = {
    A: {"os": "Windows 10", "cpu_type": "GenuineIntel x86_64", "cpu_cores": 24,
        "cpu_freq_mhz": 3418, "ram_gb": 32, "gpu_model": "Radeon RX 7900 XTX",
        "vram_gb": 24, "python": "3.13.13"},
    B: {"os": "Windows (10.0.19045)", "cpu_type": "AuthenticAMD x86_64", "cpu_cores": 24,
        "cpu_freq_mhz": 3693, "ram_gb": 31.9, "gpu_type": "RTX 3080 Ti",
        "gpu_cores_or_cuda": "cuda", "vram_gb": 12.0},
}
TZ = "Asia/Jerusalem"
# Fixed synthetic series clock: T0 + 10s per sub-game, 9s of play each. Real datetime
# arithmetic, not string formatting — sub-game 6 crosses a minute boundary, and a formatted
# seconds field would overflow to ":60" (the bug the first cut of this generator shipped).
T0 = datetime(2026, 8, 4, 1, 0, 0, tzinfo=timezone(timedelta(hours=3)))


def nonce(tag: str) -> str:
    """Deterministic per-record nonce: 32 hex chars derived from the tag."""
    return ref.canonical_hash({"nonce_tag": tag})[:32]


def sealed(payload: dict, tag: str) -> dict:
    n = nonce(tag)
    return {"payload": payload, "nonce": n, "commit": ref.ref_commit(payload, n)}


def group_block(gid: str, role_repo_order: tuple[str, str]) -> dict:
    """A declaration group block in the played shape; signature is sign-then-insert
    over the block's canonical form (the block hashed BEFORE its own signature key)."""
    cop_c, thief_c = role_repo_order
    block = {
        "group_id": gid, "group_name": gid,
        "members": [f"{gid}-member-1", f"{gid}-member-2"],
        "repos": {"cop": f"https://github.com/{gid}/cop", "thief": f"https://github.com/{gid}/thief"},
        "mcp_servers": {"cop": f"https://cop.{gid}.example/mcp",
                        "thief": f"https://thief.{gid}.example/mcp"},
        "llm_model": "template",
        "hardware_spec": HARDWARE[gid],
        "hardware_spec_sha256": ref.canonical_hash(HARDWARE[gid]),
        "github_commit": cop_c,  # the block's headline commit: this team's cop repo HEAD
        "counted_games_played": 0,
        "code_version": "1.00",
    }
    block["signature"] = "sha256:" + ref.canonical_hash(block)
    return block


def sub_game_row(n: int) -> dict:
    odd = n % 2 == 1
    cop, thief = (A, B) if odd else (B, A)          # first-sorted group cops the odds
    winner = A                                       # the campaign this mirrors swept 6-0
    result = "capture" if odd else "survival"        # odd: A's cop captures; even: A's thief survives
    score = {A: 20 if odd else 10, B: 5}
    commits = {A: COMMITS[A]["cop" if odd else "thief"],
               B: COMMITS[B]["thief" if odd else "cop"]}
    started = T0 + timedelta(seconds=10 * n)
    return {
        "sub_game_number": n,
        "roles": {cop: "police", thief: "thief"},
        "started_at": started.isoformat(),
        "ended_at": (started + timedelta(seconds=9)).isoformat(),
        "result": result, "winner_group": winner, "tie": False,
        "github_commit": commits,
        "tokens": {A: 0, B: 0},
        "score": score,
        "log_files": {A: f"log_{GID}_g{n:02d}.json", B: f"log_{GID}_g{n:02d}.json"},
        "audit": {"log_verified": True, "tampered": False},
    }


def log_doc(n: int) -> dict:
    odd = n % 2 == 1
    my_role = "police" if odd else "thief"           # written from team-aleph's side
    my_commit = COMMITS[A]["cop" if odd else "thief"]
    their_commit = COMMITS[B]["thief" if odd else "cop"]
    step_zero = sealed({  # SLIM spelling: hardware lives in the declaration it references
        "step": 0, "type": "step_zero", "declaration_ref": LINKS["declaration"],
        "group_id": A, "role": my_role, "sub_game_number": n, "github_commit": my_commit,
    }, f"g{n}-own-step0")
    first_move = sealed({  # non-ASCII on purpose — see START-HERE gate 2
        "step": 1, "state": "grid=7x7;self=[0,0];barriers=[]", "position": [0, 1],
        "move": "MOVE:E", "intent": "truth",
        "hint": "מתחיל לנוע מזרחה ברחובות — בהצלחה 🚔",
        "tokens_step": 0, "tokens_total": 0, "response_seconds": 0.4, "random_move": False,
    }, f"g{n}-own-move1")
    their_step_zero = sealed({  # SYSTEM_SPEC spelling: the reference's inline-hardware form
        "step": 0, "type": "system_spec", "spec": HARDWARE[B], "model": "none",
        "code_version": "1.00", "group_name": B, "sub_game_number": n,
        "github_commit": their_commit, "num_games_declared": 6,
    }, f"g{n}-their-step0")
    return {
        "_schema": "Per-sub-game log, PAIRING-PLAYBOOK example: sealed records in the "
                   "commit-reveal form, step-0 shown in BOTH conformant spellings (own side "
                   "slim `step_zero` + declaration_ref; opponent side inline `system_spec`). "
                   "Static team metadata lives in the declaration; join by game_uid.",
        "schema_version": "1.1", "game_id": GID, "game_uid": GUID, "links": LINKS,
        "sub_game_number": n,
        "summary": {
            "sub_game_number": n, "group_id": A, "role": my_role, "opponent_group_id": B,
            "result": "capture" if odd else "survival",
            "winner_group": A, "timezone": TZ, "steps": 1,
            "audit": "Verified OK",
        },
        "records": [step_zero, first_move],
        "opponent_records": [their_step_zero],
    }


def build() -> dict[str, dict]:
    rows = [sub_game_row(n) for n in range(1, 7)]
    totals = {g: sum(r["score"][g] for r in rows) for g in (A, B)}
    consensus_scope = {  # the pairing-AGREED trimmed scope (see PAIRING-PLAYBOOK stage 4c):
        # aggregate + rows stripped of everything two honest sides may legitimately
        # disagree on (timestamps, envelope). Serialization per vectors/report_consensus.json.
        "game_id": GID,
        "aggregate": {"total_score": totals, "sub_games_won": {A: 6, B: 0}, "ties": 0,
                      "winner_group": A, "series_tie": False},
        "sub_games": [{k: r[k] for k in
                       ("sub_game_number", "roles", "result", "winner_group", "tie", "score")}
                      for r in rows],
    }
    declaration = {
        "_schema": "Pre-game declaration, PAIRING-PLAYBOOK example: the single home for "
                   "everything fixed across the series — identity, members, repos, MCP "
                   "endpoints, BOTH teams' hardware specs, LLM model, token cap (book ch5 "
                   "step-0; §9.3.3 template list).",
        "schema_version": "1.1", "declaration_type": "pre_game_declaration",
        "report_type": "declaration",
        "game_id": GID, "game_uid": GUID, "links": LINKS, "timezone": TZ,
        "game_started_at": T0.isoformat(),
        "game_ended_at": rows[-1]["ended_at"],
        "num_sub_games": 6, "max_tokens_per_game": 200000,
        "groups": {"group_1": group_block(A, (COMMITS[A]["cop"], COMMITS[A]["thief"])),
                   "group_2": group_block(B, (COMMITS[B]["cop"], COMMITS[B]["thief"]))},
    }
    result = {
        "_schema": "Final series result, PAIRING-PLAYBOOK example: the emailed binding "
                   "report (book §9.3.3 — its full example IS the results file). Static team "
                   "metadata is NOT repeated here; it lives in the declaration.",
        "schema_version": "1.1", "report_type": "final_game_result",
        "game_id": GID, "game_uid": GUID,
        # The result additionally carries both teams' repo links (book rule 49) — the one
        # artifact the lecturer reads must be able to reach all four repos on its own.
        "links": {**LINKS,
                  "github": {g: {"cop": f"https://github.com/{g}/cop",
                                 "thief": f"https://github.com/{g}/thief"}
                             for g in (A, B)}},
        "timezone": TZ,
        "groups": [A, B], "num_sub_games": 6,
        "sub_games": rows,
        "final_result": {
            "total_score": totals, "sub_games_won": {A: 6, B: 0}, "ties": 0,
            "winner_group": A, "series_tie": False,
            "tokens_total_series": {A: 0, B: 0},
            # league fields, ARMED because this mirrors a counted series:
            "games_played_including_this": {A: 1, B: 1},
            "first_meeting_between_groups": True,
            "diversity_reward_applied": {A: True, B: False},
        },
        "mutual_agreement": {
            "sha256": ref.ref_report_consensus_signature(consensus_scope),
            "confirmed": True,
        },
    }
    files: dict[str, dict] = {f"declaration_{GID}.json": declaration,
                              f"result_{GID}.json": result}
    for n in range(1, 7):
        files[f"config_{GID}_g{n:02d}.json"] = {
            "_schema": "Per-sub-game config artifact, PAIRING-PLAYBOOK example: the flat "
                       "signed 14-key terms, inline — which is what lets "
                       "tools/check_artifacts.py RE-DERIVE the game_uid (WARNINGS §2).",
            "schema_version": "1.1", "game_id": GID, "game_uid": GUID, "links": LINKS,
            "sub_game_number": n, "terms": TERMS,
            "terms_sha256": ref.canonical_hash(TERMS),
        }
        files[f"log_{GID}_g{n:02d}.json"] = log_doc(n)
    return files


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, doc in sorted(build().items()):
        (OUT / name).write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n",
                                encoding="utf-8")
        print(f"wrote {name}")
    print(f"\n{len(build())} artifacts -> {OUT}")
    print("verify: python tools/check_artifacts.py examples/pairing-artifacts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
