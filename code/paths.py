"""Repository paths. Every script imports these so the project runs from any clone location."""
from pathlib import Path

CODE = Path(__file__).resolve().parent          # code/
ROOT = CODE.parent                              # repository root
INPUTS = ROOT / "data" / "inputs"               # law coding, AER panels, FRED, FHWA VM-2
AGG = ROOT / "data" / "fars_agg"                # FARS state-year-day-hour aggregates (built by build_fars.py)
RAW = ROOT / "data" / "raw"                     # raw NHTSA 2016-2024 CSVs (not tracked; see README)
TMP = ROOT / "data" / "tmp"                     # scratch space (not tracked)
RESULTS = ROOT / "results"                      # analysis panels and result tables
JSON = RESULTS / "json"                         # numbers passed to the report builder
FIGURES = ROOT / "figures"
PAPER = ROOT / "paper"

for _p in (TMP, RESULTS, JSON, FIGURES, PAPER):
    _p.mkdir(parents=True, exist_ok=True)
