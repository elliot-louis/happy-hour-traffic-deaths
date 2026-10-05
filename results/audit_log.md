# Audit log

## data (1980s law file)

| Status | Check | Result |
|---|---|---|
| PASS | requested columns present; every jurisdiction covered; every row marked primary or secondary | 58 rows; 51 jurisdictions; missing columns none; source_type {'secondary': 36, 'primary': 22} |
| PASS | adoption years agree with the independent sources found earlier | MA: file 1984 vs Dec 1984 (Patch: Dec 10, 1984); KS: file 1985 vs 1985 (Kansas liquor-law timeline); IN: file 1985 vs 1985 (NWI Times); NC: file 1985-08-01 vs 1985; RI: file 1985 vs 1985 (Rhode Island Monthly); IL: file 1989 vs 1989 (26-year ban ended 2015); AK: file 1986 vs 1986 (Money: on the books since 1986); UT: file 'none found' before 1996, consistent with a 2011 ban |
| FLAG | strict/partial labels applied consistently | Indiana (time-of-day price cuts banned, all-day specials allowed) is labelled partial while North Carolina, under the same standard, is labelled strict; Kansas's 1985 law covered every on-premise licensee then existing (clubs and 3.2% beer bars). Recoded here: KS and IN as bans; RI ambiguous |
| FLAG | remaining gaps | no effective date: ['VT', 'NE']; year-only dates: ['MA', 'KS', 'IN', 'RI', 'IL', 'TX', 'AK', 'VA', 'GA']; secondary-only restriction rows: ['VT', 'NE', 'TX', 'PA', 'CT', 'CT', 'VA', 'GA'] |
| PASS | follow-up memo: Rhode Island description matches the 1985 court opinion | S & S Liquor Mart v. Pastore (Aug 26, 1985) quotes P.L. 1985 ch. 345: no multi-drink price inducements; no advertising of happy hours, open bars, two-for-one nights or free-drink specials. Partial restriction confirmed |
| PASS | follow-up memo: Maine's .08 BAC date agrees with Cohen-Einav's independent panel | memo: effective Aug 4, 1988; Cohen-Einav codes Maine .08 from 1988 |
| FLAG | follow-up memo: still unresolved | Vermont Regulation 49 adoption date; Rhode Island original chapter text; whether Ohio's 9/20/84 filing was substantive; Maine's 1984 suspension-law day |

## data

| Status | Check | Result |
|---|---|---|
| PASS | FARS years built | 1982-2024 (43 years) |
| PASS | non-state codes dropped from the panel | codes [] |
| PASS | all 51 jurisdictions present in every year | min 51, max 51 |
| PASS | no duplicate state-year-day-hour cells | 0 duplicates |
| PASS | 0 <= impaired (.08+) <= any alcohol (.01+) <= deaths, and SVN <= deaths | 0 violating cells |
| PASS | 1982 national totals vs NHTSA published | deaths 43,945 vs 43,945; impaired 21,166 vs 21,113 (+0.3%) |
| PASS | 1985 national totals vs NHTSA published | deaths 43,825 vs 43,825; impaired 18,174 vs 18,125 (+0.3%) |
| PASS | 2019 national totals vs NHTSA published | deaths 36,355 vs 36,355; impaired 10,212 vs 10,142 (+0.7%) |
| PASS | no jump in national impaired share where the raw-file source changes | 1994: 1.29, 2001: 0.24, 2004: 0.03, 2012: 0.21, 2013: 0.07, 2016: 0.27 pp (90th percentile of other years 1.95) |
| PASS | deaths with unknown crash hour | max 1.01% (2003), median 0.77% |
| PASS | share of deaths in the weekday 4-10 pm window is stable where sources change | range 20.8-23.8%; changes at seams {1994: 0.02, 2001: 0.14, 2004: 0.23, 2012: 0.08, 2013: 0.16, 2016: 0.05} |
| PASS | share of deaths in the 10 pm-6 am window is stable where sources change | range 28.5-38.6%; changes at seams {1994: 1.32, 2001: 0.12, 2004: 0.04, 2012: 0.05, 2013: 0.19, 2016: 0.99} |
| PASS | state-year panel is complete | 2193 rows = 51 x 43 |
| PASS | panel totals equal the microdata aggregates | max abs diff 1.8e-12 |
| PASS | rebuilding 1985 from raw files reproduces the stored aggregates | max abs diff 0.0e+00; cells matched 1877/1877; MI records per vehicle 1 after keeping one driver per vehicle (extra records dropped: 1); crashes without driver MI 0.13% |
| PASS | rebuilding 1999 from raw files reproduces the stored aggregates | max abs diff 0.0e+00; cells matched 1876/1876; MI records per vehicle 1 after keeping one driver per vehicle (extra records dropped: 0); crashes without driver MI 0.13% |
| PASS | rebuilding 2007 from raw files reproduces the stored aggregates | max abs diff 0.0e+00; cells matched 1854/1854; MI records per vehicle 1 after keeping one driver per vehicle (extra records dropped: 0); crashes without driver MI 0.08% |
| PASS | rebuilding 2014 from raw files reproduces the stored aggregates | max abs diff 0.0e+00; cells matched 1796/1796; MI records per vehicle 1 after keeping one driver per vehicle (extra records dropped: 0); crashes without driver MI 0.09% |
| PASS | rebuilding 2020 from raw files reproduces the stored aggregates | max abs diff 0.0e+00; cells matched 1817/1817; MI records per vehicle 1 after keeping one driver per vehicle (extra records dropped: 0); crashes without driver MI 0.13% |
| PASS | FHWA VM-2 complete and consistent with Cohen-Einav mileage | 51 jurisdictions x 45 years, 0 missing; ratio to Cohen-Einav median 1.000 (5th-95th pct 0.999-1.002) |

