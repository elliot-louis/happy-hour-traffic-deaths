#!/usr/bin/env python3
"""
build_fars.py -- state x year x day-of-week x hour-bin counts of traffic deaths and
alcohol-impaired-driving deaths from raw FARS microdata, 1982-2024.

Sources
  1982-2015  Raw FARS files from a GitHub mirror of NHTSA's FARS FTP archive
             (github.com/wgetsnaps/ftp.nhtsa.dot.gov--fars): accident file + multiple-imputation (MI)
             person file (DBF; fixed-width 'SEQL' MI files for 1982-1993).
  2016-2024  NHTSA national CSV files (accident.csv + miper.csv) saved in UPLOADS as
             accident_YYYY.csv and MIPER_YYYY.csv.

Alcohol measure (NHTSA's definition of an alcohol-impaired-driving fatality)
  The MI person file carries 10 imputed BACs for every driver and non-occupant. For each crash and
  imputation j, take the highest BAC among DRIVERS (MI records with VEH_NO > 0). The crash's deaths
  are alcohol-impaired in imputation j if that BAC is >= .08. Expected alcohol-impaired deaths =
  FATALS x (share of the 10 imputations at or above .08). 'ai01' repeats this at >= .01.

Other measures
  svn  deaths in single-vehicle crashes between 8:00 pm and 3:59 am (BAC-free proxy)
  dd   deaths in crashes with a police-reported drinking driver (DRUNK_DR > 0; absent from 2021+ files)

Output  fars_agg/fars_YYYY.csv: year, state (FIPS), dow (1=Sun..7=Sat, 9=unknown),
        hbin (00-05, 06-15, 16-18, 19-21, 22-23, unk), fat, ai08, ai01, svn, dd, crashes
Usage   python build_fars.py 1982 1983 ... [--force]
"""
from paths import RESULTS, FIGURES, INPUTS, JSON, RAW as RAW_DIR, AGG as AGG_DIR, TMP as TMP_DIR, CODE  # noqa: E402
import os, re, sys, zipfile, subprocess
import numpy as np
import pandas as pd

RAW = "https://raw.githubusercontent.com/wgetsnaps/ftp.nhtsa.dot.gov--fars/master/"
UPLOADS = str(RAW_DIR)
TMP = str(TMP_DIR / "fars_download")
OUT = str(AGG_DIR)
ACC_KEEP = {"STATE", "ST_CASE", "FATALS", "HOUR", "DAY_WEEK", "VE_FORMS", "DRUNK_DR"}
MI_KEEP = {"ST_CASE", "VEH_NO", "PER_NO"}
PCOLS = [f"P{k}" for k in range(1, 11)]


def mirror_paths(y):
    """(main DBF zip, separate MI zip or None) on the mirror for year y."""
    yy = f"{y % 100:02d}"
    if y <= 1993:
        return f"fars/{y}/DBF/FARS{y}.zip", f"fars/{y}/{'SEQL' if y == 1993 else 'Seql'}/MISEQL{yy}.zip"
    if y <= 2000:
        return f"fars/{y}/DBF/FARSDBF{yy}.zip", None
    if y <= 2003:
        return f"fars/{y}/DBF/FARS{y}.zip", None
    if y <= 2011:
        main = {2006: "FARS2006.ZIP", 2007: "FARS2007.ZIP"}.get(y, f"FARS{y}.zip")
        mi = {2004: "MI2004.zip", 2005: "MI2005.zip", 2006: "MI2006.ZIP"}.get(y, f"MI{y}DBF.zip")
        return f"fars/{y}/DBF/{main}", f"fars/{y}/DBF/{mi}"
    if y == 2012:
        return "fars/2012/National/DBF/FARS2012.zip", "fars/2012/National/DBF/MI2013DBF.zip"
    return f"fars/{y}/National/FARS{y}NationalDBF.zip", None


def fetch(path):
    local = os.path.join(TMP, os.path.basename(path))
    if not (os.path.exists(local) and os.path.getsize(local) > 1000):
        subprocess.run(["curl", "-s", "-L", "--retry", "3", "-o", local, RAW + path.replace(" ", "%20")],
                       check=True)
    return local


def dbf_from_zip(zpath, pattern, keep):
    from dbfread import DBF
    z = zipfile.ZipFile(zpath)
    hits = [n for n in z.namelist() if re.fullmatch(pattern, os.path.basename(n), re.I)]
    if not hits:
        return None
    local = os.path.join(TMP, "member.dbf")
    with open(local, "wb") as f:
        f.write(z.read(hits[0]))
    t = DBF(local, load=False, char_decode_errors="ignore")
    cols = [c for c in t.field_names if c.upper() in keep or re.fullmatch(r"P\d+", c.upper())]
    df = pd.DataFrame([{c: r[c] for c in cols} for r in t])
    df.columns = [c.upper() for c in df.columns]
    return df


def miseql_from_zip(zpath):
    """Fixed-width MI person file (1982-1993). Layout verified against the data: ST_CASE cols 6-11,
    VEH_NO 12-14, PER_NO 15-16, then ten contiguous 2-character BAC fields (hundredths) from col 19."""
    z = zipfile.ZipFile(zpath)
    name = [n for n in z.namelist() if re.search(r"miper", n, re.I)][0]
    rows = []
    for line in z.read(name).decode("latin1").splitlines():
        if len(line.strip()) < 20:
            continue
        step = 2 if len(line.rstrip()) <= 40 else 3
        vals = [line[18 + step * k: 20 + step * k] for k in range(10)]
        rows.append([int(line[5:11]), int(line[11:14]), int(line[14:16])] +
                    [int(v) if v.strip() else np.nan for v in vals])
    return pd.DataFrame(rows, columns=["ST_CASE", "VEH_NO", "PER_NO"] + PCOLS)


