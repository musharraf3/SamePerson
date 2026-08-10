# SamePerson

**A patient matcher makes two different mistakes. Reporting one number hides which one you chose.**

Weekend Builds in Healthcare AI · #9

---

## The two mistakes

Every master patient index decides, thousands of times a day, whether two
records are the same person. It gets this wrong in two directions, and they are
not the same kind of wrong.

**Over-merge.** Two people become one chart. Someone can be handed another
person's allergy list, medication history, or diagnosis. Active harm, and hard
to unpick once downstream systems have copied the merged record.

**Under-merge.** One person stays two charts. Fragmented history, repeated
imaging, an interaction nobody sees because half the record is elsewhere.
Passive harm, far more common, and largely invisible, because nothing on screen
looks wrong.

The standard way to pick a matching threshold is to maximise F1 or accuracy.
Both treat one over-merge as exactly equal to one under-merge. Nobody working in
patient safety believes that, and the symmetric number is still the one that
gets published.

So this repo never prints a single accuracy figure. It prints both error counts,
in people, at every threshold, plus the band where the system should not be
deciding alone.

## The data is not mine

Everything below runs on **FEBRL**, the Freely Extensible Biomedical Record
Linkage benchmark — the standard public test set for record linkage. The records
are built from real name, surname and address frequency tables. The duplicates
are corrupted using an error model derived from published studies of real data
entry mistakes. Ground truth is carried in the record id, so every pair is
already adjudicated.

None of that was decided by me, which is the point. You can make your own test
data agree with you.

| dataset | records | people | true pairs |
|---|---:|---:|---:|
| febrl1 | 1,000 | 500 | 500 |
| febrl2 | 5,000 | 4,000 | 1,934 |
| febrl3 | 5,000 | 2,000 | 6,538 |

A generated population also runs, as a **control** rather than as evidence: it
exists so a matcher that failed everything would be visibly different from one
that discriminates.

```bash
python scripts/fetch_data.py     # ~2 MB from PyPI, no account, no DUA
```

## The result I did not expect

Three designs over the same files. Only the design changes.

| arm | design |
|---|---|
| **A** | single blocking key, exact-match comparators |
| **B** | single blocking key, domain comparators |
| **C** | multi-key blocking, domain comparators |

Under-merges at a stated harm ratio of 1 over-merge to 50 under-merges:

| dataset | A | B | C |
|---|---:|---:|---:|
| febrl1 | 173 | 165 | **3** |
| febrl2 | 771 | 705 | **115** |
| febrl3 | 2,753 | 2,537 | **265** |
| control | 232 | 217 | **97** |

I built the comparators first, because that is the interesting part: nicknames,
compound surnames, transposed birth dates, a national identifier weighted
asymmetrically. Then I measured what they were worth.

**A to B is all of that comparator work. On febrl3 it moved under-merges by 7.8%.**

**B to C changed only which pairs are compared at all. It moved them by 89.6%.**

The reason is the ceiling:

| dataset | blocking recall, single key | multi-key | true pairs never scored |
|---|---:|---:|---:|
| febrl1 | 0.670 | 0.998 | 165 (**33.0%**) |
| febrl2 | 0.636 | 0.992 | 704 (**36.4%**) |
| febrl3 | 0.614 | 0.993 | 2,526 (**38.6%**) |

Under a single blocking key — surname prefix plus birth year, the common design
— **a third of genuinely-same-person pairs are never scored at all.** No
threshold recovers them. No comparator improvement touches them. They were
discarded before the matcher ran.

Most published match rates are quoted after candidate generation without saying
so. This repo measures that first, and adds the losses to the under-merge count,
because a pair you never compared is still a pair you got wrong.

## The threshold is a harm allocation

Same matcher, same file, febrl3 arm C. Only the declared trade-off changes.

| harm ratio | threshold | over-merge | under-merge |
|---|---:|---:|---:|
| 1 : 1 *(what F1 assumes)* | 0.62 | **10** | 143 |
| 1 : 10 | 0.64 | 2 | 221 |
| 1 : 50 | 0.66 | 0 | 265 |
| 1 : 100 | 0.66 | 0 | 265 |

Optimising symmetrically puts 10 people in a position to receive someone else's
record, to save 122 people a split history. That may well be the right call. It
is not a call an F1 score should be making silently.

`--harm-ratio` makes it an argument. Whatever you set it to, it is written down,
versioned, and arguable by someone who does not write code.

## The same file, read as two countries

FEBRL carries a national identifier, because the country it was built in has one.
The United States does not. Since the FY1999 Labor–HHS appropriations act,
Congress has renewed a rider — Section 510 — barring HHS from spending any funds
to adopt a unique patient identifier. Provider and informatics groups were still
petitioning for its repeal in 2025.

`load_febrl("febrl3", drop_identifier=True)` blanks the field and changes nothing
else. Arm C, both runs:

| | blocking recall | over-merge at 1:1 | under-merge at 1:50 |
|---|---:|---:|---:|
| with identifier | 0.993 | 10 | 265 |
| **without** | 0.939 | **32** | **824** |

