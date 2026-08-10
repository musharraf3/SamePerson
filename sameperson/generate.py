"""A synthetic population and an explicit corruption model.

Every transformation applied to a record is declared here, tagged, and
recorded on the record itself. That matters more than the realism of the
name lists: the point of this file is that when the matcher fails, you can
say exactly which real-world condition caused it, because the condition is
labelled in the data.

The corruption rates below are choices, not measurements. They are stated
openly here and in the README, and the honest limit is that the absolute
error counts this repo reports depend on them. What transfers is the shape:
which conditions break matching, and who those conditions happen to.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field, asdict

GIVEN = [
    "Robert", "William", "Elizabeth", "Margaret", "Katherine", "Jennifer",
    "Michael", "Patricia", "Christopher", "Joseph", "Deborah", "Thomas",
    "Daniel", "Matthew", "Anthony", "Charles", "Susan", "Barbara",
    "Stephen", "Edward", "Francisco", "Guadalupe", "Jose", "Maria",
    "Aisha", "Nguyen", "Wei", "Priya", "Omar", "Yusuf", "Fatima", "Ling",
]
SURNAME = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller",
    "Davis", "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez",
    "Wilson", "Anderson", "Thomas", "Taylor", "Moore", "Jackson", "Martin",
    "Nguyen", "Patel", "Kim", "Chen", "Okafor", "Haddad", "Silva",
]
COMPOUND_SURNAME = [
    "Rivera Santos", "Garcia Lopez", "Hernandez Cruz", "Martinez Ruiz",
    "Gomez Vargas", "Ortiz Molina",
]
STREETS = ["Oak", "Maple", "Cedar", "Pine", "Elm", "Walnut", "Chestnut",
           "Highland", "Lincoln", "Jefferson", "Sunset", "Willow"]
SUFFIX = ["Street", "Road", "Avenue", "Drive", "Lane", "Court"]
CITIES = [("Springfield", "IL", "62704"), ("Riverside", "CA", "92501"),
          ("Fairview", "TX", "75069"), ("Georgetown", "SC", "29440"),
          ("Clinton", "IA", "52732"), ("Salem", "OR", "97301")]

# --- corruption model -------------------------------------------------------
# Each entry: tag -> probability that this condition applies to a duplicate.
# Conditions are independent and several can land on the same record.
CORRUPTIONS = {
    "nickname":        0.22,  # Robert -> Bob at a different front desk
    "name_change":     0.12,  # surname changes, most often after marriage
    "compound_split":  0.10,  # one half of a compound surname dropped
    "typo_given":      0.14,
    "typo_surname":    0.12,
    "dob_transposed":  0.07,  # day and month swapped
    "dob_typo":        0.06,
    "moved":           0.28,  # address is now different
    "phone_changed":   0.24,
    "missing_phone":   0.15,
    "missing_address": 0.10,
}


@dataclass
class Record:
    record_id: str
    person_id: str          # ground truth, never shown to the matcher
    given: str
    surname: str
    dob: str
    sex: str
    address: str
    city: str
    state: str
    postal: str
    phone: str
    identifier: str = ""
    conditions: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


def _typo(rng: random.Random, s: str) -> str:
    if len(s) < 3:
        return s
    i = rng.randrange(1, len(s) - 1)
    mode = rng.choice(("swap", "drop", "sub"))
    if mode == "swap":
        return s[:i] + s[i + 1] + s[i] + s[i + 2:]
    if mode == "drop":
        return s[:i] + s[i + 1:]
    return s[:i] + rng.choice("abcdefghijklmnopqrstuvwxyz") + s[i + 1:]


def _address(rng: random.Random) -> tuple[str, str, str, str]:
    city, state, postal = rng.choice(CITIES)
    street = f"{rng.randrange(10, 9999)} {rng.choice(STREETS)} {rng.choice(SUFFIX)}"
    return street, city, state, postal


def _phone(rng: random.Random) -> str:
    return f"({rng.randrange(200,999)}) {rng.randrange(200,999)}-{rng.randrange(1000,9999)}"


def _dob(rng: random.Random) -> str:
    y = rng.randrange(1935, 2006)
    m = rng.randrange(1, 13)
    d = rng.randrange(1, 29)
    return f"{y:04d}-{m:02d}-{d:02d}"


def make_population(n_people: int, seed: int = 20260809) -> list[Record]:
    """One canonical record per person."""
    rng = random.Random(seed)
    out = []
    for i in range(n_people):
        street, city, state, postal = _address(rng)
        surname = (rng.choice(COMPOUND_SURNAME) if rng.random() < 0.12
                   else rng.choice(SURNAME))
        out.append(Record(
            record_id=f"r{i:06d}a",
            person_id=f"p{i:06d}",
            given=rng.choice(GIVEN),
            surname=surname,
            dob=_dob(rng),
            sex=rng.choice(("F", "M")),
            address=street, city=city, state=state, postal=postal,
            phone=_phone(rng),
        ))
    return out


def _nickname_for(given: str, rng: random.Random) -> str:
    from .compare import _GROUPS
    for group in _GROUPS:
        if given.lower() == group[0]:
            return rng.choice(group[1:]).capitalize()
    return given


def make_duplicates(people: list[Record], rate: float = 0.35,
                    seed: int = 20260809) -> list[Record]:
    """For a share of people, emit a second record of the same person as it
    would appear after being registered somewhere else, later."""
    rng = random.Random(seed + 1)
    dups = []
    for p in people:
        if rng.random() > rate:
            continue
        r = Record(**{**p.as_dict(), "record_id": p.record_id[:-1] + "b",
                      "conditions": []})
        for tag, prob in CORRUPTIONS.items():
            if rng.random() >= prob:
                continue
            r.conditions.append(tag)
            if tag == "nickname":
                r.given = _nickname_for(r.given, rng)
            elif tag == "name_change":
                r.surname = rng.choice(SURNAME)
            elif tag == "compound_split":
                parts = r.surname.split()
                if len(parts) > 1:
                    r.surname = parts[0]
                else:
                    r.conditions.remove(tag)
            elif tag == "typo_given":
                r.given = _typo(rng, r.given)
            elif tag == "typo_surname":
                r.surname = _typo(rng, r.surname)
            elif tag == "dob_transposed":
                y, m, d = r.dob.split("-")
                if int(d) <= 12:
                    r.dob = f"{y}-{d}-{m}"
                else:
                    r.conditions.remove(tag)
            elif tag == "dob_typo":
                digits = list(r.dob.replace("-", ""))
                i = rng.randrange(len(digits))
                digits[i] = str((int(digits[i]) + rng.randrange(1, 9)) % 10)
                s = "".join(digits)
                r.dob = f"{s[0:4]}-{s[4:6]}-{s[6:8]}"
            elif tag == "moved":
                street, city, state, postal = _address(rng)
                r.address, r.city, r.state, r.postal = street, city, state, postal
            elif tag == "phone_changed":
                r.phone = _phone(rng)
            elif tag == "missing_phone":
                r.phone = ""
            elif tag == "missing_address":
                r.address = ""
        dups.append(r)
    return dups


def build(n_people: int = 4000, dup_rate: float = 0.35,
          seed: int = 20260809) -> list[Record]:
    people = make_population(n_people, seed)
    return people + make_duplicates(people, dup_rate, seed)
