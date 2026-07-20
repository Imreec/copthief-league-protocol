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


def ref_report_consensus_signature(report: dict) -> str:
    """Settlement consensus signature (reference report_writer.py, verified at sha 960499fd).

    A SECOND canonical form, unlike every other hash in the release: sort_keys=True,
    ensure_ascii=False, but DEFAULT (spaced) separators — json.dumps' (', ', ': ').
    The signature is computed over the report BEFORE the Hebrew signature key
    is inserted (sign-then-insert), so the field is excluded from its own preimage.
    Verify an emailed report by popping the signature key, re-serializing spaced,
    and re-hashing. Found by Alon's team (alonengel / anrbj666).
    """
    spaced = json.dumps(report, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(spaced.encode("utf-8")).hexdigest()


# --- LOCKED-MODEL DECLARATIONS (SPEC section 7) -------------------------------------------
#
# One document schema serving three named-parameter families. A peer that wants to bind a
# choice publishes a doc, hashes it, and declares the hash at negotiate time as
# "<family>_sha256". The doc itself never crosses the wire — only the hash — so the schema
# exists to make two teams' hashes COMPARABLE. Two correct implementations of the same model
# that hash different field sets refuse each other for no reason; that is the failure this
# section removes.

LOCK_FAMILIES = ("scent_model", "wire_shape", "info_mode")
LOCK_DOC_KEYS = ("family", "name", "params", "example")


def ref_lock_doc(family: str, name: str, params: dict, example: dict) -> dict:
    """A locked-model doc: exactly four keys, canonicalized by the section-2 form.

    Keeping the key set closed is the whole point — `params` and `example` carry everything
    model-specific, so the envelope is identical across families and versions.
    """
    if family not in LOCK_FAMILIES:
        raise ValueError(f"unknown family {family!r}; expected one of {LOCK_FAMILIES}")
    return {"family": family, "name": name, "params": params, "example": example}


def ref_lock_hash(doc: dict) -> str:
    """The declared value: SHA-256 over the compact canonical doc (section 2).

    Same construction Alon's team already ships as `scent_model_sha256` — a bare hash over a
    compact-canonical spec dict. The kit adds only the field set underneath it.
    """
    if tuple(sorted(doc)) != tuple(sorted(LOCK_DOC_KEYS)):
        raise ValueError(f"lock doc must have exactly {LOCK_DOC_KEYS}, got {tuple(sorted(doc))}")
    return canonical_hash(doc)


def ref_lock_decision(ours: str | None, theirs: str | None) -> str:
    """The refusal rule: refuse ONLY when both peers declare a family and disagree.

    Omission is never refusal. A peer that declares nothing (the unmodified reference peer
    declares nothing at all) stays playable — a lock that fail-fasts on a missing declaration
    cannot play the lecturer's own tooling, which is a self-inflicted forfeit, not a safeguard.
    """
    if ours is None or theirs is None:
        return "play"
    return "play" if ours == theirs else "refuse"


# --- book-v3 scent model (PROPOSED; SPEC section 5.1) -------------------------------------
#
# The book's ch.4 model, as distinct from the reference's (section 5). Printed figure 4 is a
# 5x5 emission kernel; the update is multiplicative and runs once per FULL turn.

BOOK_KERNEL = (
    (0.04, 0.14, 0.20, 0.14, 0.04),
    (0.14, 0.42, 0.62, 0.42, 0.14),
    (0.20, 0.62, 0.90, 0.62, 0.20),
    (0.14, 0.42, 0.62, 0.42, 0.14),
    (0.04, 0.14, 0.20, 0.14, 0.04),
)


def ref_book_kernel_delta(dr: int, dc: int) -> float:
    """The deposit at offset (dr, dc) from the emitting agent — a VERBATIM table lookup.

    Not a closed form on purpose. The printed values are reproducible by a radial Gaussian,
    but only inside a narrow sigma window that the book never prints, and the window differs
    by quantization rule (see `closed_form_probe` in vectors/scent_book_v3.json). Two teams
    each fitting their own Gaussian get different fields; the printed table is the only thing
    both can land on.
    """
    if abs(dr) > 2 or abs(dc) > 2:
        return 0.0
    return BOOK_KERNEL[dr + 2][dc + 2]


def ref_book_update(tau: float, delta: float, rho: float, center_intensity: float) -> float:
    """One cell, one full turn: tau' = clamp((1 - rho) * tau + delta, 0, center_intensity).

    Evaluation order is load-bearing and pinned exactly as written. The model does NO
    rounding, so the algebraically-equivalent `tau - rho * tau + delta` differs from this in
    the last bit for many inputs (75 of 534 probed) — enough to break a byte-comparison of two
    recomputed fields. Compute it in this order, or compare fields with a tolerance.

    The upper clamp is NOT in the book's printed formula, which shows only `max(0, ...)`; it
    comes from the book's own declaration that tau is a continuous value in [0, 0.9]. Without
    it a cell that decays and is re-deposited on exceeds the centre intensity (the 1.43 case).
    """
    return min(max(0.0, (1 - rho) * tau + delta), center_intensity)


def ref_book_full_turn(field: dict, center, rho: float, center_intensity: float,
                       board_size: int) -> dict:
    """One FULL turn of one agent's own trail: decay everything, deposit the kernel, clamp.

    Cadence is the book's: the update runs once per full turn, after both agents have moved —
    not once per half-turn step. Decay and deposit are a single expression, so decay applies
    to the pre-existing field only (decay-then-deposit). The reference model does the reverse
    (deposit, then decay before sending), which is one of the two models' real divergences.

    Each side recomputes the rival's field from revealed actions; nothing is received, so
    there is no receiver-side decay pass.
    """
    cells = set(field) | {
        f"{center[0] + dr},{center[1] + dc}"
        for dr in range(-2, 3) for dc in range(-2, 3)
        if 0 <= center[0] + dr < board_size and 0 <= center[1] + dc < board_size
    }
    out: dict[str, float] = {}
    # Sorted by (row, col): set iteration order varies between runs, and while key order cannot
    # change a hash (canonicalization sorts), it would make the committed fixture drift in CI.
    for key in sorted(cells, key=lambda k: tuple(int(x) for x in k.split(","))):
        r, c = (int(x) for x in key.split(","))
        value = ref_book_update(field.get(key, 0.0), ref_book_kernel_delta(r - center[0], c - center[1]),
                                rho, center_intensity)
        if value > 0.0:
            out[key] = value
    return out


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

    print("[CORE] report_consensus.json")
    rc = _load("report_consensus.json")
    sig_key = rc["signature_key"]
    for i, v in enumerate(rc["vectors"]):
        got = ref_report_consensus_signature(v["report"])
        ok = got == v["signature"]
        # sign-then-insert: popping the signature key from the signed report re-yields the preimage
        stripped = {k: val for k, val in v["signed_report"].items() if k != sig_key}
        ok = ok and stripped == v["report"] and v["signed_report"][sig_key] == v["signature"]
        # the compact (§2) form must NOT reproduce the signature — the spaced form is load-bearing
        ok = ok and canonical_hash(v["report"]) == v["compact_form_sha256"] != v["signature"]
        failures += not check(f"consensus signature #{i} ({v.get('note', '')})", ok, f"got {got}")

    print("[CORE] locked_model.json")
    lm = _load("locked_model.json")
    schema_keys = tuple(lm["doc_schema"]["keys"])
    for entry in lm["registered"]:
        doc = entry["doc"]
        ok = (
            tuple(sorted(doc)) == tuple(sorted(schema_keys))
            and doc["family"] in lm["doc_schema"]["families"]
            and entry["declared_as"] == f"{doc['family']}_sha256"
            and ref_lock_hash(doc) == entry["sha256"]
        )
        failures += not check(f"lock doc {doc['family']}/{doc['name']}", ok)
    # Distinct registrations must hash distinctly, or a lock cannot tell them apart.
    hashes = [e["sha256"] for e in lm["registered"]]
    failures += not check("registrations mutually distinct", len(set(hashes)) == len(hashes))
    for i, v in enumerate(lm["refusal_rule"]):
        got = ref_lock_decision(v["ours"], v["theirs"])
        failures += not check(f"refusal rule #{i} ({v['note']})", got == v["decision"], f"got {got}")
    # Omission must never refuse — the property that keeps no-doc peers playable.
    silent = [v for v in lm["refusal_rule"] if v["ours"] is None or v["theirs"] is None]
    failures += not check("omission is never refusal",
                          bool(silent) and all(v["decision"] == "play" for v in silent))

    print("[PROPOSED] scent_book_v3.json")
    sb = _load("scent_book_v3.json")
    rho = sb["field_walk"]["rho"]
    peak = sb["field_walk"]["center_intensity"]
    board = sb["field_walk"]["board_size"]
    failures += not check("kernel matches book figure 4 verbatim",
                          sb["kernel"] == [list(r) for r in BOOK_KERNEL])
    failures += not check("model doc hashes as registered",
                          ref_lock_hash(sb["model"]) == next(
                              e["sha256"] for e in lm["registered"]
                              if e["doc"]["name"] == sb["model"]["name"]))
    for i, v in enumerate(sb["emit"]):
        got = ref_book_full_turn({}, v["center"], rho, peak, board)
        failures += not check(f"book emit #{i} ({v['note']})", got == v["field"], f"got {got}")
    for name in ("pure_decay", "clamp"):
        v = sb["scalar_traces"][name]
        got = ref_book_update(v["tau"], v["delta"], rho, peak)
        failures += not check(f"scalar trace {name}", got == v["after"], f"got {got!r}")
    tau = 0.0
    for i, s in enumerate(sb["scalar_traces"]["chain"]["steps"]):
        tau = ref_book_update(tau, s["delta"], rho, peak)
        failures += not check(f"chain turn {i + 1}", tau == s["tau"], f"got {tau!r}")
    fork = ref_book_update(sb["scalar_traces"]["chain"]["steps"][1]["tau"], 0.14, rho, peak)
    failures += not check("chain fork (delta 0.14)",
                          fork == sb["scalar_traces"]["chain"]["fork_at_turn_3_with_delta_0_14"])
    field: dict = {}
    for v in sb["field_walk"]["turns"]:
        field = ref_book_full_turn(field, v["center"], rho, peak, board)
        failures += not check(f"field walk turn {v['turn']}", field == v["field"])
    # The two named scent models must NOT agree — that is why they are two registrations.
    dv = sb["divergence_vs_reference"]
    ref_field = ref_smell_emit(dv["center"], 0.9, 5, board)
    book_field = ref_book_full_turn({}, dv["center"], rho, peak, board)
    ok = (ref_field == dv["subtractive_chebyshev_v1"] and book_field == dv["multiplicative_book_v1"]
          and ref_field != book_field and dv["identical"] is False)
    failures += not check("named models pinned + observably different", ok)
    # The kernel is pinned verbatim BECAUSE a fitted Gaussian is not safely reproducible.
    probe = sb["closed_form_probe"]
    ok = (probe["round"]["reproduces_printed_kernel"] and probe["trunc"]["reproduces_printed_kernel"]
          and probe["windows"]["round"][1] < probe["windows"]["trunc"][0])
    failures += not check("closed-form probe: both quantizations fit, windows disjoint", ok)
    op = sb["ordering_probe"]
    ok = any(not c["equal"] for c in op["cases"]) and all(
        ((1 - rho) * c["tau"] + c["delta"] == c["pinned_order"])
        and (c["tau"] - rho * c["tau"] + c["delta"] == c["alternative_order"])
        for c in op["cases"])
    failures += not check("ordering probe: evaluation order is load-bearing", ok)

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