## estimators

| Status | Check | Result |
|---|---|---|
| PASS | modern coding: transition years dropped, first full treated years, treated cells | transition rows left []; first treated {'KS': 2013, 'IL': 2016, 'OK': 2019}; treated-post cells 27 |
| PASS | 1980s coding: first treated years, transition years dropped, excluded states absent | first treated {'MA': 1985, 'KS': 1986, 'IN': 1986, 'NC': 1986, 'VT': 1986, 'IL': 1990}; transition rows left []; excluded states present ['DE', 'UT'] |
| PASS | drinking-age covariate complete in the 1980s sample | 0 missing; Massachusetts {1983: 20.0, 1984: 20.0, 1985: 20.5, 1986: 21.0, 1987: 21.0} |
| PASS | modern_repeals ai_share: independent saturated-TWFE regression reproduces the estimate | max residual gap 2.1e-15; ATT -1.389 vs reported -1.389 |
| PASS | modern_repeals ddd_net: independent saturated-TWFE regression reproduces the estimate | max residual gap 7.8e-15; ATT 14.894 vs reported 14.894 |
| PASS | adoption_1980s ai_share: independent saturated-TWFE regression reproduces the estimate | max residual gap 2.6e-14; ATT 0.781 vs reported 0.781 |
| PASS | adoption_1980s svn_share: independent saturated-TWFE regression reproduces the estimate | max residual gap 1.2e-14; ATT -1.062 vs reported -1.062 |
| PASS | p-values agree with 95% intervals (both inverted from the same placebo distribution) | 0 of 72 rows disagree |
| PASS | placebo distributions centered near zero (|mean| < 0.5 SD) | 0 of 12 off-center |
| PASS | synthetic-control weights: nonnegative, sum to 1, match an exact optimizer (Illinois) | sum 1.000000, min 0.0e+00; pre-fit SSE 6.058e-04 vs exact 6.058e-04; post gap 2.784 vs 2.784 pp |
| PASS | synthetic DiD recovers a known effect on simulated data | true +2.00, estimated +2.00 (x100) |
| PASS | synthetic DiD: penalty-row NNLS solution matches an exact constrained optimizer | KS -1.106 vs -1.106; IL +0.554 vs +0.554; OK +0.140 vs +0.140 |
| PASS | modern ai_share without Utah in the comparison group | -1.30 (p = 0.74) vs main -1.39 (p = 0.69) |
| PASS | modern log_odds without Utah in the comparison group | -6.80 (p = 0.67) vs main -7.31 (p = 0.68) |

