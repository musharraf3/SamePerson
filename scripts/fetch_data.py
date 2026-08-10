"""Fetch the public datasets. Stdlib only, no account, no data use agreement.

FEBRL — the Freely Extensible Biomedical Record Linkage project's benchmark
datasets. These are the standard public test sets for record linkage: the
records are generated from real name, surname and address frequency tables,
and the duplicates are corrupted using an error model built from published
studies of real data entry mistakes rather than from anyone's imagination.
Ground truth is carried in the record id, so every pair is adjudicated.

They are distributed inside the `recordlinkage` package on PyPI, which is
the most stable public location for them. This script downloads that wheel
and extracts the five CSVs. It does not install the package, and nothing in
this repository imports it.

Optional: Synthea. MITRE's synthetic patient generator produces FHIR
Bundles with a `maiden` name on married patients, which is a real name
change rather than a simulated one. It is not fetched here because it needs
github.com; run scripts/fetch_synthea.sh if you want it.
"""

from __future__ import annotations

import io
import json
import os
import sys
import urllib.request
import zipfile

PYPI = "https://pypi.org/pypi/recordlinkage/json"
WANT = ("dataset1.csv", "dataset2.csv", "dataset3.csv",
        "dataset4a.csv", "dataset4b.csv")
DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "data", "febrl")


def main() -> int:
    os.makedirs(DATA, exist_ok=True)
    if all(os.path.exists(os.path.join(DATA, w)) for w in WANT):
        print(f"already present in {DATA}")
        return 0

    print("locating recordlinkage on PyPI ...")
    with urllib.request.urlopen(PYPI, timeout=60) as r:
        meta = json.load(r)
    url = None
    for f in meta["urls"]:
        if f["filename"].endswith(".whl"):
            url = f["url"]
            break
    if url is None:
        print("no wheel found on PyPI", file=sys.stderr)
        return 1

    print(f"downloading {url.rsplit('/', 1)[-1]} ...")
    with urllib.request.urlopen(url, timeout=120) as r:
        blob = r.read()

    n = 0
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        for name in z.namelist():
            base = os.path.basename(name)
            if base in WANT and "febrl" in name:
                with open(os.path.join(DATA, base), "wb") as fh:
                    fh.write(z.read(name))
                n += 1
                print(f"  {base}")
    if n != len(WANT):
        print(f"expected {len(WANT)} files, wrote {n}", file=sys.stderr)
        return 1
    print(f"\n{n} files in {DATA}")
    print("source: Febrl (Australian National University), redistributed in "
          "the recordlinkage package under its BSD licence.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
