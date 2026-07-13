"""Regenerate every fixture under ``vectors/`` from the reference constructions in
``verify_vectors.py``. CI runs this and fails on any drift (the committed vectors must equal a
fresh regeneration). Inputs here are synthetic — our own values, not the reference simulator's
content — so the fixtures pin the *algorithms*, not anyone's copyrighted data.

Run: ``python gen_vectors.py`` then ``python verify_vectors.py``.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import verify_vectors as ref

VECTORS = Path(__file__).parent / "vectors"


def _write(name: str, obj: dict) -> None:
    text = json.dumps(obj, indent=2, ensure_ascii=False) + "\n"
    (VECTORS / name).write_text(text, encoding="utf-8")
    print(f"wrote {name}")


# --- CORE -------------------------------------------------------------------------------

def gen_canonical_json() -> None:
    objects = [
        ({"b": 1, "a": {"d": 4, "c": 3}}, "sorted keys, nested object"),
        ({"hint": "אני ליד הכיכר", "move": "MOVE:N"}, "Hebrew hint stays native UTF-8 (ensure_ascii=False)"),
        ({"emoji": "🙂", "x": 1}, "astral emoji stays native — NOT \\uXXXX surrogate-escaped"),
        ({"decay_per_step": 0.1, "emit_intensity": 0.9, "min_center_intensity": 0.5,
          "ram_gb": 31.8, "vram_gb": 6.0}, "floats permitted; must be shortest round-trip repr"),
        ({"a": True, "b": None, "c": [1, 2, 3]}, "JSON literals + int array"),
    ]
    _write("canonical_json.json", {
        "description": "The one canonical form every hash uses: json.dumps(obj, sort_keys=True, "
                       "ensure_ascii=False, separators=(',', ':')), UTF-8. ensure_ascii=FALSE is "
                       "the load-bearing detail — see SPEC section 'Canonical JSON'.",
        "serialization": {"sort_keys": True, "ensure_ascii": False, "separators": [",", ":"]},
        "vectors": [
            {"object": o, "note": note, "canonical": ref._canonical_str(o), "sha256": ref.canonical_hash(o)}
            for o, note in objects
        ],
    })


def gen_commit_reveal() -> None:
    cases = [
        ({"step": 0, "type": "system_spec", "spec": {"os": "Linux", "cpu_cores": 4,
          "ram_gb": 16.0, "vram_gb": 0.0}, "model": "cli-default", "code_version": "1.0",
          "group_name": "Example-Team", "sub_game_number": 1},
         "0f1e2d3c4b5a69788796a5b4c3d2e1f0", "step-0 host-spec record (floats in spec)"),
        ({"step": 1, "state": "grid=7x7;self=[4, 3];barriers=[]", "position": [4, 3],
          "move": "MOVE:S", "intent": "truth", "hint": "I keep to the main avenues."},
         "112233445566778899aabbccddeeff00", "move record, ASCII hint"),
        ({"step": 2, "state": "grid=7x7;self=[2, 4];barriers=[[1, 1]]", "position": [2, 4],
          "move": "MOVE:N", "intent": "lie", "hint": "אני ליד הכיכר 🙂"},
         "deadbeefcafef00dfeedface00c0ffee",
         "non-ASCII hint — pins ensure_ascii=False; escaping here => opponent's audit re-hash "
         "mismatches => false tamper_forfeit => both score 0"),
    ]
    # The v3.0.0 release publishes three inconsistent commit constructions (book ch.5 listing:
    # nonce inside the object; book audit snippet: f"{nonce}|{move}"; reference code:
    # canonical|nonce). The kit pins the reference form; this entry hashes ONE identical input
    # under all three so a failing team can identify which form it accidentally implemented.
    div_payload, div_nonce = cases[1][0], cases[1][1]
    divergent = {
        "payload": div_payload,
        "nonce": div_nonce,
        "reference_form": ref.ref_commit(div_payload, div_nonce),
        "book_ch5_listing_form": ref.canonical_hash({**div_payload, "nonce": div_nonce}),
        "book_audit_snippet_form": hashlib.sha256(
            f"{div_nonce}|{div_payload['move']}".encode()
        ).hexdigest(),
        "note": "The same sealed record under the release's three published constructions — all "
                "three hashes differ. reference_form and book_ch5_listing_form hash the full "
                "record; book_audit_snippet_form structurally consumes only nonce|move, so it "
                "binds neither state nor intent (position/bluff tampering would go undetected). "
                "Only reference_form is this kit's CORE form (SPEC 'Commit-reveal'). If your "
                "commits equal one of the other two, you implemented from one of the book's "
                "illustrative listings — switch to the reference form.",
    }
    _write("commit_reveal.json", {
        "description": "Per-step commit-reveal seal. commit = SHA256(canonical_json(payload)|nonce). "
                       "Self-sealed by each peer; re-hashed by the OPPONENT at audit — so the "
                       "canonical form must match cross-team even though the payload does not.",
        "construction": "sha256(utf8(canonical_json(payload) + '|' + nonce))",
        "vectors": [
            {"payload": p, "nonce": n, "note": note, "commit": ref.ref_commit(p, n)}
            for p, n, note in cases
        ],
        "divergent_forms": divergent,
    })


def gen_terms_signature() -> None:
    terms = {
        "board_size": 7, "smell_grid_size": 5, "decay_per_step": 0.1, "emit_intensity": 0.9,
        "min_center_intensity": 0.5, "max_steps": 35, "barriers_max": 14, "setting": "Haifa",
        "hint_max_words": 15, "axis_origin_corner": "top-left", "axis_start_index": 0,
        "thief_start": [3, 3], "cop_start": [0, 0], "num_games": 1,
    }
    nonce = "a1a2a3a4b1b2b3b4c1c2c3c4d1d2d3d4"
    _write("terms_signature.json", {
        "description": "Pre-game agreement gate. signature = SHA256(canonical_json(terms)|nonce), "
                       "the same construction as a commit, over the agreed terms. The opponent "
                       "re-verifies over the terms it received (which must value-equal its own). "
                       "The float 0.1 pins shortest round-trip repr — a language that emits "
                       "'0.10000000000000001' fails the signature and cannot play.",
        "vectors": [{"terms": terms, "nonce": nonce, "signature": ref.ref_terms_signature(terms, nonce)}],
    })


def gen_game_uid() -> None:
    terms = {"board_size": 7, "smell_grid_size": 5, "decay_per_step": 0.1, "emit_intensity": 0.9,
             "min_center_intensity": 0.5, "max_steps": 35, "barriers_max": 14, "setting": "Haifa",
             "hint_max_words": 15, "thief_start": [3, 3], "cop_start": [0, 0], "num_games": 1}
    a, b = "team-aleph", "team-bet"
    _write("game_uid.json", {
        "description": "Deterministic shared id both peers reproduce with no round-trip. "
                       "game_uid = UUID(SHA256(canonical(terms)|'|'.join(sorted([g_a,g_b])))[:16]). "
                       "Group order does not matter (ids are sorted first).",
        "vectors": [
            {"terms": terms, "group_a": a, "group_b": b, "game_uid": ref.ref_game_uid(terms, a, b),
             "note": "canonical order"},
            {"terms": terms, "group_a": b, "group_b": a, "game_uid": ref.ref_game_uid(terms, b, a),
             "note": "groups swapped -> identical uid (sorted)"},
        ],
    })


def gen_pheromone() -> None:
    emit = [
        {"center": [3, 3], "intensity": 0.9, "grid_size": 5, "board_size": 7,
         "note": "full 5x5 field, centre 0.9, falloff 0.3/step"},
        {"center": [0, 0], "intensity": 0.9, "grid_size": 5, "board_size": 7,
         "note": "corner emission clipped to board bounds"},
    ]
    for e in emit:
        e["field"] = ref.ref_smell_emit(e["center"], e["intensity"], e["grid_size"], e["board_size"])
    decay = [
        {"before": {"3,3": 0.9, "3,4": 0.6, "3,5": 0.3}, "decay": 0.1,
         "note": "one step of decay by 0.1"},
        {"before": {"1,1": 0.05}, "decay": 0.1, "note": "clamps to 0.0 at the floor"},
    ]
    for d in decay:
        d["after"] = ref.ref_smell_decay(d["before"], d["decay"])
    _write("pheromone.json", {
        "description": "Scent field (book ch.4). Radial emit: half=grid//2, falloff=intensity/"
                       "(half+1), value=round(max(0,intensity-falloff*chebyshev),3). Decay/step: "
                       "round(max(0,v-decay),3). Only value>0 crosses the wire as {'r,c': value}. "
                       "Each peer emits its own and transmits it, so this is a self-test — but a "
                       "correct port is what makes your belief map behave as the book describes.",
        "emit": emit, "decay": decay,
    })


# --- ENHANCEMENTS (opt-in, SPEC Appendix A) ----------------------------------------------

def gen_joint_seed() -> None:
    pairs = [("3f9a1c", "b27e04"), ("00", "ffffffffffffffff")]
    _write("joint_seed.json", {
        "description": "ENHANCEMENT (not required by the book): trustless coin flip for a shared "
                       "seed, if a pair opts into randomized starts instead of the book's fixed "
                       "configured starts. commit=SHA256(canonical({'seed_share':r})); "
                       "seed=SHA256(canonical({'shares':[r1,r2]})).",
        "vectors": [
            {"share_group_1": s1, "share_group_2": s2,
             "commit_group_1": ref.ref_share_commit(s1), "commit_group_2": ref.ref_share_commit(s2),
             "seed": ref.ref_joint_seed(s1, s2)}
            for s1, s2 in pairs
        ],
    })


def gen_derive_starts() -> None:
    cases = [("seed-alpha", 0, 7), ("seed-alpha", 1, 7), ("seed-beta", 0, 10), ("seed-beta", 16, 10)]
    vectors = []
    for seed, index, n in cases:
        cop, thief, draws = ref.ref_derive_starts(seed, index, n)
        vectors.append({"seed": seed, "index": index, "n": n, "cop": cop, "thief": thief, "draws": draws})
    _write("derive_starts.json", {
        "description": "ENHANCEMENT (not required by the book): seeded asymmetric starts, a "
                       "structural tie-breaker if a pair prefers randomized fair starts over the "
                       "book's fixed configured cop_start/thief_start. 4 digest bytes per cell, "
                       "minimum-Chebyshev deterministic re-draw, index = game*16 + attempt.",
        "vectors": vectors,
    })


def main() -> None:
    gen_canonical_json()
    gen_commit_reveal()
    gen_terms_signature()
    gen_game_uid()
    gen_pheromone()
    gen_joint_seed()
    gen_derive_starts()


if __name__ == "__main__":
    main()
