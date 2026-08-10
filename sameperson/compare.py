"""Field comparators. Pure stdlib, no dependencies.

Every comparator returns a float in [0.0, 1.0]. 1.0 means "these agree",
0.0 means "these disagree". A comparator returns None when either side is
missing, which is different from disagreement and is handled separately in
scoring: an absent field must not count as evidence against a match.
"""

from __future__ import annotations

# Nicknames observed in US demographic data. Deliberately short and explicit
# rather than a large opaque table, so a reviewer can see exactly what the
# matcher treats as equivalent.
NICKNAMES: dict[str, str] = {}
_GROUPS = [
    ("robert", "bob", "rob", "bobby"),
    ("william", "will", "bill", "billy"),
    ("richard", "rick", "dick", "rich"),
    ("james", "jim", "jimmy", "jamie"),
    ("john", "jack", "johnny"),
    ("michael", "mike", "mick"),
    ("elizabeth", "liz", "beth", "betty", "eliza"),
    ("margaret", "maggie", "peggy", "meg"),
    ("katherine", "kathy", "kate", "katie", "kat"),
    ("jennifer", "jen", "jenny"),
    ("patricia", "pat", "patty", "trish"),
    ("deborah", "deb", "debbie"),
    ("christopher", "chris", "topher"),
    ("joseph", "joe", "joey"),
    ("thomas", "tom", "tommy"),
    ("daniel", "dan", "danny"),
    ("matthew", "matt"),
    ("anthony", "tony"),
    ("charles", "charlie", "chuck"),
    ("susan", "sue", "susie"),
    ("barbara", "barb", "babs"),
    ("stephen", "steve", "steven"),
    ("edward", "ed", "eddie", "ted"),
    ("francisco", "paco", "pancho"),
    ("guadalupe", "lupe"),
    ("jose", "pepe"),
]
for _g in _GROUPS:
    for _n in _g:
        NICKNAMES[_n] = _g[0]


def canonical_given(name: str) -> str:
    n = (name or "").strip().lower()
    return NICKNAMES.get(n, n)


def jaro(a: str, b: str) -> float:
    """Jaro similarity. Implemented here so the repo has zero dependencies
    and so the exact behaviour is inspectable rather than delegated."""
    if a == b:
        return 1.0
    if not a or not b:
        return 0.0
    window = max(len(a), len(b)) // 2 - 1
    if window < 0:
        window = 0
    a_flags = [False] * len(a)
    b_flags = [False] * len(b)
    matches = 0
    for i, ch in enumerate(a):
        lo = max(0, i - window)
        hi = min(i + window + 1, len(b))
        for j in range(lo, hi):
            if not b_flags[j] and b[j] == ch:
                a_flags[i] = b_flags[j] = True
                matches += 1
                break
    if matches == 0:
        return 0.0
    transpositions = 0
    k = 0
    for i, ch in enumerate(a):
        if a_flags[i]:
            while not b_flags[k]:
                k += 1
            if ch != b[k]:
                transpositions += 1
            k += 1
    t = transpositions / 2
    m = float(matches)
    return (m / len(a) + m / len(b) + (m - t) / m) / 3.0


def jaro_winkler(a: str, b: str, prefix_weight: float = 0.1) -> float:
    """Jaro-Winkler. The prefix boost helps with typos late in a string and
    hurts when the change is at the front, which is exactly what happens to
    surnames that gain a prefix. That trade-off is why the surname comparator
    below does not rely on this alone."""
    j = jaro(a, b)
    if j < 0.7:
        return j
    prefix = 0
    for x, y in zip(a[:4], b[:4]):
        if x != y:
            break
        prefix += 1
    return j + prefix * prefix_weight * (1 - j)


def cmp_given(a: str, b: str) -> float | None:
    if not a or not b:
        return None
    ca, cb = canonical_given(a), canonical_given(b)
    if ca == cb:
        return 1.0
    return jaro_winkler(a.lower(), b.lower())


