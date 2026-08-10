"""Bring your own records: CSV, or a FHIR Bundle of Patient resources.

The synthetic population in this repo is a demonstration. The reporting is
the part worth pointing at a real master patient index, and neither needs
the other.

FHIR note. The Patient resource holds names as a list with a use code, and
the previous name is often still there with use="old" — which is exactly the
information a matcher needs when a surname has changed, and exactly the
information a flattened export usually drops. `from_fhir_bundle` keeps every
name it finds and emits one record per name variant, so a person who married
is reachable under both. That behaviour is the whole reason to read FHIR
rather than a CSV someone exported from it.
"""

from __future__ import annotations

import csv
import json

from .generate import Record

# Column names understood without configuration. Synthea's patients.csv uses
# the first spelling in each group.
DEFAULT_MAP = {
    "record_id": ("Id", "id", "record_id", "RECORD_ID", "rec_id"),
    "person_id": ("person_id", "PERSON_ID", "truth_id"),
    "given": ("FIRST", "first", "given", "first_name", "GivenName",
              "given_name"),
    "surname": ("LAST", "last", "surname", "family", "last_name"),
    "dob": ("BIRTHDATE", "birthdate", "dob", "birth_date", "DOB",
            "date_of_birth"),
    "sex": ("GENDER", "gender", "sex", "SEX"),
    "address": ("ADDRESS", "address", "street", "line"),
    "city": ("CITY", "city", "suburb"),
    "state": ("STATE", "state"),
    "postal": ("ZIP", "zip", "postal", "postalCode", "postal_code",
               "postcode"),
    "phone": ("PHONE", "phone", "telecom", "phone_number"),
    "identifier": ("SSN", "ssn", "identifier", "soc_sec_id", "mrn", "MRN"),
}


def _pick(row: dict, names: tuple[str, ...]) -> str:
    for n in names:
        if n in row and row[n] is not None:
            return str(row[n]).strip()
    return ""


def _normalise_header(row: dict) -> dict:
    """Header cells arrive with whatever whitespace the exporter left on
    them. FEBRL's are written as ", given_name", and a lookup that misses
    silently produces an empty field rather than an error, which is the
    worst possible failure for a matcher: it reports confidently on nothing.
    """
    return {(k or "").strip(): v for k, v in row.items()}


def _iso_date(v: str) -> str:
    v = (v or "").strip()
    if len(v) == 8 and v.isdigit():          # YYYYMMDD
        return f"{v[0:4]}-{v[4:6]}-{v[6:8]}"
    return v[:10]


def from_csv(path: str, mapping: dict | None = None) -> list[Record]:
    m = {**DEFAULT_MAP, **(mapping or {})}
    out = []
    with open(path, newline="", encoding="utf-8") as fh:
        for i, raw in enumerate(csv.DictReader(fh)):
            row = _normalise_header(raw)
            rid = _pick(row, m["record_id"]) or f"csv{i:06d}"
            out.append(Record(
                record_id=rid,
                # No ground truth in a real extract. The person_id defaults to
                # the record id, which means every record is its own person
                # until the matcher says otherwise. Supply a truth column only
                # if you actually have adjudicated pairs.
                person_id=_pick(row, m["person_id"]) or rid,
                given=_pick(row, m["given"]),
                surname=_pick(row, m["surname"]),
                dob=_iso_date(_pick(row, m["dob"])),
                sex=(_pick(row, m["sex"])[:1] or "").upper(),
                address=_pick(row, m["address"]),
                city=_pick(row, m["city"]),
                state=_pick(row, m["state"]),
                postal=_pick(row, m["postal"]),
                phone=_pick(row, m["phone"]),
                identifier=_pick(row, m["identifier"]),
            ))
    return out


def _addresses(p: dict) -> tuple[str, str, str, str]:
    for a in p.get("address", []) or []:
        line = " ".join(a.get("line", []) or [])
        return (line, a.get("city", ""), a.get("state", ""),
                a.get("postalCode", ""))
    return ("", "", "", "")


def _phone(p: dict) -> str:
    for t in p.get("telecom", []) or []:
        if t.get("system") == "phone" and t.get("value"):
            return t["value"]
    return ""


def from_fhir_bundle(path: str) -> list[Record]:
    """One record per name variant on each Patient, so an 'old' name stays
    reachable. Every variant carries the same person_id, because FHIR already
    told us they are the same person."""
    with open(path, encoding="utf-8") as fh:
        bundle = json.load(fh)
    out = []
    for entry in bundle.get("entry", []) or []:
        res = entry.get("resource", {})
        if res.get("resourceType") != "Patient":
            continue
        pid = res.get("id", "")
        names = res.get("name", []) or [{}]
        street, city, state, postal = _addresses(res)
        for j, nm in enumerate(names):
            given = " ".join(nm.get("given", []) or [])
            out.append(Record(
                record_id=f"{pid}#{j}",
                person_id=pid,
                given=given,
                surname=nm.get("family", ""),
                dob=(res.get("birthDate") or "")[:10],
                sex=(res.get("gender") or "")[:1].upper(),
                address=street, city=city, state=state, postal=postal,
                phone=_phone(res),
                conditions=[f"name_use:{nm.get('use', 'unspecified')}"],
            ))
    return out
