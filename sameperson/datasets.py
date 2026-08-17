"""Load the public benchmark datasets.

FEBRL ships ground truth inside the record id: `rec-1234-org` is an original
and `rec-1234-dup-0` is a duplicate of that same person. So the person id is
not something this repo decides, and neither is the corruption. Both were
fixed by the Febrl project before I ever saw the files.

That matters for the same reason it mattered in WhoCounts: you can make your
own test data agree with you. These files were built by someone else, from
real name and address frequency tables, using an error model derived from
published studies of data entry mistakes.

Conditions are *derived*, not declared. For each duplicate this module diffs
it against its original and records which fields actually differ. Nothing is
tagged by hand, so the equity breakdown later reflects what the benchmark
did rather than what I would have chosen to simulate.
"""

from __future__ import annotations

import csv
import os
from collections import defaultdict

from .generate import Record

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "data", "febrl")

DATASETS = {
    "febrl1": ("dataset1.csv", "500 people, one duplicate each, light corruption"),
    "febrl2": ("dataset2.csv", "4,000 people, up to 6 duplicates, moderate"),
    "febrl3": ("dataset3.csv", "2,000 people, up to 6 duplicates, heavy"),
}


def _clean(row: dict) -> dict:
    return {(k or "").strip(): (v or "").strip() for k, v in row.items()}


def _dob(v: str) -> str:
    v = (v or "").strip()
    if len(v) == 8 and v.isdigit():
        return f"{v[0:4]}-{v[4:6]}-{v[6:8]}"
    return ""


def _person_id(rec_id: str) -> str:
    parts = rec_id.split("-")
    return parts[1] if len(parts) > 1 else rec_id


def load_febrl(name: str = "febrl1",
               drop_identifier: bool = False) -> list[Record]:
    """`drop_identifier=True` blanks the soc_sec_id column on every record.

    FEBRL ships a national-identifier-shaped field. It is a synthetic
    social-security-style number, not any country's health identifier, so
    read this as "a strong shared identifier is available" rather than as a
    claim about Australia.

    That distinction is the point. US patient matching across organisations
    usually has no such field. HIPAA itself ordered HHS to adopt a unique
    health identifier in 1996; a rider first attached to the FY1999
    Labor-HHS appropriations act blocked any funding to do it, and the rider
    has been carried forward every year since.

    So the two runs are the same records with and without the one field that
    would make this easy. The gap between them is the share of the problem
    that is a policy choice rather than an engineering one.
    """
    fn, _desc = DATASETS[name]
    path = os.path.join(DATA, fn)
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"{path} not found. Run: python scripts/fetch_data.py")
    out: list[Record] = []
    with open(path, newline="", encoding="utf-8") as fh:
        for raw in csv.DictReader(fh):
            r = _clean(raw)
            street = " ".join(x for x in (r.get("street_number", ""),
                                          r.get("address_1", "")) if x)
            out.append(Record(
                record_id=r["rec_id"],
                person_id=_person_id(r["rec_id"]),
                given=r.get("given_name", ""),
                surname=r.get("surname", ""),
                dob=_dob(r.get("date_of_birth", "")),
                sex="",                       # not present in FEBRL
                address=street,
                city=r.get("suburb", ""),
                state=r.get("state", ""),
                postal=r.get("postcode", ""),
                phone="",                     # not present in FEBRL
                identifier="" if drop_identifier else r.get("soc_sec_id", ""),
            ))
    return _derive_conditions(out)


_FIELDS = ("given", "surname", "dob", "address", "city", "postal",
           "state", "identifier")


def _derive_conditions(records: list[Record]) -> list[Record]:
    """Diff each duplicate against its original and label what differs."""
    originals: dict[str, Record] = {}
    for r in records:
        if r.record_id.endswith("org"):
            originals[r.person_id] = r
    for r in records:
        org = originals.get(r.person_id)
        if org is None or org.record_id == r.record_id:
            continue
        tags = []
        for f in _FIELDS:
            a, b = getattr(org, f), getattr(r, f)
            if a == b:
                continue
            if not b:
                tags.append(f"{f}_missing")
            elif not a:
                tags.append(f"{f}_added")
            else:
                tags.append(f"{f}_changed")
        r.conditions = tags or ["identical_copy"]
    return records


def counts(records: list[Record]) -> dict:
    per = defaultdict(int)
    for r in records:
        per[r.person_id] += 1
    pairs = sum(n * (n - 1) // 2 for n in per.values())
    return {"records": len(records), "people": len(per), "true_pairs": pairs,
            "max_records_per_person": max(per.values()) if per else 0}
