"""League-protocol conformance checker — stdlib only, no dependencies.

Re-implements every hash construction from SPEC.md and verifies the fixtures under
``vectors/``. Two ways to use it:

1. ``python verify_vectors.py`` — confirms the reference constructions reproduce every
   fixture (sanity check that your copy of the vectors is intact).
2. Port the four ``ref_*`` functions' *behavior* into your own codebase, then point your
   test suite at the same JSON fixtures. If your implementation reproduces every vector,
   your hashes are byte-compatible with every other conformant team.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

VECTORS = Path(__file__).parent / "vectors"


# --- reference constructions (SPEC.md §2, §6) --------------------------------------------


def canonical_bytes(obj: object) -> bytes:
    """SPEC §2: sorted keys, no whitespace, \\uXXXX-escaped non-ASCII, UTF-8."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()


def canonical_hash(obj: object) -> str:
    return hashlib.sha256(canonical_bytes(obj)).hexdigest()


def ref_commit(pos: list[int], nonce: str) -> str:
    """SPEC §6.2: position commitment."""
    return canonical_hash({"pos": pos, "nonce": nonce})


def ref_state_hash(barriers: list[list[int]], turn: str, move_count: int) -> str:
    """SPEC §6.3: common-state hash (barriers deduped + sorted, row-major)."""
    frame = {
        "barriers": sorted([list(b) for b in {tuple(b) for b in barriers}]),
        "turn": turn,
        "move_count": move_count,
    }
    return canonical_hash(frame)


def ref_derive_starts(seed: str, index: int, n: int) -> tuple[list[int], list[int]]:
    """SPEC §6.4: seed-derived start cells."""
    digest = hashlib.sha256(f"{seed}:{index}".encode()).digest()
    cells = n * n
    cop = digest[0] % cells
    thief = digest[1] % cells
    if thief == cop:
        thief = (thief + 1) % cells
    return [cop // n, cop % n], [thief // n, thief % n]


# --- fixture checks -----------------------------------------------------------------------


def check(name: str, ok: bool, detail: str = "") -> bool:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{('  ' + detail) if detail and not ok else ''}")
    return ok


def run() -> int:
    failures = 0

    data = json.loads((VECTORS / "canonical_json.json").read_text(encoding="utf-8"))
    print("canonical_json.json")
    for i, v in enumerate(data["vectors"]):
        got_bytes = canonical_bytes(v["object"]).decode()
        ok = got_bytes == v["canonical"] and canonical_hash(v["object"]) == v["sha256"]
        failures += not check(f"canonical #{i}", ok, f"got {got_bytes!r}")

    data = json.loads((VECTORS / "position_commit.json").read_text(encoding="utf-8"))
    print("position_commit.json")
    for i, v in enumerate(data["vectors"]):
        got = ref_commit(v["pos"], v["nonce"])
        pre = canonical_bytes({"pos": v["pos"], "nonce": v["nonce"]}).decode()
        ok = got == v["sha256"] and pre == v["preimage"]
        failures += not check(f"commit #{i} pos={v['pos']}", ok, f"got {got}")

    data = json.loads((VECTORS / "state_hash.json").read_text(encoding="utf-8"))
    print("state_hash.json")
    for i, v in enumerate(data["vectors"]):
        got = ref_state_hash(v["barriers"], v["turn"], v["move_count"])
        ok = got == v["sha256"]
        failures += not check(f"state #{i} move_count={v['move_count']}", ok, f"got {got}")

    data = json.loads((VECTORS / "derive_starts.json").read_text(encoding="utf-8"))
    print("derive_starts.json")
    for i, v in enumerate(data["vectors"]):
        cop, thief = ref_derive_starts(v["seed"], v["index"], v["n"])
        ok = cop == v["cop"] and thief == v["thief"]
        failures += not check(f"starts #{i} n={v['n']} index={v['index']}", ok, f"got {cop},{thief}")

    print(f"\n{'ALL VECTORS PASS' if failures == 0 else f'{failures} FAILURE(S)'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(run())
