"""Regenerate every fixture under ``vectors/`` from the reference constructions in
``verify_vectors.py``. CI runs this and fails on any drift (the committed vectors must equal a
fresh regeneration). Inputs here are synthetic — our own values, not the reference simulator's
content — so the fixtures pin the *algorithms*, not anyone's copyrighted data.

Run: ``python gen_vectors.py`` then ``python verify_vectors.py``.
"""

from __future__ import annotations

import hashlib
import json
import math
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


def gen_report_consensus() -> None:
    sig_key = "חתימת_קונסנזוס_משותפת"
    reports = [
        ({"קבוצה_א": "team-aleph", "קבוצה_ב": "team-bet",
          "תוצאה": {"מנצחת": "team-aleph", "ניקוד": [20, 5]},
          "game_uid": "f757f50d-d4f4-17e7-06cf-755905739b16",
          "tokens_total_series": 0, "github_commit": "abc1234"},
         "Hebrew-keyed report body (floats absent)"),
        ({"סדרה": [{"משחקון": 1, "ניקוד": [5, 10]}, {"משחקון": 2, "ניקוד": [20, 5]}],
          "ram_gb": 31.8, "decay_per_step": 0.1, "mutual_agreement": True},
         "nested list + floats — spaced form still shortest-round-trip floats"),
    ]
    vectors = []
    for report, note in reports:
        sig = ref.ref_report_consensus_signature(report)
        vectors.append({
            "report": report,
            "note": note,
            "signature": sig,
            "signed_report": {**report, sig_key: sig},
            "compact_form_sha256": ref.canonical_hash(report),
        })
    _write("report_consensus.json", {
        "description": "Settlement consensus signature — the release's SECOND canonical form "
                       "(reference report_writer.py, verified at sha 960499fd): "
                       "json.dumps(report, sort_keys=True, ensure_ascii=False) with DEFAULT "
                       "(spaced) separators, then SHA-256. The signature is computed BEFORE the "
                       "signature key is inserted (sign-then-insert) — verify by popping the key, "
                       "re-serializing spaced, re-hashing. compact_form_sha256 shows the §2 "
                       "compact form does NOT reproduce it: a team signing compact fails "
                       "settlement at the exact moment both teams must agree. Found by Alon's "
                       "team (alonengel / anrbj666).",
        "serialization": {"sort_keys": True, "ensure_ascii": False,
                          "separators": [", ", ": "], "separators_note": "json.dumps defaults"},
        "signature_key": sig_key,
        "vectors": vectors,
    })


# --- LOCKED-MODEL DECLARATIONS (SPEC section 7) -------------------------------------------
#
# Registered docs. Each is an input here, not an output: the fixture stores the doc AND its
# hash, and verify_vectors.py re-derives the hash from the stored doc.

BOOK_KERNEL_ROWS = [list(row) for row in ref.BOOK_KERNEL]


def _doc_scent_subtractive() -> dict:
    return ref.ref_lock_doc(
        "scent_model", "subtractive_chebyshev_v1",
        {
            "field_size": 5, "emit_intensity": 0.9, "min_center_intensity": 0.5,
            "distance": "chebyshev", "falloff": "linear",
            "falloff_step": "emit_intensity / (field_size // 2 + 1)",
            "decay": "subtractive", "decay_per_step": 0.1,
            "update": "tau' = round(max(0, tau - decay_per_step), 3)",
            "rounding_decimals": 3, "clamp": [0.0, None],
            "cadence": "per_full_turn", "order": "deposit_then_decay",
            "receiver_side_decay": True, "initial_field": "empty",
            "transmitted": True,
        },
        {
            "note": "emit at the centre of a 7x7 board, then one decay",
            "emit_center": [3, 3],
            "emit_field": ref.ref_smell_emit([3, 3], 0.9, 5, 7),
            "after_one_decay": ref.ref_smell_decay(ref.ref_smell_emit([3, 3], 0.9, 5, 7), 0.1),
        },
    )


