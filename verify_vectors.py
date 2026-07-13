"""League interop-kit conformance checker — stdlib only, no dependencies.

Re-implements every byte-level construction that two independent implementations of the
official assignment (Dr. Yoram Segal, *Distributed Cops-and-Robbers over a Peer-to-Peer
Network*, book v3.0.0) MUST agree on, and verifies the fixtures under ``vectors/``.

This kit is NOT the game spec — the book is. It pins only the serialization details the book
leaves to inter-team agreement, which are exactly where two clean-room codebases silently
diverge and lose a match. See SPEC.md for the mapping to the book's chapters.

Two ways to use it:

1. ``python verify_vectors.py`` — confirms the reference constructions reproduce every fixture.
2. Port the ``ref_*`` functions' *behavior* into your own codebase, then point your test suite at
   the same JSON fixtures. If your implementation reproduces every CORE vector, your hashes are
   byte-compatible with every other conformant team: your agreement signature will verify, both
   sides derive the same ``game_uid``, and the post-game audit of your revealed log (which the
   opponent re-hashes) passes instead of raising a false ``tamper_forfeit``.

The ENHANCEMENT vectors cover opt-in mechanics that are *not* required by the book (SPEC Appendix
A); a pair of teams conforms to them only if they agree to and both sign them into config/game.json.
"""

from __future__ import annotations

import hashlib
import json
import sys
import uuid
from pathlib import Path

VECTORS = Path(__file__).parent / "vectors"


# --- the one canonical form (book ch.5; reference domain/crypto.py) -----------------------
#
# json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
#
# Note ensure_ascii=FALSE: non-ASCII (Hebrew hints, emoji, non-English map areas) is emitted as
# native UTF-8, NOT \uXXXX-escaped. An implementation that escapes will produce a different hash
# for any payload containing non-ASCII — and since the opponent re-hashes your revealed payloads
# (which include your free-language `hint`) at audit, that mismatch reads as tampering and voids
# the match for BOTH sides. This is the single most important fact in this kit.


def _canonical_str(obj: object) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def canonical_bytes(obj: object) -> bytes:
    return _canonical_str(obj).encode("utf-8")


def canonical_hash(obj: object) -> str:
    return hashlib.sha256(canonical_bytes(obj)).hexdigest()


# --- CORE constructions (must match cross-team) ------------------------------------------


def ref_commit(payload: dict, nonce: str) -> str:
    """Per-step / agreement commit: SHA-256 over canonical(payload) with the nonce pipe-appended.

    commit = SHA256( canonical_json(payload) + "|" + nonce )

    The nonce is NOT inside the hashed object; it is concatenated to the canonical string. Each
    peer seals its own payload and sends only the commit; nonces are revealed at the end-of-game
    audit, where BOTH peers re-hash every revealed (payload, nonce) and must reproduce the commit.
    """
    return hashlib.sha256(f"{_canonical_str(payload)}|{nonce}".encode()).hexdigest()


def ref_terms_signature(terms: dict, nonce: str) -> str:
    """Pre-game agreement signature — identical construction to a commit, over the agreed terms.

    The opponent recomputes it over the terms it received (which must value-equal its own) using
    the signer's nonce; any canonicalization difference (ensure_ascii, float repr, key naming)
    makes the signature fail and the peers refuse to start.
    """
    return ref_commit(terms, nonce)


def ref_game_uid(terms: dict, group_a: str, group_b: str) -> str:
    """Deterministic shared game id both peers reproduce without a round-trip.

    game_uid = UUID( SHA256( canonical(terms) + "|" + "|".join(sorted([group_a, group_b])) )[:16] )
    """
    pair = sorted([group_a, group_b])
    seed = f"{_canonical_str(terms)}|{'|'.join(pair)}"
    return str(uuid.UUID(bytes=hashlib.sha256(seed.encode()).digest()[:16]))


def ref_smell_emit(center, intensity, grid_size, board_size):
    """Radial scent emission around a cell (book ch.4; reference domain/smell.py).

    half = grid_size // 2 ; falloff = intensity / (half + 1)
    value(cell) = round(max(0.0, intensity - falloff * chebyshev(cell, center)), 3)

    Returns the wire/snapshot form {"r,c": value} for cells inside the board with value > 0.
    """
    half = grid_size // 2
    falloff = intensity / (half + 1)
    out: dict[str, float] = {}
    for dr in range(-half, half + 1):
        for dc in range(-half, half + 1):
            r, c = center[0] + dr, center[1] + dc
            if 0 <= r < board_size and 0 <= c < board_size:
                value = round(max(0.0, intensity - falloff * max(abs(dr), abs(dc))), 3)
                if value > 0.0:
                    out[f"{r},{c}"] = value
    return out


def ref_smell_decay(values: dict, decay: float) -> dict:
    """One game-step decay: every intensity drops by the constant, clamped at 0 (rounded to 3)."""
    return {k: round(max(0.0, v - decay), 3) for k, v in values.items()}


