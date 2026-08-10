"""Command line entry point."""
from __future__ import annotations

import argparse
import json
import sys

from .adapter import from_csv, from_fhir_bundle
from .generate import build
from .harm import (by_condition, label_pairs, review_band, sweep,
                   threshold_for_harm_ratio)
from .score import blocking_report, score_all

THRESHOLDS = [round(0.50 + 0.02 * i, 2) for i in range(26)]


def _load(args) -> list:
    if args.csv:
        return from_csv(args.csv)
    if args.fhir:
        return from_fhir_bundle(args.fhir)
    return build(args.people, args.dup_rate)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="sameperson",
        description="Patient matching that reports its two errors separately.")
    src = p.add_mutually_exclusive_group()
    src.add_argument("--csv", help="a CSV of records")
    src.add_argument("--fhir", help="a FHIR Bundle of Patient resources")
    p.add_argument("--people", type=int, default=4000,
                   help="synthetic population size when no input is given")
    p.add_argument("--dup-rate", type=float, default=0.35)
    p.add_argument("--blocking", choices=("single", "multi"), default="multi")
    p.add_argument("--naive", action="store_true",
                   help="exact-match comparators, no domain knowledge")
    p.add_argument("--harm-ratio", type=float, default=50.0,
                   help="under-merges you would accept to avoid one over-merge")
    p.add_argument("--band", nargs=2, type=float, default=(0.72, 0.88),
                   metavar=("LOW", "HIGH"),
                   help="score range routed to human review")
    p.add_argument("--json", action="store_true", help="emit JSON")
    args = p.parse_args(argv)

    records = _load(args)
    if len(records) < 2:
        print("need at least two records", file=sys.stderr)
        return 2

    blk = blocking_report(records, args.blocking)
    labelled = label_pairs(records, score_all(records, args.blocking,
                                              args.naive))
    lost = blk["true_pairs_lost_to_blocking"]
    rows = sweep(labelled, THRESHOLDS, lost_to_blocking=lost)
    op = threshold_for_harm_ratio(rows, args.harm_ratio)
    band = review_band(labelled, args.band[0], args.band[1],
                       lost_to_blocking=lost)
    cond = by_condition(labelled, records, op["threshold"])

    report = {"blocking": blk, "operating_point": op, "review_band": band,
              "by_condition": cond, "sweep": rows}
    if args.json:
        print(json.dumps(report, indent=2))
        return 0

    print(f"records {len(records)}   true pairs {blk['true_pairs']}   "
          f"candidate pairs {blk['candidate_pairs']}")
    print(f"blocking ({args.blocking}) recall {blk['blocking_recall']:.4f}  "
          f"- {lost} true pairs never compared")
    if blk["lost_by_condition"]:
        top = list(blk["lost_by_condition"].items())[:3]
        print("  lost mostly to: "
              + ", ".join(f"{k} ({v})" for k, v in top))
    print()
    print(f"at a stated harm ratio of 1 over-merge : "
          f"{args.harm_ratio:g} under-merges")
    print(f"  threshold      {op['threshold']:.2f}")
    print(f"  over-merges    {op['over_merge']}   "
          f"(people who could be handed another person's record)")
    print(f"  under-merges   {op['under_merge']}   "
          f"(people whose history stays split)")
    print()
    print(f"review band {args.band[0]}-{args.band[1]}: "
          f"{band['pairs_in_band']} pairs held for a human")
    print(f"  auto over-merge {band['auto_over_merge']}   "
          f"auto under-merge {band['auto_under_merge']}")
    if cond:
        print("\nmiss rate by condition:")
        for k, v in list(cond.items())[:6]:
            print(f"  {k:18s} {v['miss_rate']:.3f}  "
                  f"({v['missed']}/{v['true_pairs']})")
    print("\nNo single accuracy figure is reported. The two errors are not "
          "the same error,\nand collapsing them chooses who gets harmed "
          "without saying so.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