def _doc_scent_book() -> dict:
    return ref.ref_lock_doc(
        "scent_model", "multiplicative_book_v1",
        {
            "field_size": 5, "center_intensity": 0.9, "decay_rho": 0.1,
            "kernel": BOOK_KERNEL_ROWS,
            "kernel_source": "book v3.0.0 figure 4 — printed values, verbatim lookup",
            "decay": "multiplicative",
            "update": "tau' = clamp((1 - rho) * tau + kernel_delta, 0, center_intensity)",
            "evaluation_order": "(1 - rho) * tau + delta, then clamp",
            "rounding_decimals": None, "clamp": [0.0, 0.9],
            "cadence": "per_full_turn", "order": "decay_then_deposit",
            "receiver_side_decay": False, "initial_field": "empty",
            "transmitted": False,
        },
        {
            "note": "the clamp case: a saturated cell decays, then takes an adjacent deposit",
            "tau": 0.9, "delta": 0.62,
            "raw": (1 - 0.1) * 0.9 + 0.62,
            "clamped": ref.ref_book_update(0.9, 0.62, 0.1, 0.9),
        },
    )


def _doc_wire_reference() -> dict:
    return ref.ref_lock_doc(
        "wire_shape", "reference-v3",
        {
            "tools": ["negotiate", "receive_turn", "submit_audit", "receive_control"],
            "messages_per_half_turn": 1,
            "smell_grid_on_wire": True,
            "move_revealed": "at_audit",
            "replicated_engines": False,
            "phases": "all four of book ch.5, with Reveal deferred to the audit boundary",
            "rival_position_computable_live": False,
        },
        {
            "note": "one turn message per half-turn; the move is sealed, the field is sent",
            "turn_message_keys": ["step", "commit", "hint", "smell_grid", "barrier_placed"],
        },
    )


def _doc_wire_bookletter() -> dict:
    return ref.ref_lock_doc(
        "wire_shape", "bookletter-v3",
        {
            "messages_per_half_turn": 2,
            "message_kinds": ["commit", "reveal"],
            "smell_grid_on_wire": False,
            "move_revealed": "per_half_turn",
            "replicated_engines": True,
            "commit_order": "police_first",
            "withheld_until_audit": ["nonce", "verdict"],
            "sealed_payload_fields": ["step", "role", "sub_game", "state_digest", "action",
                                      "hint", "verdict"],
            "audit_message_keys": ["end_state_digest", "group_id", "nonces", "verdicts"],
            "rival_position_computable_live": True,
            "unpinned_preimages": ["state_digest", "end_state_digest", "config_sha256",
                                   "terms_signature"],
        },
        {
            "note": "contributed by anrbj666 (Alon Engel, Renat Karimov), kit issue #6; the "
                    "commit layer reproduces under the section-3 construction over the full "
                    "7-field payload, the four preimages above are not yet pinned",
            "commit_construction": "SHA256(canonical(payload) + '|' + nonce)",
        },
    )


def _doc_info_mode(name: str, exact: bool) -> dict:
    return ref.ref_lock_doc(
        "info_mode", name,
        {
            "rival_position_in_observation": exact,
            "sources": (["own_state", "rival_position", "rival_scent", "hints"] if exact
                        else ["own_state", "rival_scent", "hints"]),
            "enforcement": ("structural under wire_shape reference-v3 (the rival's position "
                            "never crosses the wire); an honor term under bookletter-v3, where "
                            "the wire carries it and only the brain's restraint withholds it"),
            "artifact_provable": {
                "mismatch": True,
                "violation": False,
                "why": "a mismatch is provable from the two negotiate records; a violation is "
                       "not, because a decision record does not disclose which information "
                       "produced it",
            },
        },
        {
            "note": "the observation space the brain is entitled to read",
            "observation_keys": (["self", "barriers", "rival_position", "smell_grid", "hint"]
                                 if exact else ["self", "barriers", "smell_grid", "hint"]),
        },
    )


