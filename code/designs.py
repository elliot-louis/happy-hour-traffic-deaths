"""
designs.py -- the two natural experiments, defined once for every script.

Modern repeals: Kansas, Illinois and Oklahoma lifted or loosened their bans (2012, 2015, 2018). Each tuple is
(first full year under the new law, mid-year transition year that is dropped).

1980s adoptions (primary design): the six bans on time-limited drink discounts confirmed by the law-by-law check
(data/inputs/coding_1980s_verified.csv), compared with the states where that check found no statewide change in
1980-1995 and that appear in the drinking-age panel (data/inputs/fatalities.csv).

ORIGINAL_TREAT / ORIGINAL_EXCLUDED reproduce the earlier seven-state coding, kept for the robustness comparison.
"""
import pandas as pd
from paths import INPUTS

MOD_TREAT = {"KS": (2013, 2012), "IL": (2016, 2015), "OK": (2019, 2018)}

AD_TREAT = {"MA": (1985, None), "KS": (1986, 1985), "IN": (1986, 1985), "NC": (1986, 1985),
            "VT": (1986, 1985), "IL": (1990, 1989)}
_aer = set(pd.read_csv(INPUTS / "fatalities.csv").state.str.upper())
_law = pd.read_csv(INPUTS / "happy_hour_law_changes_1980_1995.csv")
AD_CONTROLS = sorted(s for s in _law[_law.change_type == "none found"].state.unique() if s in _aer)
AD_STATES = sorted(set(AD_TREAT) | set(AD_CONTROLS))

ORIGINAL_TREAT = dict(AD_TREAT, RI=(1986, 1985))
ORIGINAL_EXCLUDED = ["NE", "NJ", "MI", "OH", "TX", "DE", "ME", "WA", "OK", "UT"]

_cod = pd.read_csv(INPUTS / "coding_1980s_verified.csv")
AD_PARTIAL = sorted(s for s in _cod[_cod.used_as == "partial restriction"].state if s in _aer)
