"""League-protocol conformance checker — stdlib only, no dependencies.

Re-implements every hash construction from SPEC.md (v0.2) and verifies the fixtures under
``vectors/``, including the NEGATIVE fixtures (inputs your implementation must reject).

Two ways to use it:

1. ``python verify_vectors.py`` — confirms the reference constructions reproduce every fixture.
2. Port the ``ref_*`` functions' *behavior* into your own codebase, then point your test suite at
   the same JSON fixtures. If your implementation reproduces every vector (and rejects every
   negative), your hashes are byte-compatible with every other conformant team.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

VECTORS = Path(__file__).parent / "vectors"


# --- reference constructions (SPEC.md §2, §4.2, §6) ---------------------------------------


def _reject_floats(obj: object) -> None:
    """SPEC §2: floats are forbidden anywhere in a hashed object (repr drift across languages)."""
    if type(obj) is float:
        msg = "floats are forbidden in hashed objects (SPEC §2)"
        raise ValueError(msg)
    if isinstance(obj, dict):
        for k, v in obj.items():
            _reject_floats(k)
            _reject_floats(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _reject_floats(v)


def canonical_bytes(obj: object) -> bytes:
    """SPEC §2: sorted keys, no whitespace, \\uXXXX-escaped non-ASCII, UTF-8. Rejects floats."""
    _reject_floats(obj)
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()


def canonical_hash(obj: object) -> str:
    return hashlib.sha256(canonical_bytes(obj)).hexdigest()


def ref_commit(pos: list[int], nonce: str) -> str:
    """SPEC §6.2: position commitment (key order irrelevant — canonicalization sorts)."""
    return canonical_hash({"nonce": nonce, "pos": pos})


def ref_state_hash(barriers: list[list[int]], turn: str, move_count: int) -> str:
    """SPEC §6.3: common-state hash (barriers deduped + sorted, row-major)."""
    frame = {
        "barriers": sorted([list(b) for b in {tuple(b) for b in barriers}]),
        "turn": turn,
        "move_count": move_count,
    }
    return canonical_hash(frame)


def ref_derive_starts(seed: str, index: int, n: int) -> tuple[list[int], list[int], int]:
    """SPEC §6.4 (v0.3): 4 bytes per cell, min-Chebyshev deterministic re-draw, bounded.

    Returns (cop, thief, draws) where ``draws`` is the accepted draw counter value
    (64 signals the deterministic opposite-corners fallback — never hit by any fixture).
    """
    cells = n * n
    d_min = min(max(-(-n // 3), 2), n - 1)  # ceil(n/3), clamped to [2, n-1]
    for draw in range(64):
        digest = hashlib.sha256(f"{seed}:{index}:{draw}".encode()).digest()
        cop = int.from_bytes(digest[0:4], "big") % cells
        thief = int.from_bytes(digest[4:8], "big") % cells
        cop_rc = [cop // n, cop % n]
        thief_rc = [thief // n, thief % n]
        if max(abs(cop_rc[0] - thief_rc[0]), abs(cop_rc[1] - thief_rc[1])) >= d_min:
            return cop_rc, thief_rc, draw
    return [0, 0], [n - 1, n - 1], 64  # provably bounded fallback (corners: distance n-1 >= d_min)


def ref_share_commit(share: str) -> str:
    """SPEC §4.2: commitment to one team's seed share."""
    return canonical_hash({"seed_share": share})


def ref_joint_seed(share_group_1: str, share_group_2: str) -> str:
    """SPEC §4.2: the joint seed from both revealed shares (group_1 first)."""
    return canonical_hash({"shares": [share_group_1, share_group_2]})


# --- fixture checks -----------------------------------------------------------------------


def check(name: str, ok: bool, detail: str = "") -> bool:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{('  ' + detail) if detail and not ok else ''}")
    return ok


def _load(name: str) -> dict:
    return json.loads((VECTORS / name).read_text(encoding="utf-8"))


def run() -> int:
    failures = 0

    print("canonical_json.json")
    for i, v in enumerate(_load("canonical_json.json")["vectors"]):
        got = canonical_bytes(v["object"]).decode()
        ok = got == v["canonical"] and canonical_hash(v["object"]) == v["sha256"]
        failures += not check(f"canonical #{i}", ok, f"got {got!r}")

    print("position_commit.json")
    for i, v in enumerate(_load("position_commit.json")["vectors"]):
        got = ref_commit(v["pos"], v["nonce"])
        pre = canonical_bytes({"nonce": v["nonce"], "pos": v["pos"]}).decode()
        ok = got == v["sha256"] and pre == v["preimage"]
        failures += not check(f"commit #{i} pos={v['pos']}", ok, f"got {got}")

    print("state_hash.json")
    for i, v in enumerate(_load("state_hash.json")["vectors"]):
        got = ref_state_hash(v["barriers"], v["turn"], v["move_count"])
        failures += not check(f"state #{i} mc={v['move_count']}", got == v["sha256"], f"got {got}")

    print("derive_starts.json")
    for i, v in enumerate(_load("derive_starts.json")["vectors"]):
        cop, thief, draws = ref_derive_starts(v["seed"], v["index"], v["n"])
        ok = cop == v["cop"] and thief == v["thief"] and draws == v["draws"]
        failures += not check(f"starts #{i} n={v['n']} index={v['index']}", ok, f"got {cop},{thief},{draws}")

    print("match_card.json")
    mc = _load("match_card.json")
    got = canonical_hash(mc["card"]["agreement"])
    got_bytes = canonical_bytes(mc["card"]["agreement"]).decode()
    ok = got == mc["config_sha256"] and got_bytes == mc["agreement_canonical"]
    failures += not check("agreement config_sha256", ok, f"got {got}")

    print("joint_seed.json")
    for i, v in enumerate(_load("joint_seed.json")["vectors"]):
        ok = (
            ref_share_commit(v["share_group_1"]) == v["commit_group_1"]
            and ref_share_commit(v["share_group_2"]) == v["commit_group_2"]
            and ref_joint_seed(v["share_group_1"], v["share_group_2"]) == v["seed"]
        )
        failures += not check(f"joint seed #{i}", ok)

    print("negative.json")
    neg = _load("negative.json")
    for i, obj in enumerate(neg["reject_floats"]):
        try:
            canonical_bytes(obj)
            failures += not check(f"reject float #{i}", False, "was NOT rejected")
        except ValueError:
            check(f"reject float #{i}", True)
    for i, p in enumerate(neg["binding_pairs"]):
        a = ref_commit(p["pos_a"], p["nonce_a"])
        b = ref_commit(p["pos_b"], p["nonce_b"])
        failures += not check(f"binding pair #{i} commits differ", a != b, "hashes collided")

    print(f"\n{'ALL VECTORS PASS' if failures == 0 else f'{failures} FAILURE(S)'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(run())