def gen_locked_model() -> None:
    docs = [_doc_scent_subtractive(), _doc_scent_book(), _doc_wire_reference(),
            _doc_wire_bookletter(), _doc_info_mode("belief", exact=False),
            _doc_info_mode("exact", exact=True)]
    registered = [{"doc": d, "declared_as": f"{d['family']}_sha256",
                   "sha256": ref.ref_lock_hash(d)} for d in docs]
    by_name = {d["doc"]["name"]: d["sha256"] for d in registered}
    # The refusal rule is behavioural, not byte-level, so it gets its own truth table.
    a, b = by_name["subtractive_chebyshev_v1"], by_name["multiplicative_book_v1"]
    decisions = [
        (a, a, "both declare, same model"),
        (a, b, "both declare, different models"),
        (a, None, "we declare, they are silent (e.g. the unmodified reference peer)"),
        (None, b, "they declare, we are silent"),
        (None, None, "neither declares"),
    ]
    _write("locked_model.json", {
        "description": "Locked-model declarations — ONE doc schema serving THREE named-parameter "
                       "families (scent_model, wire_shape, info_mode). A peer publishes a doc, "
                       "hashes it with the section-2 compact canonical form, and declares only "
                       "the hash at negotiate time under '<family>_sha256'. The schema exists so "
                       "that two teams' hashes are COMPARABLE: a bare hash over an ad-hoc dict "
                       "makes two correct implementations of the same model refuse each other. "
                       "Refusal fires ONLY when both peers declare a family and disagree — "
                       "omission is never refusal. See SPEC section 7.",
        "doc_schema": {"keys": list(ref.LOCK_DOC_KEYS), "families": list(ref.LOCK_FAMILIES),
                       "hash": "sha256(canonical_json(doc))",
                       "declared_key": "<family>_sha256"},
        "registered": registered,
        "declaration_example": {
            "note": "what actually crosses the wire in the negotiate extras — hashes only",
            "scent_model_sha256": by_name["multiplicative_book_v1"],
            "wire_shape_sha256": by_name["reference-v3"],
            "info_mode_sha256": by_name["belief"],
        },
        "refusal_rule": [
            {"ours": o, "theirs": t, "note": note, "decision": ref.ref_lock_decision(o, t)}
            for o, t, note in decisions
        ],
    })


# --- book-v3 scent model, PROPOSED (SPEC section 5.1) -------------------------------------


def _closed_form_probe() -> dict:
    """Evidence for why the kernel is pinned verbatim rather than as a formula."""
    peak, probes = 0.9, {"round": 1.3180, "trunc": 1.3440}
    out = {}
    for mode, sigma2 in probes.items():
        rows = []
        for i in range(5):
            row = []
            for j in range(5):
                d2 = (i - 2) ** 2 + (j - 2) ** 2
                v = peak * math.exp(-d2 / (2 * sigma2))
                row.append(round(v, 2) if mode == "round" else math.floor(v * 100) / 100)
            rows.append(row)
        out[mode] = {"sigma_squared": sigma2, "reproduces_printed_kernel": rows == BOOK_KERNEL_ROWS,
                     "quantized": rows}
    out["windows"] = {"round": [1.3178, 1.3327], "trunc": [1.3436, 1.3538]}
    out["note"] = (
        "Figure 4 IS an exact radial Gaussian at printed precision — but only inside a narrow "
        "sigma window the book never prints, and the window that works under round-to-2dp is "
        "DISJOINT from the one that works under truncation. A team deriving the kernel from its "
        "own fit lands outside the other team's window and gets a different field, silently. "
        "The printed 25 values are the only thing two implementations can both reach, so the "
        "kernel is pinned verbatim. (Reconciles the open question between our earlier reading — "
        "'the values match no clean formula' — and anrbj666's 'exact Gaussian': theirs is "
        "right about the shape, ours about the reproducibility. Both conclusions point here.)"
    )
    return out


def _ordering_probe() -> dict:
    """The model does no rounding, so algebraically-equal orderings are NOT byte-equal."""
    rho, cases = 0.1, []
    for tau, delta in ((0.05, 0.04), (0.05, 0.14), (0.1, 0.14)):
        pinned, alt = (1 - rho) * tau + delta, tau - rho * tau + delta
        cases.append({"tau": tau, "delta": delta, "pinned_order": pinned,
                      "alternative_order": alt, "equal": pinned == alt})
    return {
        "pinned": "(1 - rho) * tau + delta",
        "alternative": "tau - rho * tau + delta",
        "cases": cases,
        "note": "Algebraically identical, not identical in IEEE-754 doubles. Because this model "
                "rounds nothing and each side RECOMPUTES the rival's field rather than "
                "receiving it, a byte-comparison of two recomputed fields can differ on the "
                "last bit purely from evaluation order. Pin the order as written, or compare "
                "fields with a tolerance — do not do neither.",
    }