Removing one column triples the under-merges and triples the over-merges.

**This repo takes no position on whether the United States should have a national
patient identifier.** There are serious privacy arguments against one, and they
are not mine to adjudicate. What is measurable is the cost of not having one, and
that number belongs in the argument rather than outside it.

## Who the failures land on

Miss rate at 0.80, febrl3 arm C, grouped by what actually differs between the
duplicate and its original. These labels are derived by diffing the records, not
declared by me:

| what differs | miss rate | |
|---|---:|---|
| date of birth changed | **0.789** | 445 / 564 |
| postcode changed | 0.271 | 421 / 1,551 |
| given name changed | 0.257 | 664 / 2,588 |
| identifier changed | 0.249 | 223 / 894 |
| surname changed | 0.241 | 671 / 2,784 |
| address changed | 0.154 | 614 / 3,977 |

Matching does not fail at random. It fails on records that changed, and records
change most for people who move, marry, or are registered by someone who spelled
it differently. Under a single blocking key those same surname changes are not
merely hard, they are unreachable.

## The band where it should not decide

Scores between 0.72 and 0.88 hold 1,438 pairs on febrl3.

**All 1,438 are genuinely the same person. None are false pairs.** On this
dataset the band is not capturing ambiguity, it is capturing recall the
threshold would otherwise throw away — so routing it to a human is real work
recovered, but the band is not doing the job I designed it for. That is a
finding against my own design and it stays in.

## Use it on your own data

```bash
pip install sameperson

sameperson --csv records.csv --harm-ratio 50 --band 0.72 0.88
sameperson --fhir bundle.json --blocking multi
```

CSV columns are auto-detected, including Synthea's `patients.csv` spellings.

The FHIR reader does one thing worth knowing about: `Patient.name` is a list, and
a previous name is often still present with `use="old"`. That is precisely what a
matcher needs when a surname has changed, and precisely what a flattened CSV
export of the same bundle drops. `from_fhir_bundle` emits one record per name
variant under the same person id, so someone who married stays reachable under
both.

## Run the study

```bash
git clone https://github.com/musharraf3/SamePerson && cd SamePerson
python scripts/fetch_data.py     # once
python evals/run.py              # ~3s
python -m pytest tests/ -q       # 28 tests
```

`results/results.json` holds every number above.

## Limits

**FEBRL is Australian.** Name and address frequency tables, postcode structure
and the presence of a national identifier all reflect that. The failure *modes*
transfer; the exact rates should not be read as US rates.

**FEBRL corruption is heavier than a real MPI's.** febrl3 gives up to six
duplicates per person with several corrupted fields each. That is a stress test,
not a population estimate.

**Pairs are not clustered.** Decisions are reported per pair, so a person with
three records counts as three pairs. Clustering is where transitivity bugs live
and it is not implemented here.

**The field weights are mine.** Arrived at by judgement, not trained on labelled
pairs. HL7's Identity Matching IG supplies the field set and the idea of graded
confidence, not these numbers. Blocks larger than 200 records are dropped, and
that cost is counted in the blocking report rather than hidden.

**Four things I got wrong, all in the history.** I built the comparators before
measuring blocking, which is how a 38% loss surprised me at all — the expensive
work was downstream of the cheap one. I first counted blocking losses separately
from under-merges, which flattered every arm. I originally treated a missing
field as disagreement, which penalised exactly the records with the least data. And
I built the whole thing on a population I generated myself before running it on a
benchmark somebody else built; the single-key loss came out at 21% on my data and
33–39% on theirs, which is the difference between a demonstration and a result.

## Data and sources

- **FEBRL** benchmark datasets (Australian National University), redistributed in
  the [`recordlinkage`](https://pypi.org/project/recordlinkage/) package under
  its BSD licence · [Febrl project](https://sourceforge.net/projects/febrl/)
- HL7 **Interoperable Digital Identity and Patient Matching** IG (FAST) v2.0.0 ·
  [build.fhir.org](https://build.fhir.org/ig/HL7/fhir-identity-matching-ig/patient-matching.html)
- FHIR R4 **Patient** resource and the `$match` operation ·
  [hl7.org](https://www.hl7.org/fhir/patient-operation-match.html)
- **Patient Identification SAFER Guide**, updated 2024; Weatherford & Adelman,
  *JAMIA Open*, 6 January 2026 — recommends organisational monitoring of
  identification errors and specifies no thresholds, which is the gap this repo
  points at ·
  [academic.oup.com](https://academic.oup.com/jamiaopen/article/9/1/ooaf160/8415654)
- **Section 510**, Labor–HHS appropriations rider, in force since FY1999 ·
  background from [AHIMA](https://www.ahima.org/advocacy/take-action/take-action-forms/take-action-repeal-section-510-labor-hhs-appropriations-bill-and-support-patient-identification/)
  and [Patient ID Now](https://www.healthcareitnews.com/news/patient-id-now-frustrated-section-510-remaining-labor-hhs-appropriations)

All data is synthetic. No patient information of any kind is in this repository,
and none was used.

## License

MIT. Personal project — not affiliated with, endorsed by, or representing any
employer.
