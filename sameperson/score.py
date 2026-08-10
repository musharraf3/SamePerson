"""Candidate generation and pair scoring.

Two stages, and the first one is the stage that usually goes unmeasured.

Blocking decides which pairs are ever compared. A pair that blocking drops
cannot be matched at any threshold, so blocking sets a ceiling on recall
that no amount of threshold tuning can raise. Most reported match rates are
quoted after this step without saying so. This module measures it.
"""

from __future__ import annotations

from collections import defaultdict
from itertools import combinations

from .compare import (canonical_given, cmp_address, cmp_dob, cmp_exact,
                      cmp_given, cmp_identifier, cmp_phone, cmp_surname)
from .generate import Record

# Field weights. These are ours, not read off a standard. HL7's Identity
# Matching IG supplies the field set and the idea of graded confidence; its
# published weights grade the strength of an identity assertion, which is a
# different question from how much evidence a field gives that two records
# are the same person. Address is weighted low here on purpose: people move,
# so agreement is informative and disagreement is nearly not.
# The identifier carries two weights on purpose. See cmp_identifier: a
# matching national identifier is near proof, a mismatched one is mostly
# noise, and a single symmetric weight cannot express that.
IDENTIFIER_WEIGHT_AGREE = 4.0
IDENTIFIER_WEIGHT_DISAGREE = 0.5

WEIGHTS = {
    "identifier": IDENTIFIER_WEIGHT_AGREE,
    "surname": 2.0,
    "given": 2.0,
    "dob": 3.0,
    "sex": 0.5,
    "address": 1.5,
    "postal": 1.0,
    "phone": 1.5,
}


def blocking_keys(r: Record, mode: str = "multi") -> set[str]:
    """Which keys a record is filed under.

    mode="single" is the common production design: one key, surname prefix
    plus birth year. It is cheap, it is what most tutorials show, and it
    makes a person unmatchable the moment their surname changes.

    mode="multi" files each record under several independent keys, so a
    record stays reachable when any one of them breaks.
    """
    keys = set()
    if mode == "single":
        s = (r.surname or "").lower().split()
        year = r.dob[:4] if r.dob else ""
        if s and year:
            keys.add(f"sy:{s[0][:4]}|{year}")
        return keys
    g = canonical_given(r.given)
    s = (r.surname or "").lower().split()
    year = r.dob[:4] if r.dob else ""
    if s and year:
        keys.add(f"sy:{s[0][:4]}|{year}")
    if len(s) > 1:
        keys.add(f"sy:{s[-1][:4]}|{year}")
    if g and year:
        keys.add(f"gy:{g[:4]}|{year}")
    if r.dob:
        keys.add(f"d:{r.dob}")
    if r.phone:
        d = "".join(c for c in r.phone if c.isdigit())
        if len(d) >= 10:
            keys.add(f"p:{d[-10:]}")
    if r.postal and s:
        keys.add(f"zs:{r.postal}|{s[0][:4]}")
    ident = "".join(c for c in (r.identifier or "") if c.isdigit())
    if len(ident) >= 6:
        keys.add(f"i:{ident}")
    return keys


def candidate_pairs(records: list[Record],
                    mode: str = "multi") -> set[tuple[str, str]]:
    index: dict[str, list[str]] = defaultdict(list)
    for r in records:
        for k in blocking_keys(r, mode):
            index[k].append(r.record_id)
    pairs: set[tuple[str, str]] = set()
    for _key, ids in index.items():
        if len(ids) < 2 or len(ids) > 200:
            # Oversized blocks are dropped. That is a real design decision
            # with a real cost, and it is counted in the blocking report.
            continue
        for a, b in combinations(sorted(ids), 2):
            pairs.add((a, b))
    return pairs


def score_pair_naive(a: Record, b: Record) -> float:
    """The same weighted scheme with no domain knowledge in the comparators:
    strings either match exactly or they do not. This is the arm that shows
    what the fifteen lines about nicknames, compound surnames and transposed
    dates are actually worth."""
    parts = [
        ("identifier", cmp_exact(a.identifier, b.identifier)),
        ("surname", cmp_exact(a.surname, b.surname)),
        ("given", cmp_exact(a.given, b.given)),
        ("dob", cmp_exact(a.dob, b.dob)),
        ("sex", cmp_exact(a.sex, b.sex)),
        ("address", cmp_exact(a.address, b.address)),
        ("postal", cmp_exact(a.postal, b.postal)),
        ("phone", cmp_phone(a.phone, b.phone)),
    ]
    num = den = 0.0
    for name, s in parts:
        if s is None:
            continue
        num += WEIGHTS[name] * s
        den += WEIGHTS[name]
    return num / den if den else 0.0


def score_pair(a: Record, b: Record) -> float:
    """Weighted mean over the fields that are comparable on both sides.

    A field missing on either side is excluded from both numerator and
    denominator. Absence is not disagreement, and treating it as such
    penalises exactly the people whose records are thinnest.
    """
    parts = [
        ("identifier", cmp_identifier(a.identifier, b.identifier)),
        ("surname", cmp_surname(a.surname, b.surname)),
        ("given", cmp_given(a.given, b.given)),
        ("dob", cmp_dob(a.dob, b.dob)),
        ("sex", cmp_exact(a.sex, b.sex)),
        ("address", cmp_address(a.address, b.address)),
        ("postal", cmp_exact(a.postal, b.postal)),
        ("phone", cmp_phone(a.phone, b.phone)),
    ]
    num = den = 0.0
    for name, s in parts:
        if s is None:
            continue
        if name == "identifier":
            w = (IDENTIFIER_WEIGHT_AGREE if s >= 1.0
                 else IDENTIFIER_WEIGHT_DISAGREE)
        else:
            w = WEIGHTS[name]
        num += w * s
        den += w
    if den == 0:
        return 0.0
    return num / den


def score_all(records: list[Record], mode: str = "multi",
              naive: bool = False) -> list[tuple[str, str, float]]:
    by_id = {r.record_id: r for r in records}
    fn = score_pair_naive if naive else score_pair
    return [(a, b, fn(by_id[a], by_id[b]))
            for a, b in candidate_pairs(records, mode)]


def blocking_report(records: list[Record], mode: str = "multi") -> dict:
    """How many genuinely-same-person pairs never reach the scorer."""
    by_person: dict[str, list[Record]] = defaultdict(list)
    for r in records:
        by_person[r.person_id].append(r)
    true_pairs = set()
    for _pid, rs in by_person.items():
        for a, b in combinations(sorted(r.record_id for r in rs), 2):
            true_pairs.add((a, b))
    reachable = candidate_pairs(records, mode)
    lost = true_pairs - reachable
    by_id = {r.record_id: r for r in records}
    lost_conditions: dict[str, int] = defaultdict(int)
    for a, b in lost:
        for c in set(by_id[a].conditions) | set(by_id[b].conditions):
            lost_conditions[c] += 1
    return {
        "mode": mode,
        "true_pairs": len(true_pairs),
        "candidate_pairs": len(reachable),
        "true_pairs_reachable": len(true_pairs & reachable),
        "true_pairs_lost_to_blocking": len(lost),
        "blocking_recall": (len(true_pairs & reachable) / len(true_pairs))
        if true_pairs else 0.0,
        "lost_by_condition": dict(sorted(lost_conditions.items(),
                                         key=lambda kv: -kv[1])),
    }