## inference

| Status | Check | Result |
|---|---|---|
| PASS | randomization test false-positive rate, modern design | 300 simulations (ai_share): rejected 7.0% at 5% (s.e. 1.5), 11.0% at 10% |
| PASS | randomization test power at the minimum detectable effect, modern design | 150 simulations (ai_share): rejected 81.3% at 5% (s.e. 3.2), 92.7% at 10% |
| FLAG | randomization test false-positive rate, modern design | 150 simulations (ddd_net): rejected 8.7% at 5% (s.e. 2.3), 14.0% at 10% |
| FLAG | randomization test false-positive rate, 1980s design | 300 simulations (ai_share): rejected 8.3% at 5% (s.e. 1.6), 12.3% at 10% |
| PASS | randomization test power at the minimum detectable effect, 1980s design | 150 simulations (ai_share): rejected 62.0% at 5% (s.e. 4.0), 77.3% at 10% |
| FLAG | randomization test false-positive rate, 1980s design | 150 simulations (svn_share): rejected 11.3% at 5% (s.e. 2.6), 18.0% at 10% |

## reproducibility

| Status | Check | Result |
|---|---|---|
| PASS | analysis.py re-runs cleanly | exit code 0 |
| PASS | followup.py re-runs cleanly | exit code 0 |
| PASS | vmt_extension.py re-runs cleanly | exit code 0 |
| PASS | every output table is identical after re-running all three scripts | 31 files compared; changed: none |

## data (FRED upload)

| Status | Check | Result |
|---|---|---|
| PASS | 51 jurisdictions x 1982-2024, no duplicates or gaps | 51 x 43 = 2193 rows; 0 duplicates; 0 missing |
| PASS | unemployment values are averages of twelve one-decimal monthly rates (FRED's annual-average signature) | 100.0% of values fit (random 3-decimal numbers would fit ~12% of the time) |
| PASS | unemployment agrees with Ruhm's independently compiled 1982-88 panel (48 states) | correlation 0.996; mean abs diff 0.18 pp; largest 0.93 pp (WV 1983) |
| PASS | population agrees with Ruhm's 1982-88 panel | median ratio 0.9955; range 0.971-1.020 |
| PASS | state populations sum to the published US totals | % deviation by year {1982: -0.02, 1990: -0.05, 2000: -0.01, 2010: 0.01, 2020: 0.02, 2024: -0.03} |
| PASS | population-weighted state unemployment tracks the published national rate | pp deviation by year {1982: 0.01, 1983: 0.06, 1990: 0.03, 2000: 0.01, 2009: -0.04, 2010: 0.04, 2019: -0.03, 2020: 0.03, 2023: 0.04, 2024: 0.02} |
| PASS | spot checks against well-known values | NV 2020 unemployment >= 12 (pandemic): ok; MI 2009 unemployment >= 12.5: ok; ND 2015 unemployment <= 3.5: ok; CA 2010 unemployment >= 11.5: ok; CA 2020 population 39.3-39.7M: ok; TX 2024 population 30.5-31.8M: ok; DC 2024 population 0.66-0.72M: ok; WY 2024 population 0.57-0.60M: ok |
| FLAG | no implausible jumps or repeated values | population growth range -6.0% to 11.6%; flagged [['AK', 1983, 8.63, 0.11], ['DC', 2000, 10.22, -0.88], ['NV', 2000, 11.58, 0.09]]; repeated population values 0; highest unemployment [['WV', 1983, 17.075], ['MI', 1982, 15.383], ['MI', 1983, 14.5]] |
| PASS | merged panel is complete and per-capita rates are plausible | 0 state-years missing; deaths per 100k 2.4-42.3; vehicle-miles per resident 4,517-19,143 |

## report

| Status | Check | Result |
|---|---|---|
| PASS | no formatting artifacts (NaN, undefined, null) in the report text | none |
| PASS | numbers fed to the report equal the current result tables | 9 tables compared; stale: none |
| PASS | TWFE replication in the report matches its table | coef 0.0113 (SE 0.0080) |
| PASS | spot-check of key numbers and facts in the report text | 13/13 found |
| PASS | all nine report figures exist | 12 figure files; missing none |

