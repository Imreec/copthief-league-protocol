"""Check a set of submission artifacts before anyone else sees them — stdlib only, no deps.

    python tools/check_artifacts.py <dir> [--terms terms.json] [--quiet]

The book (App. F table 20) says the four artifacts share one ``game_uid`` and take their names
from one ``game_id``. That sounds like bookkeeping. It is not: the ``game_uid`` is the only key
that joins your report to your own sealed logs *and* to your opponent's report. Two counted
reports that name one match by two different uids are contradictory, and App. E rule 35 scores
that **0 for both teams** — so a mistake here costs the points of a team that did nothing wrong.

That exact defect happened in a real cross-team series (2026-07-25), in its sneakiest form: one
side derived its uid from its **whole configuration** rather than from the flat negotiated terms.
The result was perfectly deterministic and identical across all four of that team's artifacts, so
they joined each other correctly and looked healthy — only the cross-team join failed, while every
game *value* in the two reports agreed exactly. Nothing on either side had reason to look.

Which is why ``--terms`` matters: without it this script can tell you the uid is **consistent**,
and a wrongly-derived uid already is. Only re-derivation catches that one.

Exit codes:  0 = all checks pass · 1 = at least one failed · 2 = usage / nothing to check
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import verify_vectors as ref  # noqa: E402  (path set above; the kit is not installable by design)

# Book App. F table 20. Per-sub-game files carry a zero-padded _g<NN>; match-level files do not.
MATCH_LEVEL = ("declaration", "result")
SUB_GAME_LEVEL = ("config", "log")
NAME_RE = re.compile(r"^(declaration|config|log|result)_(?P<gid>.+?)(?:_g(?P<nn>\d+))?\.json$")

# Required keys per kind. Unknown keys are tolerated on purpose — same forward-compatible stance
# the wire layer takes; a peer may legitimately carry more than we know about.
REQUIRED = {
    "declaration": {"game_id", "game_uid", "groups", "num_sub_games"},
    "config": {"game_id", "game_uid", "sub_game_number"},
    "log": {"game_id", "game_uid", "summary", "records"},
    "result": {"game_id", "game_uid", "groups", "num_sub_games", "sub_games", "final_result"},
}

_failures = 0
_quiet = False


def check(name: str, ok: bool, detail: str = "") -> bool:
    global _failures
    _failures += not ok
    if not ok or not _quiet:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}{('  ' + detail) if detail and not ok else ''}")
    return ok


def _group_ids(declaration: dict) -> list[str]:
    """The two group ids, from either shape of the `groups` block.

    The reference's declaration uses ``{"group_1": {...}, "group_2": {...}}``; the result uses a
    list. Accept both rather than insisting on one — neither is wrong, and refusing a shape the
    book permits would make this script the thing that is broken.
    """
    groups = declaration.get("groups")
    blocks = list(groups.values()) if isinstance(groups, dict) else (groups or [])
    return [b.get("group_id") for b in blocks if isinstance(b, dict) and b.get("group_id")]


def _check_many(directories: list[str], terms: str | None) -> int:
    """Check several artifact sets, then the join between them.

    This is the check no single team can perform alone, and the one the 2026-07-25 series needed:
    each side's bundle was internally perfect, and they disagreed with each other. Run it against
    your directory and your opponent's before either of you reports.
    """
    import subprocess

    worst = 0
    for directory in directories:
        cmd = [sys.executable, __file__, directory] + (["--terms", terms] if terms else [])
        worst = max(worst, subprocess.run(cmd).returncode)

    print(f"\n=== cross-team join across {len(directories)} artifact sets ===")
    # TOP LEVEL ONLY, per match. Two lessons the first join learned the hard way:
    # (1) it swept subdirectories with rglob, so the archive layout the playbook itself
    #     prescribes — every settled series snapshotted below the live set — was read as a
    #     rule-35 dispute, "the scariest verdict at the one moment it is designed to be
    #     believed" (anrbj666's P5-1). Worse than their probe shows: an archived friendly of
    #     the SAME pairing shares the live game's deterministic ids, so no grouping can save a
    #     recursive sweep. Archives are history, not disputes; point at an archived set
    #     directly to join it.
    # (2) it compared bare value-sets across everything it saw, so two DIFFERENT matches in
    #     one tree collided, and two reports of ONE match agreeing was never actually checked
    #     per match.
    def top_level_docs(directory: str) -> dict[str, dict[str, dict]]:
        """{game_id: {kind_or_name: doc}} from the directory's top level only."""
        out: dict[str, dict[str, dict]] = {}
        for path in sorted(Path(directory).glob("*.json")):
            m = NAME_RE.match(path.name)
            if not m:
                continue
            try:
                doc = json.loads(path.read_text(encoding="utf-8"))
            except (ValueError, UnicodeDecodeError):
                continue
            gid = doc.get("game_id") or m.group("gid")
            out.setdefault(gid, {})[path.name] = doc
        return out

    sides = {d: top_level_docs(d) for d in directories}
    for directory in directories:
        below = sum(1 for p in Path(directory).rglob("*.json")
                    if p.parent != Path(directory))
        if below and not _quiet:
            print(f"  note: {below} artifact file(s) in subdirectories of {directory} were NOT "
                  f"joined — archives are history, not disputes")

    shared = set.intersection(*(set(s) for s in sides.values())) if sides else set()
    if not check("the sets share a match to join", bool(shared),
                 f"per-directory matches: "
                 f"{ {d: sorted(s) for d, s in sides.items()} }"):
        worst = 1
    for directory, s in sides.items():
        extra = sorted(set(s) - shared)
        if extra and not _quiet:
            print(f"  note: match(es) only in {directory}: {extra} — not joined")

    JOIN_FIELDS = ("total_score", "sub_games_won", "winner_group", "ties", "series_tie",
                   "tokens_total_series", "games_played_including_this",
                   "first_meeting_between_groups", "diversity_reward_applied")
    for gid in sorted(shared):
        uids = {doc["game_uid"]
                for s in sides.values() for doc in s[gid].values() if doc.get("game_uid")}
        ok = check(f"[{gid}] both sets derive one game_uid", len(uids) == 1,
                   f"found {len(uids)}: {sorted(uids)}")
        if not ok:
            worst = 1
            print("\n  ^ two independently derived uids disagree. Neither side can see this "
                  "alone —\n    each bundle is self-consistent. The usual cause is one side "
                  "deriving from a\n    wider object than the flat negotiated terms. Do NOT "
                  "report until it is resolved:\n    two counted reports naming one match by "
                  "two uids zero BOTH teams (App. E r.35).")
        # Every value a grader diffs between the two reports — the league fields included
        # (they are graded inputs, and the join used to ignore all of them: imreeyal's N2,
        # then anrbj666's P5-3) — plus the one machine-checkable must-match row, the
        # consensus hash.
        results = [doc for s in sides.values() for name, doc in s[gid].items()
                   if name.startswith("result_")]
        for key in JOIN_FIELDS:
            values = {json.dumps((doc.get("final_result") or {}).get(key),
                                 sort_keys=True, ensure_ascii=False)
                      for doc in results if key in (doc.get("final_result") or {})}
            if not check(f"[{gid}] results agree on final_result.{key}", len(values) <= 1,
                         f"found {sorted(values)} — two reports of ONE match disagreeing is "
                         f"the contradictory-report shape rule 35 zeroes"):
                worst = 1
        shas = {(doc.get("mutual_agreement") or {}).get("sha256")
                for doc in results if doc.get("mutual_agreement")}
        if not check(f"[{gid}] results agree on mutual_agreement.sha256", len(shas) <= 1,
                     f"found {sorted(str(s) for s in shas)} — the settlement itself disagrees"):
            worst = 1

    print(f"\n{'ALL SETS AGREE' if worst == 0 else 'CROSS-TEAM JOIN FAILED'}")
    return 1 if worst else 0


