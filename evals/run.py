"""Reproduce every number in the README.

    python scripts/fetch_data.py     # once, ~2 MB from PyPI
    python evals/run.py

Four datasets. Three of them are the FEBRL public benchmark, where the
records, the corruption and the ground truth were all fixed by someone else.
The fourth is this repo's own generated population, and it is here as a
control rather than as evidence: it exists so that a matcher which failed
everything would be visibly distinguishable from one that discriminates.

Three arms per dataset. Only the design changes.

  A  single blocking key, exact-match comparators   the common build
  B  single blocking key, domain comparators        better scoring only
  C  multi-key blocking, domain comparators         this repo
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sameperson.datasets import DATASETS, counts, load_febrl   # noqa: E402
from sameperson.generate import build                          # noqa: E402
from sameperson.harm import (by_condition, label_pairs,        # noqa: E402
                             review_band, sweep,
                             threshold_for_harm_ratio)
from sameperson.score import blocking_report, score_all        # noqa: E402

BAND = (0.72, 0.88)
THRESHOLDS = [round(0.50 + 0.02 * i, 2) for i in range(26)]
ARMS = [
    ("A", "single", True,  "single key, exact-match comparators"),
    ("B", "single", False, "single key, domain comparators"),
    ("C", "multi",  False, "multi-key, domain comparators"),
]
RATIOS = (1, 10, 50, 100)


def run_arms(records):
    res = {}
    for name, mode, naive, label in ARMS:
        blk = blocking_report(records, mode)
        labelled = label_pairs(records, score_all(records, mode, naive))
        lost = blk["true_pairs_lost_to_blocking"]
        rows = sweep(labelled, THRESHOLDS, lost_to_blocking=lost)
        res[name] = {
            "label": label,
            "blocking": blk,
            "sweep": rows,
            "review_band": review_band(labelled, *BAND, lost_to_blocking=lost),
            "operating_points": {str(r): threshold_for_harm_ratio(rows, r)
                                 for r in RATIOS},
            "by_condition_at_0.80": by_condition(labelled, records, 0.80),
        }
    return res


def main() -> int:
    t0 = time.time()
    out = {"datasets": {}}

    sources = [(k, v[1], lambda k=k: load_febrl(k)) for k, v in DATASETS.items()]
    sources.append(("febrl3_no_id",
                    "same file, national identifier removed (the US case)",
                    lambda: load_febrl("febrl3", drop_identifier=True)))
    sources.append(("control", "generated here; must be matchable",
                    lambda: build(2000, 0.5)))

    for key, desc, loader in sources:
        try:
            records = loader()
        except FileNotFoundError as e:
            print(e, file=sys.stderr)
            return 1
        out["datasets"][key] = {
            "description": desc,
            "counts": counts(records),
            "arms": run_arms(records),
        }
        print(f"  {key} done")

    out["runtime_seconds"] = round(time.time() - t0, 1)
    os.makedirs("results", exist_ok=True)
    with open("results/results.json", "w") as f:
        json.dump(out, f, indent=2)

    print("\n" + "=" * 74)
    print("blocking recall - the ceiling that no threshold can raise")
    print("=" * 74)
    print(f"{'dataset':10s} {'records':>8s} {'true pairs':>11s} "
          f"{'single key':>11s} {'multi-key':>10s}   pairs lost to a single key")
    for key, d in out["datasets"].items():
        a = d["arms"]["A"]["blocking"]
        c = d["arms"]["C"]["blocking"]
        print(f"{key:10s} {d['counts']['records']:8d} "
              f"{a['true_pairs']:11d} {a['blocking_recall']:11.3f} "
              f"{c['blocking_recall']:10.3f}   "
              f"{a['true_pairs_lost_to_blocking']:5d} "
              f"({1 - a['blocking_recall']:.1%})")

    print("\n" + "=" * 74)
    print("errors at a stated harm ratio of 1 over-merge : 50 under-merges")
    print("=" * 74)
    print(f"{'dataset':10s} {'arm':>4s}   {'over-merge':>10s} {'under-merge':>12s}")
    for key, d in out["datasets"].items():
        for arm in ("A", "B", "C"):
            op = d["arms"][arm]["operating_points"]["50"]
            print(f"{key:10s} {arm:>4s}   {op['over_merge']:10d} "
                  f"{op['under_merge']:12d}")

    print("\n" + "=" * 74)
    print("febrl3 - what the threshold choice costs")
    print("=" * 74)
    f3 = out["datasets"]["febrl3"]["arms"]["C"]
    print(f"{'harm ratio':>12s} {'threshold':>10s} {'over-merge':>11s} "
          f"{'under-merge':>12s}")
    for r in RATIOS:
        op = f3["operating_points"][str(r)]
        note = "   <- what F1 assumes" if r == 1 else ""
        print(f"{'1:' + str(r):>12s} {op['threshold']:10.2f} "
              f"{op['over_merge']:11d} {op['under_merge']:12d}{note}")

    b = f3["review_band"]
    print(f"\nreview band {BAND[0]}-{BAND[1]}: {b['pairs_in_band']} pairs held "
          f"for a human ({b['true_pairs_in_band']} same person, "
          f"{b['false_pairs_in_band']} not)")

    print("\nfebrl3 miss rate at 0.80, by what actually differs in the record:")
    for cond, v in list(f3["by_condition_at_0.80"].items())[:10]:
        print(f"  {cond:22s} {v['miss_rate']:.3f}  "
              f"({v['missed']}/{v['true_pairs']})")

    print("\n" + "=" * 74)
    print("what the missing national identifier costs (febrl3, arm C)")
    print("=" * 74)
    with_id = out["datasets"]["febrl3"]["arms"]["C"]
    no_id = out["datasets"]["febrl3_no_id"]["arms"]["C"]
    print(f"{'':22s} {'blocking recall':>16s} {'over @1:1':>10s} "
          f"{'under @1:50':>12s}")
    for lbl, d in (("with identifier", with_id), ("without", no_id)):
        print(f"{lbl:22s} {d['blocking']['blocking_recall']:16.3f} "
              f"{d['operating_points']['1']['over_merge']:10d} "
              f"{d['operating_points']['50']['under_merge']:12d}")

    print(f"\nruntime {out['runtime_seconds']}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
