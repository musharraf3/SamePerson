"""The contribution: report the two errors separately, in people, and refuse
to collapse them into one number.

A matcher makes two mistakes and they are not the same mistake.

  over-merge   two people become one chart. Someone can be handed another
               person's allergies, medications and history. Active harm,
               and hard to unpick once downstream systems have copied it.

  under-merge  one person stays two charts. Fragmented history, repeated
               imaging, an interaction nobody sees. Passive harm, extremely
               common, and largely invisible because nothing looks wrong.

Standard practice picks the threshold that maximises F1 or accuracy. Both
treat one over-merge as exactly equal to one under-merge. Nobody working in
clinical safety believes that, and yet the number that gets published is
almost always the one that assumes it.

So this module never prints a single accuracy figure. It prints both error
counts at every threshold, the size of the band where the system should not
decide alone, and which conditions in the data the errors land on.
"""

from __future__ import annotations

from collections import defaultdict

from .generate import Record


def label_pairs(records: list[Record],
                scored: list[tuple[str, str, float]]
                ) -> list[tuple[str, str, float, bool]]:
    person = {r.record_id: r.person_id for r in records}
    return [(a, b, s, person[a] == person[b]) for a, b, s in scored]


def sweep(labelled, thresholds, lost_to_blocking: int = 0) -> list[dict]:
    """Error counts at each threshold. `lost_to_blocking` is added to the
    under-merge count because a pair that was never compared is a pair the
    system got wrong, however comfortable it is to exclude it."""
    rows = []
    for t in thresholds:
        over = sum(1 for _a, _b, s, same in labelled if s >= t and not same)
        under = sum(1 for _a, _b, s, same in labelled if s < t and same)
        rows.append({
            "threshold": round(t, 3),
            "over_merge": over,
            "under_merge": under + lost_to_blocking,
            "under_merge_scored_only": under,
        })
    return rows


def review_band(labelled, low: float, high: float,
                lost_to_blocking: int = 0) -> dict:
    """Pairs in [low, high) are not decided by the system at all.

    The number that matters operationally is how many pairs land here,
    because that is a staffing cost. A matcher that quietly auto-decides
    them is not more accurate, it has just moved the cost somewhere it
    doesn't get counted.
    """
    band = [(a, b, s, same) for a, b, s, same in labelled if low <= s < high]
    auto_over = sum(1 for _a, _b, s, same in labelled if s >= high and not same)
    auto_under = sum(1 for _a, _b, s, same in labelled if s < low and same)
    return {
        "low": low, "high": high,
        "pairs_in_band": len(band),
        "true_pairs_in_band": sum(1 for *_x, same in band if same),
        "false_pairs_in_band": len(band) - sum(1 for *_x, same in band if same),
        "auto_over_merge": auto_over,
        "auto_under_merge": auto_under + lost_to_blocking,
    }


def threshold_for_harm_ratio(rows: list[dict], ratio: float) -> dict:
    """Choose an operating point by stating the trade-off out loud.

    `ratio` is how many under-merges you would accept to avoid one
    over-merge. Setting it to 1 reproduces the usual symmetric assumption.
    Whatever you set it to, it is now written down, versioned, and arguable
    by someone who does not write code, which is the entire point.
    """
    best = None
    for r in rows:
        cost = ratio * r["over_merge"] + r["under_merge"]
        if best is None or cost < best[0]:
            best = (cost, r)
    return {"harm_ratio": ratio, "cost": best[0], **best[1]}


def by_condition(labelled, records: list[Record], threshold: float) -> dict:
    """Which conditions in the data the under-merges land on.

    This is the equity question in operational form. Matching does not fail
    at random. It fails on records that changed, and records change most for
    people who move, marry, or have a name the registration form was not
    designed to hold.
    """
    cond = {r.record_id: set(r.conditions) for r in records}
    total = defaultdict(int)
    missed = defaultdict(int)
    for a, b, s, same in labelled:
        if not same:
            continue
        tags = cond[a] | cond[b]
        for t in tags or {"no_condition"}:
            total[t] += 1
            if s < threshold:
                missed[t] += 1
    out = {}
    for t, n in total.items():
        out[t] = {"true_pairs": n, "missed": missed[t],
                  "miss_rate": round(missed[t] / n, 4) if n else 0.0}
    return dict(sorted(out.items(), key=lambda kv: -kv[1]["miss_rate"]))