def _selftest() -> int:
    """Build a synthetic artifact set, then break it, and require the right verdict each time.

    Synthetic on purpose: the fixtures elsewhere in this kit are generated from our own values
    rather than copied from the reference, and a self-test that needed the reference's sample run
    could not run in CI at all.
    """
    import subprocess
    import tempfile

    a, b = "team-bet", "team-aleph"          # deliberately unsorted, to exercise the sorting
    terms = {"board_size": 7, "smell_grid_size": 5, "decay_per_step": 0.1, "emit_intensity": 0.9,
             "min_center_intensity": 0.5, "max_steps": 35, "barriers_max": 14, "setting": "Haifa",
             "hint_max_words": 15, "axis_origin_corner": "top-left", "axis_start_index": 0,
             "thief_start": [3, 3], "cop_start": [0, 0], "num_games": 6}
    gid, guid = ref.ref_game_id(a, b), ref.ref_game_uid(terms, a, b)
    links = {"declaration": f"declaration_{gid}.json", "result": f"result_{gid}.json",
             "config": f"config_{gid}_g<NN>.json", "log": f"log_{gid}_g<NN>.json"}
    base = {"game_id": gid, "game_uid": guid, "links": links}
    files = {
        f"declaration_{gid}.json": {**base, "num_sub_games": 1,
                                    "groups": {"group_1": {"group_id": a},
                                               "group_2": {"group_id": b}}},
        f"config_{gid}_g01.json": {**base, "sub_game_number": 1, "terms": terms},
        f"log_{gid}_g01.json": {**base, "summary": {"sub_game_number": 1}, "records": []},
        f"result_{gid}.json": {**base, "num_sub_games": 1,
                               "groups": [{"group_id": a}, {"group_id": b}],
                               "sub_games": [{"sub_game_number": 1, "score": {a: 20, b: 5}}],
                               "final_result": {"total_score": {a: 20, b: 5}}},
    }

    def build(dest: Path, mutate=None) -> Path:
        dest.mkdir(parents=True, exist_ok=True)
        data = {n: json.loads(json.dumps(d)) for n, d in files.items()}
        if mutate:
            mutate(data)
        for name, doc in data.items():
            (dest / name).write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
        return dest

    def verdict(d: Path) -> int:
        return subprocess.run([sys.executable, __file__, str(d), "--quiet"],
                              capture_output=True, text=True).returncode

    def verdict2(d1: Path, d2: Path) -> int:
        return subprocess.run([sys.executable, __file__, str(d1), str(d2), "--quiet"],
                              capture_output=True, text=True).returncode

    def mint(data):
        data[f"result_{gid}.json"]["game_uid"] = "2f0c25a9-0000-4000-8000-000000000000"

    def wrong_input(data):
        """The failure that actually happened, and the one consistency checks cannot see.

        A uid derived from a WIDER config than the flat negotiated terms: perfectly
        deterministic, identical in all four files, joining them to each other correctly. Only
        re-derivation catches it.
        """
        wider = {**terms, "network": {"my_port": 8801}, "strategy": {"police_class": "x"}}
        bad = ref.ref_game_uid(wider, a, b)
        for doc in data.values():
            doc["game_uid"] = bad

    def self_first(data):
        wrong = f"{a}-vs-{b}"
        for doc in data.values():
            doc["game_id"] = wrong

    def bad_total(data):
        data[f"result_{gid}.json"]["final_result"]["total_score"][a] = 25

    def honest_tie(data):
        """A legitimately tied series: equal sub-game scores, +2 each declared (App. F tie
        score, the reference's own behaviour on a series tie). Must PASS — an earlier revision
        refused it, telling honestly tied pairs not to report."""
        fr = data[f"result_{gid}.json"]
        fr["sub_games"] = [{"sub_game_number": 1, "score": {a: 5, b: 5}}]
        fr["final_result"] = {"total_score": {a: 7, b: 7}, "series_tie": True}

    def tie_bonus_without_tie(data):
        """The +2 allowance must NOT leak: extra points with series_tie false stay refused."""
        fr = data[f"result_{gid}.json"]["final_result"]
        fr["total_score"] = {a: 22, b: 7}
        fr["series_tie"] = False

    def divergent_totals(data):
        """N2 (imreeyal dogfood): two bundles of ONE match whose results disagree on the
        values a grader diffs — must fail the JOIN even though each is internally consistent
        (this one keeps its own totals-sum identity by adjusting a sub-game row too)."""
        fr = data[f"result_{gid}.json"]
        fr["sub_games"] = [{"sub_game_number": 1, "score": {a: 10, b: 5}}]
        fr["final_result"] = {"total_score": {a: 10, b: 5}, "winner_group": a}

    def tie_fraud(data):
        """P5-4: `series_tie: true` used to be a free +2 on a series nobody tied. The
        allowance must demand COHERENCE: equal totals, null winner."""
        fr = data[f"result_{gid}.json"]["final_result"]
        fr["total_score"] = {a: 22, b: 7}
        fr["series_tie"] = True

    def winner_is_loser(data):
        """P5-2: winner_group must be the side the totals say won."""
        data[f"result_{gid}.json"]["final_result"]["winner_group"] = b

    def negative_count(data):
        """P5-2: a game count below zero is arithmetic nonsense whatever the posture."""
        data[f"result_{gid}.json"]["final_result"]["games_played_including_this"] = {a: 1, b: -7}

    def diversity_to_loser(data):
        """P5-2: the App. F reward is for a VICTORY over a new group — never the loser's."""
        fr = data[f"result_{gid}.json"]["final_result"]
        fr["winner_group"] = a
        fr["first_meeting_between_groups"] = True
        fr["diversity_reward_applied"] = {a: False, b: True}

    def friendly_posture(data):
        """The disarmed posture must stay LEGAL: unbumped counts, all-false diversity, a
        first meeting and a winner (PAIRING-PLAYBOOK 4d)."""
        fr = data[f"result_{gid}.json"]["final_result"]
        fr["winner_group"] = a
        fr["first_meeting_between_groups"] = True
        fr["games_played_including_this"] = {a: 0, b: 0}
        fr["diversity_reward_applied"] = {a: False, b: False}

    cases = [("a clean set", None, 0),
             ("a minted game_uid in the result", mint, 1),
             ("a CONSISTENT uid derived from the wrong input", wrong_input, 1),
             ("a self-first (unsorted) game_id", self_first, 1),
             ("a declared total that is not the sum", bad_total, 1),
             ("an honestly tied series declaring the App. F +2", honest_tie, 0),
             ("the +2 without a series tie", tie_bonus_without_tie, 1),
             ("a declared tie over unequal totals", tie_fraud, 1),
             ("winner_group naming the loser", winner_is_loser, 1),
             ("a negative game count", negative_count, 1),
             ("the diversity reward on the loser", diversity_to_loser, 1),
             ("the friendly (disarmed) posture", friendly_posture, 0)]
    bad = 0
    with tempfile.TemporaryDirectory() as td:
        for i, (label, mutate, want) in enumerate(cases):
            got = verdict(build(Path(td) / f"case{i}", mutate))
            ok = got == want
            bad += not ok
            print(f"  {'PASS' if ok else 'FAIL'}  {label} -> exit {got} (want {want})")
        # The cross-team JOIN — "the check neither team can run alone" — previously ran in no
        # selftest and no CI job outside a path-filtered compose run, so a regression in it
        # would have landed green (anrbj666's audit, E4). Both directions now pinned here.
        join_cases = [
            ("two sides of one match join", None, 0),
            ("two sides whose uids diverge refuse the join", mint, 1),
            ("two sides whose RESULTS disagree refuse the join", divergent_totals, 1),
        ]
        for i, (label, mutate, want) in enumerate(join_cases):
            d1 = build(Path(td) / f"join{i}a", None)
            d2 = build(Path(td) / f"join{i}b", mutate)
            got = verdict2(d1, d2)
            ok = got == want
            bad += not ok
            print(f"  {'PASS' if ok else 'FAIL'}  {label} -> exit {got} (want {want})")

        # P5-1 (anrbj666): honest archives below the live set — a DIFFERENT match in a
        # subdirectory — must not be read as a rule-35 dispute. The playbook's own layout.
        d1 = build(Path(td) / "arch-a", None)
        d2 = build(Path(td) / "arch-b", None)
        c = "team-gimel"
        arch_gid, arch_uid = ref.ref_game_id(a, c), ref.ref_game_uid(terms, a, c)
        archive = d2 / "archive" / "older"
        archive.mkdir(parents=True)
        (archive / f"result_{arch_gid}.json").write_text(json.dumps({
            "game_id": arch_gid, "game_uid": arch_uid, "links": {},
            "groups": [{"group_id": a}, {"group_id": c}], "num_sub_games": 1,
            "sub_games": [{"sub_game_number": 1, "score": {a: 5, c: 20}}],
            "final_result": {"total_score": {a: 5, c: 20}, "winner_group": c},
        }, indent=2) + "\n", encoding="utf-8")
        got = verdict2(d1, d2)
        ok = got == 0
        bad += not ok
        print(f"  {'PASS' if ok else 'FAIL'}  an archived DIFFERENT match below one side is "
              f"history, not a dispute -> exit {got} (want 0)")
    print(f"\n{'SELFTEST PASSES' if bad == 0 else f'{bad} SELFTEST FAILURE(S)'}")
    return 1 if bad else 0


