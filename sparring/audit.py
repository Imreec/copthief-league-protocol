"""The end-of-game mutual audit — the iron rule (book ch.5, App. E rules 19-20).

Each side reveals every record with its nonce; the **opponent** re-hashes them with its own
serializer and compares against the commit it was sent at the time. Any mismatch is tampering by
definition — "there is no room here for interpretation or a statistical margin" — and the sanction
is total, independent of what happened on the board.

Which is exactly why a serialization difference is so expensive. Two *honest* peers whose JSON
differs by one escaped character will each fail to reproduce the other's commits, each conclude
the other tampered, and both score zero. That is the failure this whole kit exists to prevent, and
it is the one a practice run should surface.

When a mismatch is found, the report names the step and prints **both canonical strings**, plus a
pointer to the kit's ``divergent_forms`` vector — because the most common cause is not tampering
at all but having built the commit from a different one of the release's three published
constructions.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sparring import kitref


@dataclass
class AuditResult:
    passed: bool
    verified_steps: int
    failed_steps: list[int] = field(default_factory=list)
    detail: str = ""
    skipped: bool = False

    def to_wire(self) -> dict:
        return {"passed": self.passed, "verified_steps": self.verified_steps,
                "failed_steps": list(self.failed_steps), "skipped": self.skipped}


def audit_records(records: list[dict]) -> AuditResult:
    """Re-hash every revealed record with OUR serializer. This is the cross-team check."""
    failed: list[int] = []
    notes: list[str] = []
    for record in records:
        payload, nonce, claimed = record.get("payload"), record.get("nonce"), record.get("commit")
        if payload is None or nonce is None or claimed is None:
            failed.append(int((payload or {}).get("step", -1)))
            notes.append("a revealed record is missing payload, nonce or commit")
            continue
        recomputed = kitref.commit(payload, nonce)
        if recomputed != claimed:
            step = int(payload.get("step", -1))
            failed.append(step)
            if len(notes) < 3:      # enough to diagnose; not the whole log
                notes.append(
                    f"step {step}: they committed {claimed}, we recompute {recomputed}\n"
                    f"      our canonical form of their payload:\n"
                    f"      {kitref.canonical_str(payload)}")
    result = AuditResult(passed=not failed, verified_steps=len(records) - len(failed),
                         failed_steps=failed)
    if failed:
        result.detail = (
            "\n    ".join(notes) +
            "\n    Before concluding tampering: the release publishes THREE different commit "
            "constructions, and building from the wrong one fails every audit in good faith. "
            "Hash one of their records under all three with the `divergent_forms` entry in "
            "vectors/commit_reveal.json — if one of the others matches, that is the bug. "
            "Otherwise compare the canonical strings for an escaped non-ASCII character "
            "(SPEC section 2).")
    return result


def skipped() -> AuditResult:
    """No audit is possible when a game never produced revealed records.

    The reference skips the audit on timeout and stop, and so do we — but it is recorded as
    skipped rather than passed. A hollow "verified" entry in an artifact is worse than an honest
    absence.
    """
    return AuditResult(passed=False, verified_steps=0, skipped=True,
                       detail="no revealed records — the game never reached settlement")
