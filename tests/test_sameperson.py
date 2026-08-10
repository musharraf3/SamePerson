import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sameperson.compare import (cmp_dob, cmp_given, cmp_phone, cmp_surname,
                                jaro_winkler)
from sameperson.generate import Record, build, make_population
from sameperson.harm import (by_condition, label_pairs, review_band, sweep,
                             threshold_for_harm_ratio)
from sameperson.score import (blocking_keys, blocking_report, candidate_pairs,
                              score_all, score_pair)


def _rec(**kw):
    base = dict(record_id="x", person_id="p", given="Robert", surname="Smith",
                dob="1970-03-04", sex="M", address="12 Oak Street",
                city="Salem", state="OR", postal="97301",
                phone="(503) 555-1212")
    base.update(kw)
    return Record(**base)


# --- comparators ------------------------------------------------------------

def test_nickname_is_full_agreement():
    assert cmp_given("Robert", "Bob") == 1.0
    assert cmp_given("Elizabeth", "Liz") == 1.0


def test_different_names_are_not_agreement():
    assert cmp_given("Robert", "Susan") < 0.7


def test_missing_field_returns_none_not_zero():
    # The distinction the whole scoring rule depends on.
    assert cmp_given("Robert", "") is None
    assert cmp_surname("", "Smith") is None
    assert cmp_phone("", "5035551212") is None


def test_compound_surname_half_dropped():
    assert cmp_surname("Rivera Santos", "Rivera") == 0.9
    assert cmp_surname("Rivera-Santos", "Santos") == 0.9


def test_unrelated_surnames_score_low():
    assert cmp_surname("Okafor", "Nguyen") < 0.6


def test_dob_transposition_and_typo():
    assert cmp_dob("1970-03-04", "1970-04-03") == 0.85
    assert cmp_dob("1970-03-04", "1970-03-05") == 0.7
    assert cmp_dob("1970-03-04", "1988-11-22") == 0.0


def test_jaro_winkler_bounds():
    assert jaro_winkler("smith", "smith") == 1.0
    assert 0.0 <= jaro_winkler("smith", "xyzab") <= 1.0


# --- scoring ----------------------------------------------------------------

def test_identical_records_score_one():
    assert score_pair(_rec(), _rec()) == 1.0


def test_absent_field_does_not_penalise():
    full = score_pair(_rec(), _rec())
    thin = score_pair(_rec(phone=""), _rec(phone=""))
    assert thin == full == 1.0


def test_score_is_bounded():
    a = _rec()
    b = _rec(given="Susan", surname="Okafor", dob="1988-11-22",
             sex="F", address="9 Pine Road", postal="62704",
             phone="(217) 555-9999")
    assert 0.0 <= score_pair(a, b) <= 1.0


# --- blocking ---------------------------------------------------------------

def test_single_key_mode_emits_one_key():
    assert len(blocking_keys(_rec(), "single")) == 1


def test_multi_key_mode_emits_more():
    assert len(blocking_keys(_rec(), "multi")) > 1


def test_surname_change_is_unreachable_under_single_key():
    a = _rec(record_id="a", surname="Smith")
    b = _rec(record_id="b", surname="Okafor")
    assert ("a", "b") not in candidate_pairs([a, b], "single")
    assert ("a", "b") in candidate_pairs([a, b], "multi")


def test_blocking_report_counts_true_pairs():
    recs = build(200, 0.5)
    rep = blocking_report(recs, "multi")
    assert rep["true_pairs"] > 0
    assert rep["true_pairs_reachable"] + rep["true_pairs_lost_to_blocking"] \
        == rep["true_pairs"]
    assert 0.0 <= rep["blocking_recall"] <= 1.0


def test_multi_key_recall_beats_single_key():
    recs = build(600, 0.5)
    single = blocking_report(recs, "single")["blocking_recall"]
    multi = blocking_report(recs, "multi")["blocking_recall"]
    assert multi > single


# --- harm reporting ---------------------------------------------------------

def test_sweep_counts_both_errors_separately():
    recs = build(300, 0.5)
    lab = label_pairs(recs, score_all(recs))
    rows = sweep(lab, [0.6, 0.9])
    assert rows[0]["over_merge"] >= rows[1]["over_merge"]
    assert rows[0]["under_merge"] <= rows[1]["under_merge"]


def test_blocking_losses_are_added_to_under_merges():
    recs = build(300, 0.5)
    lab = label_pairs(recs, score_all(recs))
    plain = sweep(lab, [0.8])[0]
    with_lost = sweep(lab, [0.8], lost_to_blocking=7)[0]
    assert with_lost["under_merge"] == plain["under_merge"] + 7
    assert with_lost["under_merge_scored_only"] == plain["under_merge"]