def _surname_parts(name: str) -> list[str]:
    return [p for p in (name or "").lower().replace("-", " ").split() if p]


def cmp_surname(a: str, b: str) -> float | None:
    """Surnames change, and they change in structured ways: marriage,
    hyphenation, and compound Hispanic surnames where one half gets dropped
    by a registration form with a single Last Name box. A pure string
    distance treats 'Rivera Santos' -> 'Rivera' as a large change. It isn't.
    """
    if not a or not b:
        return None
    if a.lower() == b.lower():
        return 1.0
    pa, pb = _surname_parts(a), _surname_parts(b)
    if not pa or not pb:
        return None
    # One name's parts are a subset of the other's: dropped or added half.
    if set(pa) <= set(pb) or set(pb) <= set(pa):
        return 0.9
    # Any shared component at all is meaningful evidence.
    if set(pa) & set(pb):
        return 0.8
    return jaro_winkler(" ".join(pa), " ".join(pb))


def cmp_dob(a: str, b: str) -> float | None:
    """Dates of birth are entered as digits and fail as digits. The two
    dominant failures are a transposed day/month and a single wrong digit.
    Both leave the record recoverable; a genuinely different date does not.
    Expects ISO YYYY-MM-DD."""
    if not a or not b:
        return None
    if a == b:
        return 1.0
    try:
        ya, ma, da = a.split("-")
        yb, mb, db = b.split("-")
    except ValueError:
        return 0.0
    if ya == yb and ma == db and da == mb:
        return 0.85  # day/month transposed
    digits_a = (ya + ma + da)
    digits_b = (yb + mb + db)
    if len(digits_a) == len(digits_b):
        diff = sum(1 for x, y in zip(digits_a, digits_b) if x != y)
        if diff == 1:
            return 0.7  # single digit typo
        if diff == 2 and ya == yb:
            return 0.5
    return 0.0


def cmp_exact(a: str, b: str) -> float | None:
    if not a or not b:
        return None
    return 1.0 if a.strip().lower() == b.strip().lower() else 0.0


def _digits(s: str) -> str:
    return "".join(c for c in (s or "") if c.isdigit())


def cmp_phone(a: str, b: str) -> float | None:
    da, db = _digits(a), _digits(b)
    if not da or not db:
        return None
    if da[-10:] == db[-10:]:
        return 1.0
    return 0.0


def cmp_identifier(a: str, b: str) -> float | None:
    """A national identifier is the strongest field there is, and it is
    strong in one direction only.

    Agreement is close to proof: two different people almost never carry the
    same number. Disagreement proves very little, because the number is long,
    it is keyed by hand, and it is frequently absent or wrong. So this
    returns a score, and the scorer weights it asymmetrically - heavily when
    it agrees, barely at all when it does not. Treating a mistyped digit as
    evidence of a different person is how a matcher loses someone.
    """
    da, db = _digits(a), _digits(b)
    if not da or not db:
        return None
    if da == db:
        return 1.0
    if len(da) == len(db):
        diff = sum(1 for x, y in zip(da, db) if x != y)
        if diff == 1:
            return 0.5
    return 0.0


def cmp_address(a: str, b: str) -> float | None:
    """Street address after light normalisation. People move, so a
    disagreement here is weak evidence of being different people, which is
    reflected in the weight rather than in this score."""
    if not a or not b:
        return None
    norm = {
        "street": "st", "road": "rd", "avenue": "ave", "drive": "dr",
        "lane": "ln", "court": "ct", "boulevard": "blvd", "north": "n",
        "south": "s", "east": "e", "west": "w", "apartment": "apt",
    }
    def n(s: str) -> str:
        out = []
        for tok in s.lower().replace(",", " ").replace(".", " ").split():
            out.append(norm.get(tok, tok))
        return " ".join(out)
    na, nb = n(a), n(b)
    if na == nb:
        return 1.0
    return jaro_winkler(na, nb)