def gen_scent_book_v3() -> None:
    rho, center, board = 0.1, 0.9, 7
    emit = []
    for c, note in (([3, 3], "kernel deposited on an empty field, board centre"),
                    ([0, 0], "corner emission clipped to board bounds")):
        emit.append({"center": c, "note": note,
                     "field": ref.ref_book_full_turn({}, c, rho, center, board)})
    # Scalar traces: one cell's history, which is where the model's arithmetic is legible.
    pure = {"note": "book ch.4 worked example: a fresh centre trace after one full turn of "
                    "pure decay, no new deposit (the book prints ~0.81)",
            "tau": 0.9, "delta": 0.0, "after": ref.ref_book_update(0.9, 0.0, rho, center)}
    clamp = {"note": "the upper clamp earns its keep: the printed formula's max(0, .) alone "
                     "would leave 1.43, above the book's declared [0, 0.9] range for tau",
             "tau": 0.9, "delta": 0.62, "raw": (1 - rho) * 0.9 + 0.62,
             "after": ref.ref_book_update(0.9, 0.62, rho, center)}
    chain, tau = [], 0.0
    for delta in (0.62, 0.20, 0.20):
        tau = ref.ref_book_update(tau, delta, rho, center)
        chain.append({"delta": delta, "tau": tau})
    forked = ref.ref_book_update(chain[1]["tau"], 0.14, rho, center)
    scalar_chain = {
        "note": "three full turns of one cell, from an EMPTY start: an orthogonal deposit, then "
                "two turns at kernel distance 2. The fork shows the same predecessor under a "
                "0.14 deposit instead of 0.20. Values contributed by anrbj666 (Alon Engel, "
                "Renat Karimov) and re-derived here from the book's figure 4 alone.",
        "steps": chain, "fork_at_turn_3_with_delta_0_14": forked,
    }
    walk, field = [], {}
    for turn, pos in enumerate(([3, 3], [3, 4], [2, 4]), start=1):
        field = ref.ref_book_full_turn(field, pos, rho, center, board)
        walk.append({"turn": turn, "center": pos, "field": field})
    ref_field = ref.ref_smell_emit([3, 3], 0.9, 5, 7)
    book_field = ref.ref_book_full_turn({}, [3, 3], rho, center, board)
    _write("scent_book_v3.json", {
        "description": "PROPOSED — the book's ch.4 scent model as a named registration, "
                       "'multiplicative_book_v1', beside the reference's "
                       "'subtractive_chebyshev_v1' (section 5, CORE). Multiplicative decay "
                       "against a verbatim 5x5 figure-4 kernel, once per FULL turn, from an "
                       "empty start, with NO rounding. PROPOSED until a second independent "
                       "implementation reproduces these fixtures — the kit's own bar. Spec "
                       "facts contributed by anrbj666 (Alon Engel, Renat Karimov); every value "
                       "below is re-derived here from book v3.0.0 ch.4 and App. F.",
        "status": "PROPOSED",
        "model": _doc_scent_book(),
        "kernel": BOOK_KERNEL_ROWS,
        "closed_form_probe": _closed_form_probe(),
        "ordering_probe": _ordering_probe(),
        "emit": emit,
        "scalar_traces": {"pure_decay": pure, "clamp": clamp, "chain": scalar_chain},
        "field_walk": {
            "note": "three full turns of a moving agent's own trail on a 7x7 board, empty start",
            "board_size": board, "rho": rho, "center_intensity": center, "turns": walk,
        },
        "divergence_vs_reference": {
            "note": "one agent at [3,3] on an empty 7x7, after one turn, under each model — "
                    "the fields differ in shape AND support, so a team can see at a glance "
                    "which model it built. Neither is wrong; they are different registrations.",
            "center": [3, 3],
            "subtractive_chebyshev_v1": ref_field,
            "multiplicative_book_v1": book_field,
            "identical": ref_field == book_field,
        },
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
    gen_report_consensus()
    gen_locked_model()
    gen_scent_book_v3()
    gen_joint_seed()
    gen_derive_starts()


if __name__ == "__main__":
    main()