def test_harm_ratio_of_one_is_the_symmetric_case():
    rows = [{"threshold": 0.7, "over_merge": 10, "under_merge": 5},
            {"threshold": 0.9, "over_merge": 1, "under_merge": 40}]
    assert threshold_for_harm_ratio(rows, 1)["threshold"] == 0.7
    assert threshold_for_harm_ratio(rows, 50)["threshold"] == 0.9


def test_review_band_holds_out_its_pairs():
    recs = build(300, 0.5)
    lab = label_pairs(recs, score_all(recs))
    band = review_band(lab, 0.72, 0.88)
    assert band["pairs_in_band"] == (band["true_pairs_in_band"]
                                    + band["false_pairs_in_band"])


def test_unchanged_records_are_never_missed():
    """The control. If nothing about a person's demographics changed and the
    matcher still misses the pair, the matcher is broken rather than strict."""
    recs = build(1500, 0.5)
    lab = label_pairs(recs, score_all(recs))
    cond = by_condition(lab, recs, 0.80)
    assert cond["no_condition"]["missed"] == 0


def test_population_is_deterministic():
    assert [r.as_dict() for r in make_population(50, 7)] == \
           [r.as_dict() for r in make_population(50, 7)]


# --- the public benchmark ---------------------------------------------------

import pytest  # noqa: E402

from sameperson.compare import cmp_identifier                    # noqa: E402
from sameperson.datasets import DATA, counts, load_febrl         # noqa: E402

_HAVE_FEBRL = os.path.exists(os.path.join(DATA, "dataset1.csv"))
needs_febrl = pytest.mark.skipif(
    not _HAVE_FEBRL, reason="run scripts/fetch_data.py first")


def test_identifier_agreement_is_strong_disagreement_is_not():
    assert cmp_identifier("1234567", "1234567") == 1.0
    assert cmp_identifier("1234567", "1234568") == 0.5   # one digit
    assert cmp_identifier("1234567", "9876543") == 0.0
    assert cmp_identifier("", "1234567") is None


def test_identifier_mismatch_is_weighted_down():
    """A wrong digit in a national id must not outweigh agreeing name and
    date of birth. This is the asymmetry the scorer exists to express."""
    a = _rec(identifier="1234567")
    b = _rec(identifier="9876543")
    assert score_pair(a, b) > 0.8


@needs_febrl
def test_febrl_loads_with_ground_truth():
    recs = load_febrl("febrl1")
    c = counts(recs)
    assert c["records"] == 1000
    assert c["people"] == 500
    assert c["true_pairs"] == 500


@needs_febrl
def test_febrl_person_id_comes_from_the_record_id():
    recs = load_febrl("febrl1")
    org = [r for r in recs if r.record_id.endswith("org")][0]
    dups = [r for r in recs
            if r.person_id == org.person_id and r.record_id != org.record_id]
    assert dups, "every febrl1 original has exactly one duplicate"


@needs_febrl
def test_conditions_are_derived_not_declared():
    recs = load_febrl("febrl3")
    tags = {t for r in recs for t in r.conditions}
    # Derived tags name a field and what happened to it.
    assert any(t.endswith("_changed") for t in tags)
    assert all(t == "identical_copy" or t.rsplit("_", 1)[0] in
               ("given", "surname", "dob", "address", "city", "postal",
                "state", "identifier") for t in tags)


@needs_febrl
def test_dropping_the_identifier_makes_matching_harder():
    """The policy counterfactual. Same file, read twice."""
    with_id = load_febrl("febrl3")
    without = load_febrl("febrl3", drop_identifier=True)
    assert all(r.identifier == "" for r in without)
    a = blocking_report(with_id, "multi")["blocking_recall"]
    b = blocking_report(without, "multi")["blocking_recall"]
    assert a > b


@needs_febrl
def test_multi_key_beats_single_key_on_the_benchmark():
    for name in ("febrl1", "febrl2", "febrl3"):
        recs = load_febrl(name)
        single = blocking_report(recs, "single")["blocking_recall"]
        multi = blocking_report(recs, "multi")["blocking_recall"]
        assert multi > single + 0.2, name


@needs_febrl
def test_csv_adapter_survives_padded_headers(tmp_path):
    """FEBRL writes its header as ', given_name'. A lookup that misses a
    padded column returns empty and the matcher then reports confidently on
    nothing, which is worse than crashing."""
    from sameperson.adapter import from_csv
    src = os.path.join(DATA, "dataset1.csv")
    recs = from_csv(src)
    assert len(recs) == 1000
    assert sum(1 for r in recs if r.given) > 900
    assert sum(1 for r in recs if r.dob) > 900
    assert sum(1 for r in recs if r.identifier) > 900
    assert recs[0].record_id.startswith("rec-")
    assert all(len(r.dob) == 10 for r in recs if r.dob)
