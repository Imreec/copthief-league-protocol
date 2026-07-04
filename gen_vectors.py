"""Regenerate every fixture under ``vectors/`` from the reference constructions.

Deterministic: CI runs this and fails on any diff, so the committed fixtures always match the
reference implementation in ``verify_vectors.py``. The §6.2/§6.3/canonical values are unchanged
from v0.1 and byte-identical to what the EX06 implementation produced; §6.4 values are v0.2
(new construction, see SPEC changelog).
"""

from __future__ import annotations

import json
from pathlib import Path

from verify_vectors import (
    canonical_bytes,
    canonical_hash,
    ref_commit,
    ref_derive_starts,
    ref_joint_seed,
    ref_share_commit,
    ref_state_hash,
)

VECTORS = Path(__file__).parent / "vectors"

# --- canonical JSON edge cases -------------------------------------------------------------
canon_cases = [
    {"b": 1, "a": [2, 1], "nested": {"z": "x", "y": [0]}},
    {"unicode": "שלום", "ascii": "hi"},
    {"empty_list": [], "empty_obj": {}, "null": None, "bool": True},
    {"report_type": "bonus_game", "totals_by_group": {"Team-A": 80, "Team-B": 60}},
    {"astral": "🙂", "note": "surrogate-pair escaping (SPEC §2)"},
]
canonical_json = {
    "description": "Canonical JSON form: sort_keys, separators (',',':'), ensure_ascii "
    "(astral -> surrogate pairs), UTF-8, floats rejected (see negative.json)",
    "vectors": [
        {"object": o, "canonical": canonical_bytes(o).decode(), "sha256": canonical_hash(o)}
        for o in canon_cases
    ],
}

# --- position commits ------------------------------------------------------------------------
commit_cases = [
    ([2, 3], "abc123"),
    ([0, 0], "00"),
    ([9, 9], "deadbeefcafe"),
    ([4, 7], "f" * 32),
]
position_commit = {
    "description": "SHA-256 position commitments: sha256(canonical({'nonce':s,'pos':[r,c]}))",
    "vectors": [
        {
            "pos": pos,
            "nonce": nonce,
            "preimage": canonical_bytes({"nonce": nonce, "pos": pos}).decode(),
            "sha256": ref_commit(pos, nonce),
        }
        for pos, nonce in commit_cases
    ],
}

# --- state hashes ----------------------------------------------------------------------------
state_cases: list[tuple[list[list[int]], str, int, str | None]] = [
    ([[1, 1]], "cop", 4, None),
    ([], "thief", 0, None),
    ([[2, 2], [0, 1]], "thief", 13, "unsorted input -> sorted preimage"),
    ([], "cop", 49, None),
    (
        [],
        "cop",
        2,
        "TERMINAL ply: capture on the cop's 2nd ply — turn stays on the mover (SPEC §6.3); "
        "reproduces the final frame of an EX06 live sub-game",
    ),
]
state_hash = {
    "description": "Common-state hashes: sha256(canonical({'barriers':sorted,'move_count':n,'turn':s})). "
    "Terminal-ply rule: turn stays on the mover of a game-ending ply.",
    "vectors": [
        {
            "barriers": b,
            "turn": t,
            "move_count": mc,
            **({"note": note} if note else {}),
            "sha256": ref_state_hash(b, t, mc),
        }
        for b, t, mc, note in state_cases
    ],
}

# --- seed -> starts (v0.2 construction) ------------------------------------------------------
starts_vectors = []
for seed in ["league-spec-v0.2-example", "0123456789abcdef"]:
    for n in [5, 8, 10]:
        for index in [0, 1, 2, 16, 17]:  # 16/17 = sub-game 1 attempts 0/1 (index = g*16 + a)
            cop, thief, draws = ref_derive_starts(seed, index, n)
            starts_vectors.append(
                {"seed": seed, "index": index, "n": n, "cop": cop, "thief": thief, "draws": draws}
            )