def upload(prefix, y):
    for f in os.listdir(UPLOADS):
        if re.fullmatch(fr"{prefix}_{y}\.csv", f, re.I):
            df = pd.read_csv(os.path.join(UPLOADS, f), encoding="latin1", low_memory=False)
            # strip a UTF-8 byte-order mark (read as latin1) from the first column name
            df.columns = [re.sub(r"^(\ufeff|ï»¿)", "", c).upper().strip() for c in df.columns]
            return df
    raise FileNotFoundError(f"{prefix}_{y}.csv not found in {UPLOADS}")


def aggregate(acc, mi, year):
    keep = ["ST_CASE", "VEH_NO"] + (["PER_NO"] if "PER_NO" in mi else []) + PCOLS
    mi = mi[keep].apply(pd.to_numeric, errors="coerce").dropna(subset=["ST_CASE"])
    pos = mi[PCOLS].values.ravel()
    pos = pos[(pos > 0) & ~np.isnan(pos)]
    scale = 1000.0 if np.percentile(pos, 90) > 60 else 100.0          # thousandths vs hundredths
    drivers = mi[mi.VEH_NO > 0]
    extra = int(drivers.duplicated(["ST_CASE", "VEH_NO"]).sum())       # NHTSA file quirk: >1 MI record in a vehicle
    if "PER_NO" in drivers:
        drivers = drivers.sort_values("PER_NO")
    drivers = drivers.drop_duplicates(["ST_CASE", "VEH_NO"])            # one driver per vehicle (lowest person number)
    max_rows_per_vehicle = int(drivers.groupby(["ST_CASE", "VEH_NO"]).size().max())
    hi = drivers.groupby("ST_CASE")[PCOLS].max() / scale              # highest driver BAC, each imputation
    hi.index = hi.index.astype("int64")
    acc = acc.copy()
    for c in ["STATE", "ST_CASE", "FATALS", "HOUR", "DAY_WEEK", "VE_FORMS"]:
        acc[c] = pd.to_numeric(acc[c], errors="coerce")
    acc = acc.dropna(subset=["ST_CASE"])
    acc["ST_CASE"] = acc["ST_CASE"].astype("int64")
    acc["p08"] = acc.ST_CASE.map((hi >= 0.08).mean(axis=1))
    acc["p01"] = acc.ST_CASE.map((hi >= 0.01).mean(axis=1))
    no_mi = acc.p08.isna().mean()
    acc[["p08", "p01"]] = acc[["p08", "p01"]].fillna(0.0)
    h = acc.HOUR.replace({24: 0})
    acc["hbin"] = np.select([h.between(0, 5), h.between(6, 15), h.between(16, 18), h.between(19, 21),
                             h.between(22, 23)], ["00-05", "06-15", "16-18", "19-21", "22-23"], "unk")
    acc["dow"] = acc.DAY_WEEK.where(acc.DAY_WEEK.between(1, 7), 9).fillna(9).astype(int)
    acc["fat"] = acc.FATALS
    acc["ai08"] = acc.fat * acc.p08
    acc["ai01"] = acc.fat * acc.p01
    acc["svn"] = acc.fat * ((acc.VE_FORMS == 1) & (h.between(20, 23) | h.between(0, 3)))
    acc["dd"] = (acc.fat * (pd.to_numeric(acc["DRUNK_DR"], errors="coerce") > 0)) if "DRUNK_DR" in acc else np.nan
    acc["crashes"] = 1
    g = (acc.groupby(["STATE", "dow", "hbin"])[["fat", "ai08", "ai01", "svn", "dd", "crashes"]]
            .sum(min_count=1).reset_index().rename(columns={"STATE": "state"}))
    g.insert(0, "year", year)
    info = dict(year=year, bac_scale=int(scale), crashes=len(acc), fatalities=int(acc.fat.sum()),
                ai08=int(round(acc.ai08.sum())), ai_share=round(acc.ai08.sum() / acc.fat.sum(), 3),
                crashes_without_driver_MI=round(no_mi, 4), max_MI_rows_per_vehicle=max_rows_per_vehicle,
                extra_MI_records_dropped=extra)
    return g, info


def process(year):
    if year >= 2016:
        acc, mi = upload("accident", year), upload("MIPER", year)
    else:
        main, mi_path = mirror_paths(year)
        z = fetch(main)
        acc = dbf_from_zip(z, r"(acc\d{2,4}|accident)\.dbf", ACC_KEEP)
        mi = dbf_from_zip(z, r"miper\d*\.dbf", MI_KEEP)
        if mi is None:
            zm = fetch(mi_path)
            mi = miseql_from_zip(zm) if "MISEQL" in mi_path.upper() else dbf_from_zip(zm, r"miper\d*\.dbf", MI_KEEP)
    g, info = aggregate(acc, mi, year)
    g.to_csv(os.path.join(OUT, f"fars_{year}.csv"), index=False)
    for f in os.listdir(TMP):
        os.remove(os.path.join(TMP, f))
    return info


if __name__ == "__main__":
    os.makedirs(TMP, exist_ok=True)
    os.makedirs(OUT, exist_ok=True)
    force = "--force" in sys.argv
    log = []
    for y in [int(a) for a in sys.argv[1:] if a.isdigit()]:
        if not force and os.path.exists(os.path.join(OUT, f"fars_{y}.csv")):
            print(y, "already built")
            continue
        try:
            info = process(y)
            log.append(info)
            print(info, flush=True)
        except Exception as e:
            print(y, "ERROR", repr(e), flush=True)
    if log:
        path = os.path.join(OUT, "build_log.csv")
        pd.DataFrame(log).to_csv(path, mode="a", header=not os.path.exists(path), index=False)