def main() -> int:
    global _quiet
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("directory", nargs="*",
                    help="one or more directories, each holding a declaration/config/log/result "
                         "set. Give TWO — yours and your opponent's — and the cross-team join is "
                         "checked too: both sides must have derived the same game_uid and the "
                         "same game_id, which is the check no single team can do alone")
    ap.add_argument("--selftest", action="store_true",
                    help="check this script still catches what it claims to (used by CI)")
    ap.add_argument("--terms", help="the signed 14-key terms as JSON, to also verify that the "
                                    "game_uid and game_id DERIVE from them (SPEC section 4)")
    ap.add_argument("--quiet", action="store_true", help="print only failures")
    args = ap.parse_args()
    _quiet = args.quiet

    if args.selftest:
        return _selftest()
    if not args.directory:
        ap.print_usage(sys.stderr)
        print("give a directory, or --selftest", file=sys.stderr)
        return 2

    if len(args.directory) > 1:
        return _check_many(args.directory, args.terms)

    root = Path(args.directory[0])
    if not root.is_dir():
        print(f"not a directory: {root}", file=sys.stderr)
        return 2

    found: dict[str, list[tuple[Path, str | None, dict]]] = {k: [] for k in REQUIRED}
    for path in sorted(root.glob("*.json")):
        m = NAME_RE.match(path.name)
        if not m:
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            print(f"  FAIL  {path.name} is not readable UTF-8 JSON  {exc}")
            return 1
        found[m.group(1)].append((path, m.group("nn"), data))

    total = sum(len(v) for v in found.values())
    if total == 0:
        print(f"no artifacts found in {root} — expected declaration_<game_id>.json and friends "
              f"(book App. F table 20)", file=sys.stderr)
        return 2

    print(f"{root}  ({total} artifacts)")

    # --- 1. the set ----------------------------------------------------------------------
    for kind in MATCH_LEVEL:
        check(f"exactly one {kind} artifact", len(found[kind]) == 1,
              f"found {len(found[kind])}")
    for kind in SUB_GAME_LEVEL:
        check(f"at least one {kind} artifact", len(found[kind]) >= 1)

    every = [(k, p, nn, d) for k, items in found.items() for p, nn, d in items]

    # --- 2. names ------------------------------------------------------------------------
    for kind, path, nn, _ in every:
        if kind in MATCH_LEVEL:
            check(f"{path.name}: match-level file carries no _g<NN>", nn is None)
        else:
            check(f"{path.name}: sub-game file carries a zero-padded _g<NN>",
                  nn is not None and len(nn) >= 2, f"got {nn!r}")

    # --- 3. the ids ----------------------------------------------------------------------
    for kind, path, nn, data in every:
        m = NAME_RE.match(path.name)
        check(f"{path.name}: filename game_id matches the one inside",
              m.group("gid") == data.get("game_id"),
              f"filename says {m.group('gid')!r}, file says {data.get('game_id')!r}")
        if nn is not None and "sub_game_number" in data:
            check(f"{path.name}: _g{nn} matches sub_game_number",
                  int(nn) == data["sub_game_number"], f"file says {data['sub_game_number']}")

    uids = {d.get("game_uid") for _, _, _, d in every}
    ok = check("ONE game_uid across every artifact", len(uids) == 1,
               f"found {len(uids)}: {sorted(str(u) for u in uids)}")
    if not ok:
        print("\n  ^ this is the one that zeroes both teams. The uid is derived from the FLAT "
              "negotiated\n    terms and both group ids, so every sub-game of one pairing shares "
              "it by construction.\n    Two reports naming one match by two uids are "
              "contradictory (App. E rule 35).\n    Note this failure is the loud kind. The quiet "
              "kind — a uid derived from a wider\n    config — keeps all four files agreeing and "
              "is only caught by --terms.")

    uid = next(iter(uids))
    try:
        uuid.UUID(str(uid))
        check("game_uid is a well-formed UUID", True)
    except (ValueError, AttributeError, TypeError):
        check("game_uid is a well-formed UUID", False, f"got {uid!r}")

    ids = {d.get("game_id") for _, _, _, d in every}
    check("ONE game_id across every artifact", len(ids) == 1, f"found {sorted(str(i) for i in ids)}")

    # --- 4. game_id is the SORTED pair ---------------------------------------------------
    if found["declaration"]:
        gids = _group_ids(found["declaration"][0][2])
        if check("the declaration names two group ids", len(gids) == 2, f"found {gids}"):
            expected = ref.ref_game_id(*gids)
            actual = next(iter(ids))
            ok = check("game_id is the SORTED pair (SPEC section 4)", actual == expected,
                       f"expected {expected!r}, got {actual!r}")
            if not ok and actual == "-vs-".join(gids[::-1] if gids[0] > gids[1] else gids):
                print("    ^ this looks like self-first naming. Sort the pair: the reference does, "
                      "so\n      both peers derive one id with no round-trip and no convention to "
                      "settle.")

    # --- 5. required keys ----------------------------------------------------------------
    for kind, path, _, data in every:
        missing = sorted(REQUIRED[kind] - set(data))
        check(f"{path.name}: required keys present", not missing, f"missing {missing}")

    # --- 6. the result agrees with itself ------------------------------------------------
    if found["result"]:
        res = found["result"][0][2]
        subs = res.get("sub_games") or []
        if isinstance(res.get("num_sub_games"), int):
            check("result: sub_games count matches num_sub_games",
                  len(subs) == res["num_sub_games"],
                  f"{len(subs)} entries vs num_sub_games={res['num_sub_games']}")
        totals: dict[str, int] = {}
        for sg in subs:
            for gid, score in (sg.get("score") or {}).items():
                if isinstance(score, (int, float)):
                    totals[gid] = totals.get(gid, 0) + score
        declared = (res.get("final_result") or {}).get("total_score")
        if totals and isinstance(declared, dict):
            # On a SERIES tie the reference ADDS the App. F tie score (2, fixed) to each side's
            # equal total — observed live against the reference implementation, so an honestly
            # tied series legitimately declares summed+2 per group. An earlier revision of this
            # check refused that, and its own docstring says "do NOT report until resolved" —
            # telling a tied pair not to report is the rule-35 sanction this tool exists to
            # prevent. The allowance is exactly +2 and only under a declared series_tie.
            final = res.get("final_result") or {}
            summed = {k: totals.get(k) for k in declared}
            series_tie = bool(final.get("series_tie"))
            tie_adjusted = {k: (None if v is None else v + 2) for k, v in summed.items()}
            # The +2 allowance is CONDITIONED (anrbj666's P5-4: it used to be a free +2 for
            # both sides on any series that merely SAID it tied): a declared tie must also
            # have equal totals and no winner, or the tie flag is the lie.
            tie_coherent = (series_tie
                            and len(set(declared.values())) == 1
                            and final.get("winner_group") is None)
            delta = {k: (declared[k] - summed[k]) for k in declared
                     if isinstance(declared.get(k), int) and isinstance(summed.get(k), int)}
            hint = ""
            if any(v == 10 for v in delta.values()):
                hint = (" — a +10 delta looks like the DIVERSITY reward baked into the totals; "
                        "it lands in the league standings, never in total_score (SPEC §6.2)")
            check("result: totals are the sum of the sub-game scores (derived, not declared; "
                  "+2 each under a COHERENT series tie — equal totals, null winner)",
                  summed == declared or (tie_coherent and tie_adjusted == declared),
                  f"summed {totals}, declared {declared}, series_tie {series_tie}{hint}")

            # --- the league fields: the only graded inputs, previously ungated ----------
            # (anrbj666's P5-2.) Everything below is CONDITIONAL on the key being present,
            # and posture-aware: a friendly legitimately declares unbumped counts and
            # all-false diversity (PAIRING-PLAYBOOK 4d), so absence-of-award never fails —
            # only arithmetic impossibilities and awards to the wrong side do.
            row_groups = set(declared)
            if "winner_group" in final:
                winner = final["winner_group"]
                if len(set(declared.values())) == 1:
                    check("result: equal totals mean NO winner (and a declared series tie)",
                          winner is None and series_tie,
                          f"totals {declared} are equal but winner_group={winner!r}, "
                          f"series_tie={series_tie}")
                else:
                    true_winner = max(declared, key=lambda g: declared[g])
                    check("result: winner_group is the side with the higher total",
                          winner == true_winner,
                          f"totals {declared} but winner_group={winner!r}")
            if "sub_games_won" in final and subs:
                derived_won = {g: sum(1 for sg in subs
                                      if isinstance(sg.get("score"), dict)
                                      and all(x in sg["score"] for x in row_groups)
                                      and sg["score"][g] == max(sg["score"].values())
                                      and len(set(sg["score"].values())) > 1)
                               for g in row_groups}
                check("result: sub_games_won derives from the sub-game rows",
                      {g: final["sub_games_won"].get(g) for g in row_groups} == derived_won,
                      f"rows give {derived_won}, declared {final['sub_games_won']}")
            if "ties" in final and subs and all("score" in sg for sg in subs):
                # The full identity (anrbj666's P5-13): zeroed rows are credited to NOBODY, so
                # the naive won+won+ties == num_sub_games fails any series with a technical
                # loss. The true identity carries the zeroed rows explicitly.
                zeroed = sum(1 for sg in subs
                             if set(sg["score"].values()) == {0})
                tie_rows = sum(1 for sg in subs
                               if len(set(sg["score"].values())) == 1
                               and set(sg["score"].values()) != {0})
                won_total = sum(1 for sg in subs
                                if len(set(sg["score"].values())) > 1)
                check("result: won + tie rows + zeroed rows == num_sub_games (zeroed rows "
                      "are credited to nobody)",
                      won_total + tie_rows + zeroed == len(subs)
                      and final["ties"] == tie_rows,
                      f"rows: won {won_total}, ties {tie_rows}, zeroed {zeroed}, "
                      f"declared ties {final['ties']}, num {len(subs)}")
            if "tokens_total_series" in final and subs and all("tokens" in sg for sg in subs):
                derived_tokens = {g: sum(sg["tokens"].get(g, 0) for sg in subs)
                                  for g in row_groups}
                check("result: tokens_total_series is the sum of the per-row tokens",
                      {g: final["tokens_total_series"].get(g) for g in row_groups}
                      == derived_tokens,
                      f"rows sum to {derived_tokens}, declared {final['tokens_total_series']}")
            if isinstance(final.get("games_played_including_this"), dict):
                counts = final["games_played_including_this"]
                check("result: game counts are non-negative integers",
                      all(isinstance(v, int) and not isinstance(v, bool) and v >= 0
                          for v in counts.values()),
                      f"declared {counts}")
            if isinstance(final.get("diversity_reward_applied"), dict):
                awarded_to = [g for g, v in final["diversity_reward_applied"].items() if v]
                check("result: a diversity reward goes only to the WINNER of a FIRST meeting "
                      "(all-false is always legal — the friendly posture)",
                      all(g == final.get("winner_group") for g in awarded_to)
                      and (not awarded_to or bool(final.get("first_meeting_between_groups"))),
                      f"awarded to {awarded_to}, winner {final.get('winner_group')!r}, "
                      f"first_meeting {final.get('first_meeting_between_groups')!r}")
        listed = {sg.get("sub_game_number") for sg in subs}
        logged = {int(nn) for _, nn, _ in found["log"] if nn is not None}
        if listed and logged:
            check("every log file's sub-game appears in the result",
                  logged <= listed,
                  f"logs present for {sorted(logged)}, result lists "
                  f"{sorted(x for x in listed if x is not None)}")

    # --- 7. does the uid actually DERIVE? ------------------------------------------------
    #
    # The check that matters most, and the only one that catches the failure that actually
    # happened. A uid derived from the WRONG INPUT — a whole config rather than the flat
    # negotiated terms — is perfectly deterministic and identical across all four artifacts, so
    # every consistency check above passes and the bundle looks healthy. Only re-derivation sees
    # it, and only the cross-team join would otherwise fail.
    gids = _group_ids(found["declaration"][0][2]) if found["declaration"] else []
    terms = None
    source = ""
    if args.terms:
        terms = json.loads(Path(args.terms).read_text(encoding="utf-8"))
        source = f"--terms {args.terms}"
    else:
        # Some artifact sets carry the flat signed set inline; use it if it is really the 14-key
        # set, rather than guessing at an extraction this kit does not pin.
        for kind, _, _, data in every:
            candidate = data.get("terms")
            if isinstance(candidate, dict) and len(candidate) == 14:
                terms, source = candidate, f"the {kind} artifact's own `terms`"
                break

    if terms is not None and len(gids) == 2:
        derived = ref.ref_game_uid(terms, *gids)
        ok = check(f"game_uid DERIVES from the flat terms ({source})", derived == uid,
                   f"derived {derived}, artifacts carry {uid}")
        if not ok:
            print("\n  ^ the uid is consistent everywhere and still wrong. That is the sneaky\n"
                  "    failure: a uid derived from the wrong input — a whole config rather than\n"
                  "    the flat 14-key negotiated terms — joins your own four files perfectly and\n"
                  "    fails only against your opponent. The reference computes\n"
                  "    derive_game_ids(terms_from_config(...), ...): the EXTRACTED keys, not the\n"
                  "    configuration they came from.")
        check("game_id derives from the same sorted pair",
              ref.ref_game_id(*gids) == next(iter(ids)))
    elif not _quiet:
        print("\n  note: pass --terms <flat signed terms>.json to verify the uid DERIVES.\n"
              "        Without it this script confirms the uid is CONSISTENT, which a uid derived\n"
              "        from the wrong input already is — that is exactly the case that has cost a\n"
              "        real pairing a clean join. The extraction of the 14 terms from a config\n"
              "        file is the reference's `terms_from_config` and is not pinned by this kit,\n"
              "        so it is not guessed here.")

    print(f"\n{'ALL ARTIFACT CHECKS PASS' if _failures == 0 else f'{_failures} FAILURE(S)'}")
    return 1 if _failures else 0


if __name__ == "__main__":
    sys.exit(main())