derive_starts = {
    "description": "v0.2 seed-derived start cells: for draw=0,1,...: digest=sha256(f'{seed}:{index}:{draw}'); "
    "cop=int(digest[0:4])%n^2, thief=int(digest[4:8])%n^2; accept iff chebyshev>=d_min where "
    "d_min=min(max(ceil(n/3),2),n-1); cell i -> [i//n, i%n]. Re-runs: index = game*16 + attempt.",
    "vectors": starts_vectors,
}

# --- match card ------------------------------------------------------------------------------
CARD = {
    "agreement": {
        "protocol": "league/0.2",
        "match_id": "2026-08-01-aleph-vs-bet",
        "groups": {"group_1": "Team-Aleph", "group_2": "Team-Bet"},
        "grid": [10, 10],
        "rounds": 25,
        "num_games": 6,
        "swap_at": 3,
        "max_barriers": 0,
        "disclosure": "A",
        "scent_k": None,
        "stage": "demo",
        "report_email": "league-reports@example.com",
        "seed": "league-spec-v0.2-example",
        "timeouts": {"per_ply_seconds": 120, "per_subgame_seconds": 1800, "max_messages": 200},
    },
    "transport": {
        "urls": {
            "group_1_cop": "https://aleph.example/cop/mcp",
            "group_1_thief": "https://aleph.example/thief/mcp",
            "group_2_cop": "https://bet.example/cop/mcp",
            "group_2_thief": "https://bet.example/thief/mcp",
        },
        "scheduled_utc": "2026-08-01T18:00:00Z",
    },
}
match_card = {
    "description": "config_sha256 = sha256(canonical(card['agreement'])) — the 'transport' part is "
    "NOT hashed (SPEC §4.1), so tunnel restarts / rescheduling never brick the handshake.",
    "card": CARD,
    "agreement_canonical": canonical_bytes(CARD["agreement"]).decode(),
    "config_sha256": canonical_hash(CARD["agreement"]),
}

# --- joint seed ------------------------------------------------------------------------------
seed_cases = [
    ("a3f1c2d4e5b60718293a4b5c6d7e8f90", "00ff00ff00ff00ff00ff00ff00ff00ff"),
    ("deadbeef", "cafebabe"),
]
joint_seed = {
    "description": "SPEC §4.2 trustless coin flip: commit_i = sha256(canonical({'seed_share': r_i})); "
    "seed = sha256(canonical({'shares': [r_group_1, r_group_2]}))",
    "vectors": [
        {
            "share_group_1": r1,
            "share_group_2": r2,
            "commit_group_1": ref_share_commit(r1),
            "commit_group_2": ref_share_commit(r2),
            "seed": ref_joint_seed(r1, r2),
        }
        for r1, r2 in seed_cases
    ],
}

# --- negative vectors ------------------------------------------------------------------------
negative = {
    "description": "Inputs a conformant implementation MUST reject (floats, SPEC §2) and "
    "commit-binding pairs whose hashes MUST differ (SPEC §6.2).",
    "reject_floats": [
        {"x": 7.5},
        {"totals": {"a": 2.0}},
        {"nested": [1, [2, [3.5]]]},
        {"ok": 1, "bad": [True, 0.1]},
    ],
    "binding_pairs": [
        {"pos_a": [2, 3], "nonce_a": "abc123", "pos_b": [2, 3], "nonce_b": "abc124"},
        {"pos_a": [2, 3], "nonce_a": "abc123", "pos_b": [3, 2], "nonce_b": "abc123"},
    ],
}

files = {
    "canonical_json.json": canonical_json,
    "position_commit.json": position_commit,
    "state_hash.json": state_hash,
    "derive_starts.json": derive_starts,
    "match_card.json": match_card,
    "joint_seed.json": joint_seed,
    "negative.json": negative,
}
for name, payload in files.items():
    (VECTORS / name).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    n_v = len(payload.get("vectors", payload.get("reject_floats", [])))
    print(f"wrote {name}")
print("done")