# --- ENHANCEMENT constructions (opt-in; NOT required by the book) -------------------------


def ref_share_commit(share: str) -> str:
    """SPEC Appendix A — joint-seed coin flip: commitment to one team's seed share."""
    return canonical_hash({"seed_share": share})


def ref_joint_seed(share_group_1: str, share_group_2: str) -> str:
    """SPEC Appendix A — the joint seed from both revealed shares (group_1 first)."""
    return canonical_hash({"shares": [share_group_1, share_group_2]})


def ref_derive_starts(seed: str, index: int, n: int) -> tuple[list[int], list[int], int]:
    """SPEC Appendix A — optional seeded asymmetric starts (a fairness alternative to the book's
    fixed configured starts). 4 digest bytes per cell, minimum-Chebyshev deterministic re-draw."""
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
    return [0, 0], [n - 1, n - 1], 64


# --- fixture checks -----------------------------------------------------------------------


def check(name: str, ok: bool, detail: str = "") -> bool:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{('  ' + detail) if detail and not ok else ''}")
    return ok


def _load(name: str) -> dict:
    return json.loads((VECTORS / name).read_text(encoding="utf-8"))


def run() -> int:
    failures = 0

    print("[CORE] canonical_json.json")
    for i, v in enumerate(_load("canonical_json.json")["vectors"]):
        got = _canonical_str(v["object"])
        ok = got == v["canonical"] and canonical_hash(v["object"]) == v["sha256"]
        failures += not check(f"canonical #{i} ({v.get('note', '')})", ok, f"got {got!r}")

    print("[CORE] commit_reveal.json")
    cr = _load("commit_reveal.json")
    for i, v in enumerate(cr["vectors"]):
        got = ref_commit(v["payload"], v["nonce"])
        failures += not check(f"commit #{i} ({v.get('note', '')})", got == v["commit"], f"got {got}")
    # The release's three published commit constructions over the same sealed record (the audit-
    # snippet form consumes only its nonce|move fields) — all pinned and mutually distinct
    # (SPEC 'Commit-reveal': the contradiction, resolved).
    dv = cr["divergent_forms"]
    got_ref = ref_commit(dv["payload"], dv["nonce"])
    got_ch5 = canonical_hash({**dv["payload"], "nonce": dv["nonce"]})
    got_audit = hashlib.sha256(f"{dv['nonce']}|{dv['payload']['move']}".encode()).hexdigest()
    ok = (
        got_ref == dv["reference_form"]
        and got_ch5 == dv["book_ch5_listing_form"]
        and got_audit == dv["book_audit_snippet_form"]
        and len({got_ref, got_ch5, got_audit}) == 3
    )
    failures += not check("divergent forms: pinned + mutually distinct", ok)

    print("[CORE] terms_signature.json")
    for i, v in enumerate(_load("terms_signature.json")["vectors"]):
        got = ref_terms_signature(v["terms"], v["nonce"])
        failures += not check(f"terms signature #{i}", got == v["signature"], f"got {got}")

    print("[CORE] game_uid.json")
    for i, v in enumerate(_load("game_uid.json")["vectors"]):
        got = ref_game_uid(v["terms"], v["group_a"], v["group_b"])
        failures += not check(f"game_uid #{i}", got == v["game_uid"], f"got {got}")

    print("[CORE] pheromone.json")
    ph = _load("pheromone.json")
    for i, v in enumerate(ph["emit"]):
        got = ref_smell_emit(v["center"], v["intensity"], v["grid_size"], v["board_size"])
        failures += not check(f"smell emit #{i}", got == v["field"], f"got {got}")
    for i, v in enumerate(ph["decay"]):
        got = ref_smell_decay(v["before"], v["decay"])
        failures += not check(f"smell decay #{i}", got == v["after"], f"got {got}")

    print("[ENH] joint_seed.json")
    for i, v in enumerate(_load("joint_seed.json")["vectors"]):
        ok = (
            ref_share_commit(v["share_group_1"]) == v["commit_group_1"]
            and ref_share_commit(v["share_group_2"]) == v["commit_group_2"]
            and ref_joint_seed(v["share_group_1"], v["share_group_2"]) == v["seed"]
        )
        failures += not check(f"joint seed #{i}", ok)

    print("[ENH] derive_starts.json")
    for i, v in enumerate(_load("derive_starts.json")["vectors"]):
        cop, thief, draws = ref_derive_starts(v["seed"], v["index"], v["n"])
        ok = cop == v["cop"] and thief == v["thief"] and draws == v["draws"]
        failures += not check(f"starts #{i} n={v['n']} index={v['index']}", ok, f"got {cop},{thief},{draws}")

    print(f"\n{'ALL VECTORS PASS' if failures == 0 else f'{failures} FAILURE(S)'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(run())
