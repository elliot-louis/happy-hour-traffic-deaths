const fs = require("fs");
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, Table, TableRow, TableCell, WidthType,
  AlignmentType, ImageRun, ShadingType, LevelFormat, Footer, PageNumber,
} = require("docx");

const path = require("path");
const ROOT = path.resolve(__dirname, "..", "..");
const RES = path.join(ROOT, "results"), JS = path.join(RES, "json");
const rj = (f) => JSON.parse(fs.readFileSync(f, "utf8"));
const D = rj(path.join(JS, "report_data.json"));
const FIG = path.join(ROOT, "figures") + path.sep;
const OUTFILE = path.join(ROOT, "paper", "happy_hour_report.docx");
const W = 9360;

// ---------------------------------------------------------------- helpers
const MINUS = "\u2212";
const num = (x, d = 1) => (x < 0 ? MINUS : "") + Math.abs(x).toFixed(d);
const sgn = (x, d = 1) => (x > 0 ? "+" : x < 0 ? MINUS : "") + Math.abs(x).toFixed(d);
const pv = (p) => (p < 0.001 ? "<0.001" : p < 0.0095 ? p.toFixed(3) : p.toFixed(2));
const peq = (p) => (p < 0.001 ? "p < 0.001" : "p = " + (p < 0.0095 ? p.toFixed(3) : p.toFixed(2)));
const ci = (r, d = 1) => `[${num(r.ci_lo, d)}, ${num(r.ci_hi, d)}]`;
const M = (g, o) => D.main.find((r) => r.design === g && r.outcome === o);
const S = (s, o) => D.sc.find((r) => r.state === s && r.outcome === o);
const RB = (g, spec, o) => D.rob.find((r) => r.design === g && r.spec === spec && r.outcome === o);
const BS = (g, o, s) => D.bystate.find((r) => r.design === g && r.outcome === o && r.state === s);
const pct = (x, base) => ((100 * x) / base).toFixed(0);
const oddsPct = (x) => Math.abs(100 * (Math.exp(x / 100) - 1)).toFixed(0);

const run = (pt) => (typeof pt === "string" ? new TextRun(pt) : new TextRun(pt));
const P = (parts) =>
  new Paragraph({ spacing: { after: 140, line: 276 }, children: (typeof parts === "string" ? [parts] : parts).map(run) });
const H1 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun(t)] });
const H2 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun(t)] });
const BUL = (parts) =>
  new Paragraph({ numbering: { reference: "bullets", level: 0 }, spacing: { after: 90, line: 264 },
    children: (typeof parts === "string" ? [parts] : parts).map(run) });

function cell(text, w, head, center) {
  const o = {
    width: { size: w, type: WidthType.DXA },
    margins: { top: 50, bottom: 50, left: 90, right: 90 },
    children: [new Paragraph({ alignment: center ? AlignmentType.CENTER : AlignmentType.LEFT,
      children: [new TextRun({ text: String(text), bold: head, size: 18 })] })],
  };
  if (head) o.shading = { fill: "DCE6F1", type: ShadingType.CLEAR, color: "auto" };
  return new TableCell(o);
}
function table(headers, rows, widths, centerCols = []) {
  const hdr = new TableRow({ tableHeader: true, children: headers.map((h, i) => cell(h, widths[i], true, i > 0)) });
  const body = rows.map((r) => new TableRow({ children: r.map((c, i) => cell(c, widths[i], false, centerCols.includes(i))) }));
  return new Table({ width: { size: W, type: WidthType.DXA }, columnWidths: widths, rows: [hdr, ...body] });
}
const note = (t) => new Paragraph({ spacing: { before: 60, after: 220 }, children: [new TextRun({ text: t, italics: true, size: 17, color: "444444" })] });
const ttl = (t) => new Paragraph({ spacing: { before: 200, after: 80 }, keepNext: true, children: [new TextRun({ text: t, bold: true, size: 20 })] });
function figure(file, cap) {
  const buf = fs.readFileSync(FIG + file);
  const w = buf.readUInt32BE(16), h = buf.readUInt32BE(20);
  return [
    new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 120 }, keepNext: true,
      children: [new ImageRun({ type: "png", data: buf, transformation: { width: 624, height: Math.round((624 * h) / w) } })] }),
    note(cap),
  ];
}

// ---------------------------------------------------------------- numbers
const g1 = "modern_repeals", g2 = "adoption_1980s";
const mA = M(g1, "ai_share"), mL = M(g1, "log_odds"), mS = M(g1, "svn_share"), mN = M(g1, "ddd_net");
const aA = M(g2, "ai_share"), aL = M(g2, "log_odds"), aS = M(g2, "svn_share"), aI = M(g2, "ddd_ai"), aP = M(g2, "ddd_sober"), aN = M(g2, "ddd_net");
const il = S("IL", "ai_share"), ks = S("KS", "ai_share"), ok = S("OK", "ai_share");
const bKS = BS(g1, "ai_share", "KS"), bIL = BS(g1, "ai_share", "IL"), bOK = BS(g1, "ai_share", "OK");
const tp = RB(g1, "timing placebo (5 yrs early)", "ai_share");
const natY = (y) => D.nat.find((r) => r.year === y);
const F = rj(path.join(JS, "followup_data.json"));
const FA = (spec, o) => F.A.find((r) => r.spec === spec && r.outcome === o);
const FB = (prefix) => F.B.find((r) => r.test.startsWith(prefix));
const FC = (unit, o) => F.C.find((r) => r.unit === unit && r.outcome === o);
const VD = rj(path.join(JS, "vmt_data.json"));
const TN = rj(path.join(RES, "tests_now_results.json"));
const INm = TN.monthly.rows[0], OKm = TN.monthly.rows[2], ITP = TN.monthly.indiana_in_time_placebos_pp;
const MT = rj(path.join(RES, "more_tests_results.json"));
const MR = (sec, g, y, spec) => MT.rows.find((r) => r.section === sec && r.design === g && r.outcome === y && (!spec || r.spec.startsWith(spec)));
const PL = MT.pooled.find((r) => r.outcome === "log_odds" && r.weighting.startsWith("equal")), PS = MT.pooled.find((r) => r.outcome === "ai_share" && r.weighting.startsWith("equal"));
const WK = MT.weekend_checks;
const FD = rj(path.join(JS, "fred_data.json"));
const FR = (g, spec, o) => FD.rows.find((r) => r.design === g && r.spec === spec && r.outcome === o);
const fM = FR("modern_repeals", "per capita", "ai_per_cap"), fA = FR("adoption_1980s", "per capita", "ai_per_cap");
const RC = rj(path.join(JS, "recode_data.json"));
const RR = (d, o) => RC.rows.find((r) => r.design.startsWith(d) && r.outcome === o);
const b6 = (o) => RR("Six bans (MA", o), b4 = (o) => RR("Four strict", o), pt = (o) => RR("Nine partial", o);
const PQ6 = RC.pooled.find((r) => r.outcome === "log_odds" && r.changes === "3 repeals + 6 bans");
const PCk = RC.partial_checks.ai_share;
const FU = RC.followup.ai_share;
const SA1 = "+ seat belt, 65 mph, .08 BAC, income";
const VR = (g, spec, o) => VD.rows.find((r) => r.design === g && r.spec === spec && r.outcome === o);
const VS = (unit, o) => VD.sdid.find((r) => r.unit === unit && r.outcome === o);
const pc = (x, d = 1) => sgn(100 * (Math.exp(x / 100) - 1), d);
const vM = VR("modern_repeals", "main", "ai_per_vmt"), vMs = VR("modern_repeals", "main", "sober_per_vmt"), vMx = VR("modern_repeals", "excl. 2020-21", "sober_per_vmt");
const vA = VR("adoption_1980s", "1982-95, drinking age", "ai_per_vmt"), vA2 = VR("adoption_1980s", "1983-95, traffic-safety controls", "ai_per_vmt");
const vC1 = VR("modern_repeals", "+ log VMT, rural share", "ai_share"), sdV = VS("Pooled (mean of 3)", "ai_per_vmt");

// ---------------------------------------------------------------- content
const kids = [];
const SN = { MA: "Massachusetts", KS: "Kansas", IN: "Indiana", NC: "North Carolina", VT: "Vermont", IL: "Illinois" };
const sens = (s) => `${SN[s.split(" ")[0]]}’s date`;
const PM = TN.power.modern_repeals, PA = TN.power.adoption_1980s;
const f0 = (x) => (100 * x).toFixed(0);
const bs80 = D.bystate.filter((r) => r.design === g2 && r.outcome === "ai_share");
const nClean = RC.n_clean_aer;

kids.push(new Paragraph({ alignment: AlignmentType.LEFT, spacing: { after: 60 },
  children: [new TextRun({ text: "Happy Hour Laws and Alcohol-Impaired Traffic Deaths", bold: true, size: 36, color: "1F3864" })] }));
kids.push(new Paragraph({ spacing: { after: 280 }, children: [new TextRun({ text: "Elliot Louis  |  Trinity College  |  October 2026", size: 20, color: "555555" })] }));

kids.push(H1("Abstract"));
kids.push(P(`Do bans on happy hour drink discounts reduce drunk-driving deaths? This paper uses crash-level FARS data for 1982–2024 to study two natural experiments: three states that lifted bans between 2012 and 2018, and six states that banned time-limited drink discounts between 1984 and 1989. Imputation difference-in-differences estimates, with randomization inference designed for a handful of treated states, find no detectable effect in either direction. The 1980s bans did not lower the share of traffic deaths involving an impaired driver by more than about ${num(-aA.ci_lo)} percentage points (${pct(-aA.ci_lo, aA.baseline)}% of baseline), and the repeals did not raise it by more than about ${num(mA.ci_hi)} points. The null holds under synthetic control, synthetic difference-in-differences, alternative codings of the 1980s laws, and controls for driving exposure, other traffic-safety laws and economic conditions.`));

kids.push(H1("Summary"));
kids.push(P(`This paper uses raw, crash-level FARS data for 1982–2024 to ask the question twice: once with the three modern repeals (Kansas 2012, Illinois 2015, Oklahoma 2018) and once with the six states that banned time-limited drink discounts in 1984–1989 (Massachusetts, Kansas, Indiana, North Carolina, Vermont and Illinois), compared with the ${nClean} states where a law-by-law check found no statewide change. Estimates come from an imputation difference-in-differences estimator that is robust to staggered timing, and inference comes from size-matched randomization tests built for designs with only a handful of treated states.`));
kids.push(P(`Neither experiment shows a detectable effect on alcohol-impaired traffic deaths. Lifting a ban changed the alcohol-impaired share of deaths by ${sgn(mA.att)} percentage points (95% randomization interval ${ci(mA)}, ${peq(mA.p)}); imposing one changed it by ${sgn(aA.att)} points (${ci(aA)}, ${peq(aA.p)}). The 1980s bans did not lower the impaired share by more than about ${num(-aA.ci_lo)} points, roughly ${pct(-aA.ci_lo, aA.baseline)}% of its ${aA.baseline.toFixed(0)}% baseline, and the repeals rule out increases larger than about ${num(mA.ci_hi)} points (${pct(mA.ci_hi, mA.baseline)}% of a ${mA.baseline.toFixed(0)}% baseline). Measured per vehicle-mile with FHWA data, impaired deaths moved ${pc(vM.att)}% after repeals (${pc(vM.ci_lo)}% to ${pc(vM.ci_hi)}%) and ${pc(vA.att)}% after bans (${pc(vA.ci_lo)}% to ${pc(vA.ci_hi)}%). Pooling all nine law changes, having a ban changes the odds that a traffic death involved an impaired driver by ${pc(PL.att, 0)}% (95% interval ${pc(PL.ci_lo, 0)}% to ${pc(PL.ci_hi, 0)}%). Adding unemployment and population data from FRED changes nothing: per 100,000 residents, impaired deaths moved ${pc(fM.att)}% after repeals (${pc(fM.ci_lo)}% to ${pc(fM.ci_hi)}%) and ${pc(fA.att)}% after bans (${pc(fA.ci_lo)}% to ${pc(fA.ci_hi)}%).`));
kids.push(P(`A sharper test looks where happy hours actually operate. Comparing the odds that a death involved an impaired driver in weekday 4–10 p.m. crashes with 10 p.m.–6 a.m. crashes, within the same state and year, the estimates point the way the happy-hour mechanism predicts in both experiments (up ${num(mN.att, 0)} log points after repeals, down ${num(-aN.att, 0)} after bans), but neither is statistically significant (${peq(mN.p)} and ${peq(aN.p)}). In the 1980s the net figure comes from sober crashes: sober deaths shifted from nighttime toward weekday evenings (${sgn(aP.att)} log points, ${peq(aP.p)}) while impaired deaths did not (${sgn(aI.att)}, ${peq(aI.p)}), a pattern a happy hour law cannot produce. Seat-belt, speed-limit, BAC-law and income controls leave the sober shift in place (Section 7.3). A further test comparing weekday with weekend evenings finds that repeals raised alcohol involvement on weekday evenings (nominal p = ${pv(WK.main.p)}, about ${pv(WK.size.share_p_at_or_below_actual)} once the test is calibrated by simulation) and the 1980s bans moved it the other way, which is at most suggestive of timing displacement (Section 7.7).`));
kids.push(P(`Illinois was the one state a method singled out: its synthetic control implied a ${num(il.mean_post_gap_x100)}-point rise after 2015 (placebo rank p = ${pv(il.placebo_rank_p)}). Follow-up tests show this is an artifact of the comparison states (Section 7.1). Dropping Mississippi alone cuts the gap to ${num(FB("Leave out MS").post)} points, excluding Southern donors erases it, the same test flags Illinois at a fake 2008 date, and synthetic difference-in-differences puts Illinois at ${sgn(FC("IL", "ai_share").tau)} points (p = ${pv(FC("IL", "ai_share").p)}).`));
kids.push(P(`Indiana’s July 2024 change cannot be evaluated properly until 2025 data arrive, but an early look at the six months of 2024 after it took effect finds a change of ${sgn(INm.att_pp)} points in the impaired share (95% interval ${num(INm.ci_lo_pp)} to ${sgn(INm.ci_hi_pp)}), far too imprecise to mean anything yet (Section 7.6).`));
kids.push(P(`The 1980s coding rests on a law-by-law check of every state’s history (Section 7.9). It found that several states once treated as comparisons had restricted drink specials themselves and that Rhode Island’s law was a partial restriction, so both are left out of the main design. Counting Rhode Island as a ban, or keeping only the four strictest bans, leaves the impaired-share result unchanged. The check also turned up one surprise, a significant drop in the impaired share after the weaker partial restrictions (${sgn(pt("ai_share").att)} points, ${peq(pt("ai_share").p)}); it disappears without Maine and Ohio, both of which changed other drunk-driving laws in the same years.`));

kids.push(H1("1. Data and measures"));
kids.push(P("Crash files and imputed-BAC files come from a GitHub mirror of NHTSA’s FARS archive (github.com/wgetsnaps/ftp.nhtsa.dot.gov--fars) for 1982–2015 and from NHTSA’s national CSV releases for 2016–2024. NHTSA’s multiple-imputation file gives ten imputed blood-alcohol values for every driver. A crash’s deaths count as alcohol-impaired in a given imputation if the highest driver BAC is at least 0.08 g/dL; expected impaired deaths are the crash’s deaths times the share of the ten imputations that meet the threshold. This reproduces NHTSA’s definition of an alcohol-impaired-driving fatality."));
kids.push(P(`National totals match NHTSA’s published figures closely: ${natY(1982).ai08.toLocaleString("en-US", { maximumFractionDigits: 0 })} impaired deaths in 1982 against NHTSA’s 21,113; ${natY(1985).ai08.toLocaleString("en-US", { maximumFractionDigits: 0 })} in 1985 against 18,125; and ${natY(2019).ai08.toLocaleString("en-US", { maximumFractionDigits: 0 })} in 2019 against 10,142, with total deaths matching exactly. As a further check, a conventional two-way fixed-effects (TWFE) specification gives a ban coefficient of ${D.twfe.coef.toFixed(4)} (SE ${D.twfe.se.toFixed(4)}) on these data, close to the 0.0155 (SE 0.0120) it gives on NHTSA’s published state-level BAC tables for 1994–2024. The two data sources agree, so differences between that specification and the estimates below come from design rather than data.`));
kids.push(P("The state-year outcomes are:"));
kids.push(BUL([{ text: "Impaired share: ", bold: true }, "impaired deaths divided by all deaths."]));
kids.push(BUL([{ text: "Log odds: ", bold: true }, "log of impaired deaths over sober deaths. Sober deaths in the same state and year absorb exposure (miles driven, population, weather, road design), so no outside controls are needed."]));
kids.push(BUL([{ text: "Single-vehicle-night share: ", bold: true }, "deaths in single-vehicle crashes between 8 p.m. and 4 a.m. divided by all deaths, a standard proxy that uses no BAC data."]));
kids.push(BUL([{ text: "Evening-versus-night contrast: ", bold: true }, "log of impaired deaths on weekdays 4–10 p.m. over impaired deaths 10 p.m.–6 a.m., plus the same ratio for sober deaths as a placebo."]));
kids.push(BUL([{ text: "Net evening test: ", bold: true }, "the impaired ratio minus the sober ratio, i.e. the log odds ratio of alcohol involvement in weekday-evening versus nighttime crashes. Anything that shifts all crashes between evening and night cancels out."]));

kids.push(H1("2. Designs and methods"));
kids.push(ttl("Table 1. Treatment coding"));
kids.push(table(["State", "Change", "Effective", "First full year", "Notes"], [
  ["KS", "Ban lifted", "7/1/2012", "2013", "Broad liquor bill (Sub. for HB 2689) that also allowed retailer tastings and microdistillery licenses"],
  ["IL", "Ban → restricted", "7/15/2015", "2016", "APIS codes Illinois as restricted, not repealed"],
  ["OK", "Ban lifted", "10/1/2018", "2019", "Same day State Question 792 took effect (full-strength beer and wine in grocery stores), plus later brewery hours"],
  ["IN", "Ban → restricted", "7/1/2024", "2025", "No full post year yet. ≤4 h/day, ≤15 h/week, none 9 p.m.–3 a.m.; $500k liability insurance; to-go cocktails"],
  ["MA", "Ban (204 CMR 4.03)", "12/1984", "1985", "Commission regulation promulgated Nov 21, 1984, in force in December; same week the House passed the drinking-age-21 bill"],
  ["KS", "Ban (L. 1985 ch. 173)", "1985", "1986", "Covered private clubs and 3.2% beer bars, then the only on-premise licensees; same year the age for 3.2% beer rose to 21"],
  ["IN", "Ban (IC 7.1-5-10-20)", "1985", "1986", "Statute (P.L. 86-1985) banning time-of-day price cuts and 2-for-1s; all-day specials allowed"],
  ["NC", "Ban (14B NCAC 15B .0223)", "8/1/1985", "1986", "Commission rule; full-day specials allowed"],
  ["VT", "Ban (Reg. 49)", "~1985", "1986", "Liquor Control Board regulation; adoption year unverified (1985 or 1986)"],
  ["IL", "Ban (235 ILCS 5/6-28)", "1989", "1990", "Ended by the 2015 law after 26 years"],
], [900, 1500, 1150, 1050, 4760]));
kids.push(note(`1980s comparison group: the ${nClean} states in the drinking-age data where the law-by-law check found no statewide happy-hour change in 1980–1995 (data/inputs/coding_1980s_verified.csv). States with partial restrictions (PA, CT, VA, ME, TX, WA, MI, OH and RI) are left out; AK, HI and DC fall outside the drinking-age data. Mid-year transition years are dropped for the treated state. Section 7.9 compares alternative codings.`));
kids.push(P("For each design, state and year fixed effects are fit on untreated state-years only (never-treated states plus treated states before their change). Each treated state’s counterfactual is then imputed, and actual minus imputed outcomes are averaged over the first six full years under the new law (Borusyak, Jaravel & Spiess, 2024). The 1980s models add the minimum legal drinking age, which was rising in the same years, taken from Ruhm’s 1982–88 state panel."));
kids.push(P("With three to six treated states, cluster-robust standard errors are unreliable (Conley & Taber, 2011). Inference instead uses joint randomization. Each draw gives every treated state’s event dates to a different never-treated state of similar size (0.5 to 2 times its pre-period deaths, or the 8 closest in size when fewer qualify), re-fits the model with all of those placebo states treated at once, and recomputes the pooled estimate. Five thousand draws form the null distribution; p-values are equal-tailed and 95% intervals invert that distribution. Per-state p-values compare each state with single-state placebo fits from its size pool. For the modern repeals, each state also gets a synthetic control with in-space placebos (Abadie, Diamond & Hainmueller, 2010)."));
kids.push(P(`An audit script re-derives the key pieces independently (audit_log.md lists every check). Rebuilding sample years from the raw FARS files reproduces the stored aggregates exactly, a saturated two-way fixed-effects regression reproduces the imputation estimates to machine precision, and the synthetic-control and synthetic-DiD weights match an exact constrained optimizer. The audit caught one data quirk, a single 1985 vehicle with two imputed-BAC records, which the build de-duplicates (it moved Texas’s 1985 count by 0.3 deaths). Simulations test the inference by giving the real event dates to randomly chosen never-treated states, where the true effect is zero: at the 5% level the joint test rejected ${(100 * PM[0].reject_5pct).toFixed(1)}% of the time in the modern design and ${(100 * PA[0].reject_5pct).toFixed(1)}% in the 1980s design (${PM[0].sims} simulations each), somewhat above the nominal 5% (Section 7.6). Building the null from separate one-state fits would understate its spread when several states share event dates, as in the 1980s wave, because those states also share the estimation error in the year effects; the joint test avoids this.`));

kids.push(H1("3. Results: the modern repeals"));
kids.push(ttl("Table 2. Headline estimates (average over the first six full years under the new law)"));
const rowsT2 = D.main.filter((r) => r.design === g1).map((r) => {
  const a = M(g2, r.outcome);
  return [r.label, `${sgn(r.att, 2)}  ${ci(r, 2)}`, pv(r.p), `${sgn(a.att, 2)}  ${ci(a, 2)}`, pv(a.p)];
});
kids.push(table(["Outcome", "Repeals: estimate [95% CI]", "p", "1980s bans: estimate [95% CI]", "p"], rowsT2, [3100, 2230, 800, 2430, 800], [1, 2, 3, 4]));
kids.push(note("Repeal estimates are the effect of lifting a ban (positive values would mean bans were working); 1980s estimates are the effect of imposing one (negative values would mean bans work). Intervals and p-values come from 5,000 joint randomization draws (Section 2)."));
kids.push(P(`Across the first six full years after repeal, the impaired share moved by ${sgn(mA.att)} points relative to the imputed counterfactual (${ci(mA)}, ${peq(mA.p)}) and the log odds by ${sgn(mL.att)} (${ci(mL)}). State by state, Kansas moved ${sgn(bKS.att)} points, Illinois ${sgn(bIL.att)} and Oklahoma ${sgn(bOK.att)}; none is unusual against its size-matched placebos (p = ${pv(bKS.p)}, ${pv(bIL.p)} and ${pv(bOK.p)}). A timing placebo that pretends each repeal happened five years early finds nothing (${sgn(tp.att)} points, ${peq(tp.p)}), so there is no sign of pre-existing trends. The estimates barely move when 2020–21 or 2024 are dropped, with fatality weights, with state-specific linear trends, or when only the two full repeals are pooled (Table 4).`));
kids.push(...figure("fig1_modern_repeals_event_study.png", "Figure 1. Modern repeals: actual minus imputed outcomes by event year. Solid black = mean of the three states; it turns dotted where fewer states contribute (Kansas and Illinois through year 8, Kansas alone after that). Colored lines = individual states; gray = 95% range of the same statistic across joint placebo draws. The headline estimates average event years 0–5. Pre-period values are in-sample residuals, so they show fit rather than test for pre-trends; the timing placebo in Table 4 is the formal test."));
kids.push(ttl("Table 3. Synthetic control, alcohol-impaired share (percentage points)"));
kids.push(table(["State", "Pre-period fit (RMSPE)", "Mean post gap", "First six years", "Placebo rank p", "Largest donor weights"],
  [ks, il, ok].map((r) => [r.state, num(r.pre_rmspe_x100, 2), sgn(r.mean_post_gap_x100, 2), sgn(r.first6_post_gap_x100, 2), pv(r.placebo_rank_p), r.donor_weights]),
  [700, 1450, 1250, 1250, 1200, 3510], [1, 2, 3, 4]));
kids.push(note("RMSPE = root mean squared prediction error before the repeal. The placebo rank p is the share of the 37 states (36 donors plus the treated state) with a post/pre RMSPE ratio at least as large as the treated state’s."));
kids.push(P(`Synthetic control tells a similar story for Kansas and Oklahoma: post-repeal gaps of ${sgn(ks.mean_post_gap_x100)} and ${sgn(ok.mean_post_gap_x100)} points, unremarkable against placebos (p = ${pv(ks.placebo_rank_p)} and ${pv(ok.placebo_rank_p)}), although Kansas is poorly fit before 2012. Illinois is the exception. Synthetic Illinois tracked the real state within ${num(il.pre_rmspe_x100, 1)} points from 1994 to 2014, then ran about ${num(il.mean_post_gap_x100, 1)} points below it after 2015, the most extreme ratio of the 37 states (p = ${pv(il.placebo_rank_p)}).`));
kids.push(P("Three things argue against reading this as a repeal effect. Illinois’s impaired share fell by about 1.7 points between 2012–14 and 2016–19, the same as the national average, so the gap reflects a post-2015 decline in the particular donor states rather than a rise in Illinois. Illinois moved only to restricted happy hours, while Kansas and Oklahoma, which repealed outright, show negative gaps. And with three states tested, the chance that one reaches p ≤ 0.03 by luck is roughly 9%. Section 7.1 tests this directly."));
kids.push(...figure("fig2_synthetic_control.png", "Figure 2. Synthetic control gaps (actual minus synthetic) for each repeal state, with donor states run as placebo treated units (gray; placebos with pre-period fit more than five times worse than the treated state’s are omitted)."));

kids.push(H1("4. Results: the 1980s bans"));
kids.push(P(`The 1980s bans give a more precise answer. After the six bans took effect, the impaired share moved by ${sgn(aA.att)} points (${ci(aA)}, ${peq(aA.p)}) and the log odds by ${sgn(aL.att)} (${ci(aL)}), controlling for the rising drinking age. State by state the estimates range from ${sgn(Math.min(...bs80.map((r) => r.att)))} to ${sgn(Math.max(...bs80.map((r) => r.att)))} points, and none is unusual against its size-matched placebos (smallest p = ${pv(Math.min(...bs80.map((r) => r.p)))}). The reported minimum detectable effect at 80% power is ${num(aA.mde80)} points (${pct(aA.mde80, aA.baseline)}% of baseline), against ${num(mA.mde80)} points (${pct(mA.mde80, mA.baseline)}%) for the modern repeals; simulations in Section 7.6 suggest the true 80%-power threshold in the 1980s design is somewhat larger.`));
kids.push(P(`The single-vehicle-night share, a proxy that uses no BAC data, fell by ${num(-aS.att)} points (${ci(aS)}, ${peq(aS.p)}). The evening-versus-night tests separate impaired from sober crashes. Impaired deaths did not shift between weekday evenings and nights (${sgn(aI.att)} log points, ${peq(aI.p)}), but sober deaths did: in ban states they moved from nighttime toward weekday evenings (${sgn(aP.att)} log points, ${peq(aP.p)}). A happy hour law should not move sober crashes. That shift is what produces the net evening test of ${sgn(aN.att)} log points (${ci(aN)}, ${peq(aN.p)}), which points the way a working ban would only because the sober side moved. Section 7.3 shows that seat-belt, speed-limit, BAC-law and income controls do not remove the sober shift, and Section 7.7 finds the same timing shift in all deaths, which use no BAC data.`));
kids.push(...figure("fig3_adoption_wave_event_study.png", "Figure 3. 1980s bans: actual minus imputed outcomes by event year. Solid black = mean of the six states, dotted where fewer states contribute; gray lines = individual states; shaded = 95% placebo range."));

kids.push(H1("5. What the evidence rules out"));
kids.push(P(`Figure 4 summarizes every headline estimate with its randomization interval. Read as equivalence bounds, the 1980s evidence rules out ban effects larger than about ${pct(-aA.ci_lo, aA.baseline)}% of the impaired share and ${oddsPct(aL.ci_lo)}% of the odds that a death involved an impaired driver. The modern repeals are less precise but rule out increases larger than about ${pct(mA.ci_hi, mA.baseline)}% of the share and ${oddsPct(mL.ci_hi)}% of the odds. Effects beyond those bounds are not supported by the data; smaller effects cannot be excluded.`));
kids.push(...figure("fig4_summary_estimates.png", "Figure 4. All headline estimates with 95% randomization-inference intervals."));

kids.push(H1("6. Robustness"));
const cellR = (r) => (r ? `${sgn(r.att, 2)} (${pv(r.p)})` : "");
const specsM = [["Main", null], ["Drop 2020–21", "excl. 2020-21"], ["Drop 2024", "excl. 2024 (newest FARS year)"], ["Fatality-weighted", "fatality-weighted"],
  ["All post years", "all post years"], ["State linear trends", "state linear trends"], ["KS + OK only", "KS + OK only (full repeals)"], ["Timing placebo (5 yrs early)", "timing placebo (5 yrs early)"]];
kids.push(ttl("Table 4. Robustness, modern repeals: estimate (p)"));
kids.push(table(["Specification", "Impaired share (pp)", "Log odds (x100)", "Net evening test (x100)"],
  specsM.map(([lab, sp]) => [lab, ...["ai_share", "log_odds", "ddd_net"].map((o) => cellR(sp ? RB(g1, sp, o) : M(g1, o)))]),
  [3060, 2100, 2100, 2100], [1, 2, 3]));
kids.push(note("The timing placebo uses only true pre-repeal years, so its window is event years 0–3 of the fake date."));
const specsA = [["Main", null], ["Include partial-restriction states as controls", "incl. partial-restriction states as controls"], ["No drinking-age covariate", "no MLDA covariate"], ["Fatality-weighted", "fatality-weighted"]];
kids.push(ttl("Table 5. Robustness, 1980s bans: estimate (p)"));
kids.push(table(["Specification", "Impaired share (pp)", "Single-vehicle-night (pp)", "Sober placebo (x100)", "Net evening test (x100)"],
  specsA.map(([lab, sp]) => [lab, ...["ai_share", "svn_share", "ddd_sober", "ddd_net"].map((o) => cellR(sp ? RB(g2, sp, o) : M(g2, o)))]),
  [2960, 1600, 1600, 1600, 1600], [1, 2, 3, 4]));
kids.push(note("Partial-restriction states are the nine identified by the law-by-law check (Table 1 note)."));

kids.push(H1("7. Follow-up checks"));
kids.push(H2("7.1 Stress-testing the Illinois synthetic control"));
const bBase = FB("Base"), bMS = FB("Leave out MS"), bNoS = FB("No Southern"), bMW = FB("Midwest and Northeast"), bFake = FB("In-time placebo");
kids.push(P(`The Illinois gap depends on which states make up synthetic Illinois (Table 6, Figure 5). Mississippi carries the largest weight (${F.base_w.MS.toFixed(2)}); dropping it alone cuts the post-2015 gap from ${num(bBase.post)} to ${num(bMS.post)} points, and excluding Southern donors erases it (${sgn(bNoS.post)} points, p = ${pv(bNoS.p)}). With Midwestern and Northeastern donors only, the gap is ${sgn(bMW.post)} points (p = ${pv(bMW.p)}), and across the leave-one-out fits it ranges from ${num(F.loo_range[0])} to ${num(F.loo_range[1])} points. An in-time placebo that pretends Illinois repealed in 2008, using only data through 2014, produces a ${sgn(bFake.post)}-point gap that is also nominally significant (p = ${pv(bFake.p)}): the placebo-rank test flags Illinois even when nothing happened, so it overstates the evidence for this state. The original Illinois result reflects a post-2015 decline in a few Southern donor states, not a change in Illinois.`));
kids.push(ttl("Table 6. Illinois synthetic control under alternative specifications (impaired share, percentage points)"));
kids.push(table(["Specification", "Pre-fit RMSPE", "Post gap", "First six years", "Placebo p", "Largest donor weights"],
  F.B.map((r) => [r.test, num(r.pre, 2), sgn(r.post, 2), sgn(r.first6, 2), r.p === null ? "–" : pv(r.p), r.donors]),
  [2860, 900, 900, 950, 850, 2900], [1, 2, 3, 4]));
kids.push(...figure("fig5_illinois_stress_tests.png", "Figure 5. Illinois minus synthetic Illinois under alternative donor pools (left) and with each positive-weight donor dropped in turn (right). The dashed line marks the July 2015 repeal."));
kids.push(H2("7.2 Synthetic difference-in-differences"));
const cK = FC("KS", "ai_share"), cI = FC("IL", "ai_share"), cO = FC("OK", "ai_share"), cP = FC("Pooled (mean of 3)", "ai_share");
kids.push(P(`Synthetic difference-in-differences (Arkhangelsky et al., 2021) combines synthetic-control weights on comparison states with weights on pre-repeal years and lets each state differ in level from its comparison group. It finds nothing for any of the three repeals (Table 7): ${sgn(cK.tau)} points for Kansas, ${sgn(cI.tau)} for Illinois and ${sgn(cO.tau)} for Oklahoma on the impaired share, with placebo p-values of ${pv(cK.p)}, ${pv(cI.p)} and ${pv(cO.p)}. The pooled estimate is ${sgn(cP.tau)} points (${ci(cP)}, p = ${pv(cP.p)}), with an interval about as wide as the imputation estimator’s.`));
kids.push(ttl("Table 7. Synthetic difference-in-differences: estimate [95% placebo interval] (p)"));
kids.push(table(["State", "Impaired share (pp)", "Log odds (x100)"],
  ["KS", "IL", "OK", "Pooled (mean of 3)"].map((st) => [st, ...["ai_share", "log_odds"].map((o) => { const r = FC(st, o); return `${sgn(r.tau, 2)} [${num(r.ci_lo, 1)}, ${num(r.ci_hi, 1)}] (${pv(r.p)})`; })]),
  [2360, 3500, 3500], [1, 2]));
kids.push(note("State intervals are the estimate ± 1.96 standard deviations of 36 in-space placebo estimates; the pooled interval inverts 5,000 randomization draws."));
kids.push(H2("7.3 Traffic-safety controls for the 1980s bans"));
const a1 = (o) => FA(SA1, o);
kids.push(P(`The 1980s bans overlapped with other traffic-safety changes: seat-belt laws took effect in Kansas and North Carolina in ${F.belt_first.KS} and Indiana in ${F.belt_first.IN}, right as their bans began, and many states raised rural speed limits to 65 mph in 1987. Using Cohen and Einav’s state panel (1983–1997), this check controls for primary and secondary seat-belt laws, 65-mph limits, .08 BAC laws and per-capita income, and adds impaired and sober deaths per vehicle-mile as outcomes. Georgia, where counties and cities around Atlanta banned happy hours locally in 1985, is already outside the comparison group.`));
kids.push(P(`The alcohol measures stay flat: the impaired share moves ${sgn(a1("ai_share").att)} points (${ci(a1("ai_share"))}, ${peq(a1("ai_share").p)}) and impaired deaths per mile ${sgn(a1("ai_per_vmt").att)} log points (${peq(a1("ai_per_vmt").p)}). The controls do not explain the sober shift: sober deaths still move from nighttime toward weekday evenings (${sgn(a1("ddd_sober").att)} log points, ${peq(a1("ddd_sober").p)}), and the single-vehicle-night share changes by ${sgn(a1("svn_share").att)} points (${peq(a1("svn_share").p)}). With the sober side moving, the net evening test reaches ${sgn(a1("ddd_net").att)} (${peq(a1("ddd_net").p)}), nominally significant but for the reason given in Section 4: it reflects more sober evening deaths, not fewer impaired ones. Seat-belt laws are therefore not the explanation for the timing shift, and whatever caused it was not specific to alcohol.`));
kids.push(ttl("Table 8. 1980s bans, 1983–1995, with added controls: estimate (p)"));
const specsF = ["1983-95, drinking age only", SA1];
kids.push(table(["Outcome", "Drinking age only", "+ traffic-safety controls"],
  ["ai_share", "log_odds", "ai_per_vmt", "sober_per_vmt", "svn_share", "ddd_sober", "ddd_net"].map((o) =>
    [FA(specsF[0], o).label, ...specsF.map((sp) => `${sgn(FA(sp, o).att, 2)} (${pv(FA(sp, o).p)})`)]),
  [4360, 2500, 2500], [1, 2]));
kids.push(...figure("fig6_1980s_with_traffic_controls.png", "Figure 6. 1980s bans with and without traffic-safety controls (95% randomization intervals)."));
kids.push(H2("7.4 Coding and data checks"));
kids.push(P("Oklahoma’s repeal took effect on October 1, 2018, the same day as State Question 792’s liquor modernization (full-strength beer and wine in grocery and convenience stores, refrigerated beer in liquor stores) and a law letting breweries stay open until 2 a.m., so its post-period measures a bundle; Table 1 notes this. In the modern design Utah is coded as banned throughout, as in APIS, although some press accounts date its comprehensive ban to 2011; the law-by-law check found no statewide Utah law in 1980–1995, which is why Utah sits in the 1980s comparison group. If Utah adopted its ban during the modern sample, it is not a clean comparison state there; dropping it moves the modern-repeal estimate from −1.39 to −1.30 points. NHTSA first released the 2024 FARS annual file on April 1, 2026, and final releases follow 12 to 15 months after the initial release, so the 2024 jumps in Kansas and Oklahoma should be re-checked in the final file. On the same schedule, Indiana’s first full post-repeal year (2025) would arrive around spring 2027."));
kids.push(H2("7.5 Deaths per vehicle-mile (FHWA VM-2)"));
kids.push(P(`FHWA’s VM-2 series gives vehicle-miles traveled by state, road type and rural or urban area for ${VD.years[0]}–${VD.years[1]}. Summed to state totals, it matches Cohen and Einav’s mileage series to within 0.2% in 90% of state-years over their 1983–1997 overlap. Rates per mile answer the exposure question directly: if lifting a ban raised drinking and driving, impaired deaths per mile should rise while sober deaths per mile stay put.`));
kids.push(P(`After the modern repeals, impaired deaths per 100 million vehicle-miles (${VD.rates.modern_treated.toFixed(2)} in the three states before repeal) changed by ${pc(vM.att)}% (95% interval ${pc(vM.ci_lo)}% to ${pc(vM.ci_hi)}%, ${peq(vM.p)}); synthetic difference-in-differences gives ${pc(sdV.tau)}% (${peq(sdV.p)}). Sober deaths per mile, the placebo, rose ${pc(vMs.att, 0)}% (${peq(vMs.p)}) by similar amounts in all three states, and ${pc(vMx.att, 0)}% (${peq(vMx.p)}) without 2020–21. That is a general rise in road deaths in these states, not an alcohol effect, and it is exactly what the log odds of impaired versus sober deaths nets out: the log-odds estimate equals the impaired-per-mile estimate minus the sober-per-mile estimate. After the 1980s bans, impaired deaths per mile (${VD.rates.adoption_treated.toFixed(2)} per 100 million miles before the bans) changed by ${pc(vA.att)}% (${pc(vA.ci_lo)}% to ${pc(vA.ci_hi)}%, ${peq(vA.p)}), and by ${pc(vA2.att)}% with the full traffic-safety controls, so the bans did not cut the per-mile rate by more than about ${Math.abs(100 * (Math.exp(vA.ci_lo / 100) - 1)).toFixed(0)}%. Adding log vehicle-miles and the rural share of driving as covariates leaves the modern-repeal estimates unchanged (impaired share ${sgn(vC1.att)} points, ${peq(vC1.p)}).`));
kids.push(ttl("Table 9. Estimates with FHWA vehicle-miles: estimate [95% CI] (per-mile outcomes in log points; shares in pp)"));
kids.push(table(["Design", "Specification", "Outcome", "Estimate [95% CI]", "p"],
  VD.rows.map((r) => [r.design === "modern_repeals" ? "Repeals" : "1980s bans", r.spec, r.label, `${sgn(r.att, 2)} ${ci(r, 1)}`, pv(r.p)]),
  [1150, 2400, 2900, 2110, 800], [3, 4]));
kids.push(note("Log points x100 approximate percent changes for small values. Randomization intervals as in Table 2."));
kids.push(...figure("fig7_per_mile_event_study.png", "Figure 7. Deaths per vehicle-mile: actual minus imputed counterfactual for impaired deaths after the modern repeals (left), sober deaths after the repeals as a placebo (middle), and impaired deaths after the 1980s bans (right)."));
kids.push(H2("7.6 Calibration, date sensitivity and an early look at Indiana"));
kids.push(P(`Simulations measure how the inference behaves. The real event dates go to randomly chosen never-treated states, either as they are (true effect zero) or with an effect equal to the reported minimum detectable effect added to their post-change years (Table 10). The test is slightly liberal in both designs: at the 5% level it rejects a true null ${f0(PM[0].reject_5pct)}% of the time for the modern impaired share and ${f0(PM[2].reject_5pct)}% for the modern net evening test, and ${f0(PA[0].reject_5pct)}% for the 1980s impaired share and ${f0(PA[2].reject_5pct)}% for the 1980s single-vehicle-night share. p-values near 0.05 therefore deserve skepticism; none of the headline impaired-share estimates comes close to that threshold. Power at the stated minimum detectable effect is ${f0(PM[1].reject_5pct)}% in the modern design but only ${f0(PA[1].reject_5pct)}% in the 1980s design, so the reported 1980s minimum detectable effect understates the effect size the design can reliably detect. The average estimate is close to the injected effect (${num(PM[1].mean_estimate_x100, 2)} vs ${num(PM[1].injected_x100, 2)} and ${num(PA[1].mean_estimate_x100, 2)} vs ${num(PA[1].injected_x100, 2)} points), so the estimator shows little bias.`));
kids.push(ttl("Table 10. Simulated false-positive rates and power of the joint randomization test"));
const OL = { ai_share: "Impaired share (pp)", ddd_net: "Net evening test (x100)", svn_share: "Single-vehicle-night share (pp)" };
kids.push(table(["Design", "Outcome", "Injected effect", "Simulations", "Rejected at 5% (± s.e.)", "At 10%", "Mean estimate"],
  [...PM, ...PA].map((r) => [r.design === "modern_repeals" ? "Repeals" : "1980s bans", OL[r.outcome], r.injected_x100 ? num(r.injected_x100, 2) : "none",
    String(r.sims), `${(100 * r.reject_5pct).toFixed(1)}% (± ${(100 * r.mc_se).toFixed(1)})`, `${(100 * r.reject_10pct).toFixed(1)}%`, sgn(r.mean_estimate_x100, 2)]),
  [1100, 2200, 1000, 1250, 1760, 850, 1200], [2, 3, 4, 5, 6]));
kids.push(note("With no injected effect, the rejection rate is the false-positive rate (target 5% and 10%); with the minimum detectable effect injected, it is power (target about 80% at 5%)."));
kids.push(P(`Second, the 1980s dates. Moving any single adopter’s date one year earlier or later leaves the impaired-share estimate between ${sgn(TN.dates.ai_share.min_att, 2)} and ${sgn(TN.dates.ai_share.max_att, 2)} points, with p-values from ${pv(TN.dates.ai_share.min_p)} to ${pv(TN.dates.ai_share.max_p)}. The single-vehicle-night estimate ranges from ${sgn(TN.dates.svn_share.min_att, 2)} to ${sgn(TN.dates.svn_share.max_att, 2)} points, with p-values from ${pv(TN.dates.svn_share.min_p)} to ${pv(TN.dates.svn_share.max_p)}; it is most sensitive to ${sens(TN.dates.svn_share.most_sensitive)}.`));
kids.push(P(`Third, month-level data from the 2016–2024 FARS files, whose monthly totals match the annual data exactly, allow an early look at Indiana. The six months after its July 2024 change are compared with a counterfactual built from ${INm.placebos} states with at least 300 deaths a year, allowing each state its own seasonal pattern. Indiana’s impaired share changed by ${sgn(INm.att_pp)} points (95% interval ${num(INm.ci_lo_pp)} to ${sgn(INm.ci_hi_pp)}, p = ${pv(INm.p)}; Figure 8), within the range of Indiana’s own swings when the same test is run at fake July dates in 2018–2023 (${num(Math.min(...ITP))} to ${sgn(Math.max(...ITP))} points). With six months of data the smallest reliably detectable effect is ${num(INm.mde80_pp)} points, about ${pct(INm.mde80_pp, INm.baseline_share_pct)}% of Indiana’s ${INm.baseline_share_pct.toFixed(0)}% baseline, and the 2024 file is still preliminary, so this says nothing yet about Indiana. The same monthly method applied to Oklahoma, now including the October–December 2018 months that the annual design drops, gives ${sgn(OKm.att_pp)} points (${num(OKm.ci_lo_pp)} to ${sgn(OKm.ci_hi_pp)}, p = ${pv(OKm.p)}), consistent with the annual result.`));
kids.push(...figure("fig8_indiana_early_look.png", "Figure 8. Indiana, month by month: actual minus imputed impaired share, with the 95% range of the same statistic for placebo states given the July 2024 date. The dashed line marks the July 1, 2024 change."));
kids.push(H2("7.7 Mechanism and specification checks"));
const wkM = MR("weekend", "modern_repeals", "we_net"), wkMi = MR("weekend", "modern_repeals", "we_ai"), wkMs = MR("weekend", "modern_repeals", "we_sober"), wkA = MR("weekend", "adoption_1980s", "we_net");
const tA = MR("timing", "adoption_1980s", "tod_all"), eA = MR("timing", "adoption_1980s", "eve_per_vmt"), nA = MR("timing", "adoption_1980s", "night_per_vmt"), tM = MR("timing", "modern_repeals", "tod_all");
kids.push(P(`Happy hours are mostly a weekday practice, so a sharper mechanism test compares weekday evenings (Monday–Friday, 4–10 p.m.) with weekend evenings at the same hours, when light and traffic are similar but happy hours are rare. After the modern repeals, the odds that a weekday-evening death involved an impaired driver rose by ${num(wkM.att)} log points relative to weekend evenings (95% interval ${num(wkM.ci_lo)} to ${num(wkM.ci_hi)}, p = ${pv(wkM.p)}). The estimate is positive in all three states (Kansas ${sgn(WK.main.by_state.KS.att, 0)}, Illinois ${sgn(WK.main.by_state.IL.att, 0)}, Oklahoma ${sgn(WK.main.by_state.OK.att, 0)}) and in every specification in Table 11, and a placebo run five years before the repeals finds nothing. The 1980s bans move it the other way (${sgn(wkA.att)}, p = ${pv(wkA.p)}), as working bans would.`));
kids.push(P(`Three cautions keep this from being a finding. Simulations show the test is liberal for this outcome, rejecting true nulls ${f0(WK.size.reject_5pct)}% of the time at the 5% level; only ${f0(WK.size.share_p_at_or_below_actual)}% of null simulations produce a p-value as small as the actual one, so the calibrated p-value is about ${pv(WK.size.share_p_at_or_below_actual)}. Only part of the estimate comes from impaired deaths (${sgn(wkMi.att)}, p = ${pv(wkMi.p)}); the rest is a fall in sober weekday-evening deaths (${sgn(wkMs.att)}, p = ${pv(wkMs.p)}), which a happy hour law should not cause. And with total impaired deaths unchanged, the pattern is at most suggestive of displacement: repeals shifting when alcohol-involved crashes happen rather than how many there are.`));
kids.push(ttl("Table 11. Weekday-vs-weekend evening test, modern repeals (x100): estimate [95% CI] and p"));
const wr = [["Main", WK.main.att, wkM.ci_lo, wkM.ci_hi, WK.main.p], ...Object.entries(WK.robustness).map(([k, v]) => [k.charAt(0).toUpperCase() + k.slice(1), v.att, v.ci_lo, v.ci_hi, v.p])];
kids.push(table(["Specification", "Estimate [95% CI]", "p"], wr.map(([k, a, lo, hi, p]) => [k, `${sgn(a, 1)} [${num(lo, 1)}, ${num(hi, 1)}]`, pv(p)]), [4360, 3400, 1600], [1, 2]));
kids.push(note(`p-values are nominal; calibrated by simulation, the main p-value is about ${pv(WK.size.share_p_at_or_below_actual)}.`));
kids.push(P(`The 1980s timing shift is not an artifact of BAC imputation. The evening-versus-night contrast for all deaths, which uses no BAC data, rises ${num(tA.att, 0)} log points after the bans (${peq(tA.p)}). Per vehicle-mile, weekday-evening deaths rose ${pc(eA.att, 0)}% (${peq(eA.p)}) while night deaths changed ${pc(nA.att, 0)}% (${peq(nA.p)}), the same direction though neither is significant on its own. The shift appears in sober crashes and in all deaths but not in impaired crashes, which is why it shows up in the sober placebo but not in the alcohol measures. The modern repeals show no such shift (${sgn(tM.att)}, ${peq(tM.p)}).`));
const nbM = MR("neighbors", "modern_repeals", "ai_share"), nbA = MR("neighbors", "adoption_1980s", "ai_share");
const jk = (g, y) => MT.rows.filter((r) => r.section === "jackknife" && r.design === g && r.outcome === y);
const spanTxt = (a) => `${sgn(Math.min(...a.map((r) => r.att)))} and ${sgn(Math.max(...a.map((r) => r.att)))}`;
const jkS = jk("adoption_1980s", "svn_share"), jkMin = jkS.reduce((a, b) => (a.p < b.p ? a : b));
const jkSig = jkS.filter((r) => r.p < 0.05).length;
kids.push(P(`Dropping states that border a treated state, where cross-border drinking could contaminate the comparison, leaves the impaired-share estimates essentially unchanged (repeals ${sgn(nbM.att)} points, ${peq(nbM.p)}; 1980s ${sgn(nbA.att)}, ${peq(nbA.p)}). Dropping one treated state at a time moves the repeal estimate between ${spanTxt(jk("modern_repeals", "ai_share"))} points and the 1980s estimate between ${spanTxt(jk("adoption_1980s", "ai_share"))}, none significant. The single-vehicle-night estimate is significant in ${jkSig} of the six leave-one-out fits (${jkMin.spec.replace("without", "without")}: ${sgn(jkMin.att)} points, ${peq(jkMin.p)}).`));
kids.push(P(`Pooling all nine law changes as the effect of having a ban, with the repeal estimates sign-flipped and each law change weighted equally, gives the tightest answer: a ban changes the odds that a traffic death involved an impaired driver by ${pc(PL.att, 0)}% (95% interval ${pc(PL.ci_lo, 0)}% to ${pc(PL.ci_hi, 0)}%, ${peq(PL.p)}) and the impaired share by ${sgn(PS.att)} points (${num(PS.ci_lo)} to ${sgn(PS.ci_hi)}). Inverse-variance weights give the same result. Bans did not lower the odds of alcohol involvement by more than about ${Math.abs(100 * (Math.exp(PL.ci_lo / 100) - 1)).toFixed(0)}%.`));
const MD = MT.midrvacc;
kids.push(P(`As a further check on the data build, NHTSA’s own highest-driver-BAC file for 2013–2015 agrees with the build’s driver-BAC construction for ${(100 * Math.min(...MD.map((r) => r.identical_share))).toFixed(1)}% or more of crashes, and national impaired deaths differ by at most ${Math.max(...MD.map((r) => 100 * (r.impaired_deaths_mine / r.impaired_deaths_nhtsa_file - 1))).toFixed(1)}%.`));
kids.push(P(`Figure 9 collects the impaired-share estimates from the main designs and every robustness check in Sections 6–7, including the unemployment controls and the alternative 1980s codings: ${MT.curve.n_modern} for the repeals (${sgn(MT.curve.range_modern[0])} to ${sgn(MT.curve.range_modern[1])} points) and ${MT.curve.n_1980s} for the 1980s bans (${sgn(MT.curve.range_1980s[0])} to ${sgn(MT.curve.range_1980s[1])}). None is statistically significant.`));
kids.push(...figure("fig9_specification_curve.png", "Figure 9. Impaired-share estimates from the main designs and every robustness check, sorted, with 95% intervals: modern repeals (left) and 1980s bans (right). The partial-restriction estimates in Table 13 are not ban effects and are not shown."));
kids.push(H2("7.8 Unemployment and population (FRED)"));
const uM = FR("modern_repeals", "+ unemployment", "ai_share"), uA = FR("adoption_1980s", "+ unemployment", "ai_share"), sM = FR("modern_repeals", "per capita", "sober_per_cap");
const fAu = FR("adoption_1980s", "per capita + unemployment", "ai_per_cap"), sdC = FD.sdid.find((r) => r.outcome === "ai_per_cap");
const pwM = FR("modern_repeals", "population-weighted", "ai_share"), pwA = FR("adoption_1980s", "population-weighted", "ai_share");
kids.push(P(`FRED’s annual state unemployment rates (averages of the monthly BLS series) and Census resident population for 1982–2024 pass every check in the audit log. The file is complete for all 51 jurisdictions and 43 years. Every unemployment value is an exact average of twelve one-decimal monthly rates, as FRED’s annual series are, and the values agree with the independently compiled figures in Ruhm’s 1982–88 panel (correlation 0.996, mean difference 0.18 points; the remaining gaps reflect later BLS revisions). State populations sum to the published US totals within 0.05%, and population-weighted state unemployment tracks the national rate within 0.06 points. One quirk: Nevada and the District of Columbia jump 12% and 10% in 2000, where the population series switches from 1990s estimates to the 2000 census count. Dropping both states moves the per-capita repeal estimate from ${pc(fM.att)}% to ${pc(FD.nvdc.att)}%.`));
kids.push(P(`Unemployment as a control leaves the estimates unchanged (repeals: impaired share ${sgn(uM.att)} points, ${peq(uM.p)}; 1980s: ${sgn(uA.att)}, ${peq(uA.p)}). Per 100,000 residents, impaired deaths changed by ${pc(fM.att)}% after the repeals (95% interval ${pc(fM.ci_lo)}% to ${pc(fM.ci_hi)}%, ${peq(fM.p)}; ${FD.base_per_100k.modern_repeals.toFixed(1)} per 100,000 before), with synthetic difference-in-differences giving ${pc(sdC.tau)}% (${peq(sdC.p)}) and sober deaths per resident ${pc(sM.att, 0)}% (${peq(sM.p)}). After the 1980s bans the change was ${pc(fA.att)}% (${pc(fA.ci_lo)}% to ${pc(fA.ci_hi)}%, ${peq(fA.p)}; ${FD.base_per_100k.adoption_1980s.toFixed(1)} per 100,000 before), and ${pc(fAu.att)}% with unemployment controlled. Weighting states by population instead of equally gives the same answer (impaired share ${sgn(pwM.att)} points for repeals, ${sgn(pwA.att)} for bans; Table 12).`));
kids.push(ttl("Table 12. Estimates with FRED unemployment and population: estimate [95% CI] (per-capita outcomes in log points; shares in pp)"));
kids.push(table(["Design", "Specification", "Outcome", "Estimate [95% CI]", "p"],
  FD.rows.map((r) => [r.design === "modern_repeals" ? "Repeals" : "1980s bans", r.spec, r.label, `${sgn(r.att, 2)} ${ci(r, 1)}`, pv(r.p)]),
  [1150, 2400, 2900, 2110, 800], [3, 4]));
kids.push(note("Joint randomization intervals as in Table 2; population-weighted rows weight each state by its pre-change population."));
kids.push(H2("7.9 The 1980s coding and alternative codings"));
kids.push(P(`The 1980s design rests on a law-by-law check of every state’s happy-hour history for 1980–1995, against statutes, regulations and the 1994 NHTSA digest (data/inputs/coding_1980s_verified.csv). It confirmed the adoption years of the six bans and shaped the design in three ways. First, Pennsylvania (December 1985), Connecticut (January 1986) and Virginia (about 1985) restricted drink specials themselves, and several Atlanta-area counties banned happy hours in 1985, so states with any restriction are left out of the comparison group, while Delaware and Utah, which had no statewide law in the period, are included. Second, Rhode Island’s 1985 law was a partial restriction: the state supreme court described it that year as banning multi-drink price inducements and happy-hour advertising, not single-drink discounts. Third, the laws differ in strength. The check classes Kansas, Indiana and Rhode Island as partial restrictions, but by the standard it applies to North Carolina (time-limited price cuts banned, full-day specials allowed) Indiana’s statute is a ban, and Kansas’s covered every on-premise licensee then licensed, so the main design treats six states as bans. Vermont’s adoption date remains unverified (1985 or 1986).`));
kids.push(P(`Table 13 compares alternative codings against the same ${nClean}-state comparison group. Keeping only the four laws the check classes as strict bans gives ${sgn(b4("ai_share").att)} points on the impaired share (${peq(b4("ai_share").p)}), counting Rhode Island as a seventh ban gives ${sgn(RR("Original seven", "ai_share").att)} (${peq(RR("Original seven", "ai_share").p)}), and moving Vermont to 1986 or adding Alaska’s 1986 ban changes little. The net evening test points the way a working ban would in every ban coding, but as in the main design it is not matched by any change in the impaired share, and it weakens with Alaska included.`));
kids.push(P(`One result is a genuine surprise. The nine partial restrictions (Pennsylvania, Connecticut, Virginia, Maine, Texas, Washington, Michigan, Ohio and Rhode Island) are followed by a drop in the impaired share of ${num(-pt("ai_share").att)} points (95% interval ${num(pt("ai_share").ci_lo)} to ${num(pt("ai_share").ci_hi)}, ${peq(pt("ai_share").p)}). It survives traffic-safety and unemployment controls (${sgn(PCk["+ traffic-safety controls and unemployment (1983-95; WA, MI lack pre-years)"].att)} points) and dropping any single uncertain state, and it is negative in eight of the nine states. It is still hard to read as a happy-hour effect: the stronger laws show nothing, there is no evening timing signature (${sgn(pt("ddd_net").att, 0)}, ${peq(pt("ddd_net").p)}), Maine and Ohio contribute the largest drops, and it is one of many estimates in this paper. Follow-up research supports reading it as a confound. Maine adopted immediate license suspension in 1984 and in August 1988 lowered its BAC limit to .08, and to .05 for convicted offenders; Cohen and Einav’s panel independently dates Maine’s .08 law to ${RC.followup.maine_08_first_year_cohen_einav}. Ohio’s substantive rule dates to April 15, 1988 (its official rule history lists no earlier version; before then Ohio restricted only drink-price advertising), and Ohio adopted immediate license suspension in September 1993. Without Maine and Ohio, the estimate falls to ${sgn(FU["without Maine and Ohio"].att)} points (${peq(FU["without Maine and Ohio"].p)}), and cutting their post-periods before those laws leaves ${sgn(FU["Maine and Ohio post-periods cut before their confounding laws"].att)} (${peq(FU["Maine and Ohio post-periods cut before their confounding laws"].p)}), with Maine’s 1984 suspension law still inside that window. The result rests on two states with confounding laws, so it is not a finding.`));
kids.push(ttl("Table 13. Alternative 1980s codings, same comparison group: estimate (p)"));
const DN = ["Six bans (MA, KS, IN, NC, VT, IL)", "Four strict bans (MA, NC, VT, IL)", "Original seven, clean comparison group", "Six bans, Vermont dated 1986", "Six bans plus Alaska (1983-95)", "Nine partial restrictions"];
const DL = { "Six bans (MA, KS, IN, NC, VT, IL)": "Six bans (main design)", "Four strict bans (MA, NC, VT, IL)": "Four strict bans only (MA, NC, VT, IL)", "Original seven, clean comparison group": "Six bans plus Rhode Island", "Six bans plus Alaska (1983-95)": "Six bans plus Alaska (1983–95)" };
kids.push(table(["Treated states", "Impaired share (pp)", "Log odds (x100)", "Per 100k (log x100)", "Net evening test (x100)"],
  DN.map((d) => [DL[d] || d, ...["ai_share", "log_odds", "ai_per_cap", "ddd_net"].map((o) => { const r = RC.rows.find((x) => x.design === d && x.outcome === o); return `${sgn(r.att, 2)} (${pv(r.p)})`; })]),
  [2960, 1600, 1600, 1600, 1600], [1, 2, 3, 4]));
kids.push(note("Joint randomization p-values in parentheses. Each row uses its own randomization draws, so p-values for the main-design row can differ slightly from Table 2."));

kids.push(H1("8. Limitations"));
kids.push(BUL([{ text: "Imputed BACs. ", bold: true }, "NHTSA imputes missing BACs partly from crash characteristics, including time of day. That pulls untested drivers toward national time-of-day patterns and biases the evening-versus-night tests toward zero. BAC testing rates were also much lower in the 1980s. The 1980s timing shift, however, also appears in all deaths, which use no BAC data (Section 7.7)."]));
kids.push(BUL([{ text: "1980s coding. ", bold: true }, "Dates are verified law by law (Section 7.9), but Vermont’s adoption year, the exact days for several states and the adoption date of Rhode Island’s broader price regulation remain unconfirmed, and the line between a ban and a restriction is a judgment call for Kansas and Indiana. Shifting any one date by a year leaves the impaired-share result intact."]));
kids.push(BUL([{ text: "Bundled reforms. ", bold: true }, "Kansas’s 2012 repeal came in a broad liquor bill; Indiana’s adds an insurance mandate and to-go cocktails; Oklahoma’s took effect the same day as State Question 792’s liquor modernization."]));
kids.push(BUL([{ text: "Few treated units. ", bold: true }, `Randomization inference assumes similar-size states are exchangeable; in simulations the joint test rejected true nulls ${(100 * PM[0].reject_5pct).toFixed(0)}% (modern) and ${(100 * PA[0].reject_5pct).toFixed(0)}% (1980s) of the time at the 5% level, and the 1980s design has less power than its reported minimum detectable effect implies. The COVID years and the newest file (2024) add noise; Kansas and Oklahoma both jump 7–10 points in 2024, and dropping 2024 does not change the results.`]));
kids.push(BUL([{ text: "Covariates. ", bold: true }, "Robustness checks in both designs add vehicle-miles, the rural share of driving, unemployment and population, and the 1980s checks also control for seat-belt, speed-limit and BAC laws and income. State-specific drinking trends and other concurrent laws remain uncontrolled, and the shift in 1980s crash timing remains unexplained."]));

kids.push(H1("9. Policy context and a better experiment"));
kids.push(P("Massachusetts, which banned happy hour in 1984, is actively debating repeal. In July 2026 the state Senate adopted Sen. Julian Cyr’s municipal local-option happy hour amendment to its economic development bill, S.3178 (State House News Service, 2026b). Cyr’s earlier versions of the proposal barred discounts after 10 p.m. and required drink prices to stay fixed during a promotion (Boston.com, 2024). Only the Senate version of the bill includes it. The bill is now in a House–Senate conference, where House negotiators dropped the same proposal in 2022 and 2024 (NBC Boston, 2022; State House News Service, 2026a), and Speaker Mariano has suggested it faces a dim future (State House News Service, 2026a). Under new rules, though, the Legislature has until the end of 2026 to act on bills sent to conference by July 31 (Massachusetts High Technology Council, 2026). Indiana’s 2024 law, now in effect, will provide a fourth repeal once FARS data for 2025 and later are released."));
kids.push(P("A municipal local option would be a far better natural experiment than anything in this project: many towns opting in at different dates under one state’s laws and enforcement. Crash records from the Massachusetts Department of Transportation could support a town-level staggered design, and it would be worth specifying that analysis before any law takes effect."));

kids.push(H1("10. Next steps"));
kids.push(BUL(`Add Indiana once the 2025 FARS file is released (the early look at July–December 2024 is uninformative: ${sgn(INm.att_pp)} points, ${num(INm.ci_lo_pp)} to ${sgn(INm.ci_hi_pp)}), and re-check 2024 in NHTSA’s final release.`));
kids.push(BUL("With Indiana’s 2025 data, test the weekday-evening pattern directly: its law allows discounts only before 9 p.m."));
kids.push(BUL("Pin down Vermont’s adoption date, which likely needs 1985–87 Liquor Control Board minutes or newspaper archives, and when Rhode Island’s broader price regulation (Rule 16) took effect."));
kids.push(BUL("Re-run the evening-versus-night tests on drivers with actual BAC test results, removing the imputation’s pull toward national time-of-day patterns."));
kids.push(BUL("Specify a town-level design in advance for a Massachusetts local option."));

kids.push(H1("References"));
[
  "Abadie, A., Diamond, A., & Hainmueller, J. (2010). Synthetic control methods for comparative case studies. Journal of the American Statistical Association, 105(490), 493–505.",
  "Arkhangelsky, D., Athey, S., Hirshberg, D. A., Imbens, G. W., & Wager, S. (2021). Synthetic difference-in-differences. American Economic Review, 111(12), 4088–4118.",
  "Borusyak, K., Jaravel, X., & Spiess, J. (2024). Revisiting event-study designs: Robust and efficient estimation. Review of Economic Studies, 91(6), 3253–3285.",
  "Cohen, A., & Einav, L. (2003). The effects of mandatory seat belt laws on driving behavior and traffic fatalities. Review of Economics and Statistics, 85(4), 828–843.",
  "Conley, T. G., & Taber, C. R. (2011). Inference with “difference in differences” with a small number of policy changes. Review of Economics and Statistics, 93(1), 113–125.",
  "Ruhm, C. J. (1996). Alcohol policies and highway vehicle fatalities. Journal of Health Economics, 15(4), 435–454.",
  "Subramanian, R. (2002). Transitioning to multiple imputation: A new method to impute missing blood alcohol concentration (BAC) values in FARS (DOT HS 809 403). NHTSA.",
  "Federal Highway Administration. Highway Statistics, Table VM-2: Functional system travel, 1980–2024.",
  "Federal Reserve Bank of St. Louis. FRED: state unemployment rates (BLS Local Area Unemployment Statistics) and resident population (U.S. Census Bureau), 1982–2024.",
  "National Highway Traffic Safety Administration. Digest of State Alcohol-Highway Safety Related Legislation, 12th ed. (1994); state statutes and regulations as cited in Table 1.",
  "National Highway Traffic Safety Administration. Fatality Analysis Reporting System (FARS), 1982–2024. Files for 1982–2015 accessed through a mirror of NHTSA’s FTP archive, https://github.com/wgetsnaps/ftp.nhtsa.dot.gov--fars.",
  "National Institute on Alcohol Abuse and Alcoholism. Alcohol Policy Information System (APIS): Drink Specials.",
  "Boston.com. (2024, July 11). Happy hour in Massachusetts? Legislature takes big step toward reviving discounted drinks. https://www.boston.com/news/politics/2024/07/11/happy-hour-in-massachusetts-legislature-takes-big-step-toward-reviving-discounted-drinks",
  "Massachusetts High Technology Council. (2026, August). 2025–2026 legislative session wrap-up: Key outcomes and what comes next. https://www.mhtc.org/?p=330188",
  "NBC Boston. (2022). Could happy hour return to Mass.? Senate’s economic development bill includes the option. https://www.nbcboston.com/news/local/could-happy-hour-return-to-mass-senates-economic-development-bill-includes-the-option/2780921/",
  "State House News Service. (2026a, July 22). Mariano spells out threshold for “fun agenda”: 81 votes. https://www.statehousenews.com/news/legislature/house/mariano-spells-out-threshold-for-fun-agenda-81-votes/article_3a0a8770-3ff9-4a53-9ff0-6eaafd720130.html",
  "State House News Service. (2026b, July 24). Senators show they’re up for some of “fun agenda,” but not all of it. https://www.statehousenews.com/news/economy/senators-show-theyre-up-for-some-of-fun-agenda-but-not-all-of-it/article_b2a2c2d1-851a-4c05-978e-e2a73e267af4.html",
].forEach((t) => kids.push(new Paragraph({ spacing: { after: 90 }, indent: { left: 360, hanging: 360 }, children: [new TextRun({ text: t, size: 19 })] })));

// ---------------------------------------------------------------- document
const doc = new Document({
  creator: "Elliot Louis",
  lastModifiedBy: "Elliot Louis",
  title: "Happy Hour Laws and Alcohol-Impaired Traffic Deaths",
  description: "Natural-experiment evidence from FARS crash data, 1982-2024",
  styles: {
    default: { document: { run: { font: "Calibri", size: 22 } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 27, bold: true, color: "1F3864" }, paragraph: { spacing: { before: 300, after: 120 }, outlineLevel: 0, keepNext: true } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 23, bold: true, color: "2E5597" }, paragraph: { spacing: { before: 200, after: 100 }, outlineLevel: 1, keepNext: true } },
    ],
  },
  numbering: { config: [{ reference: "bullets", levels: [{ level: 0, format: LevelFormat.BULLET, text: "\u2022", alignment: AlignmentType.LEFT,
    style: { paragraph: { indent: { left: 540, hanging: 270 } } } }] }] },
  sections: [{
    properties: { page: { size: { width: 12240, height: 15840 }, margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 } } },
    footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER,
      children: [new TextRun({ children: [PageNumber.CURRENT], size: 18, color: "777777" })] })] }) },
    children: kids,
  }],
});
Packer.toBuffer(doc).then((buf) => { fs.writeFileSync(OUTFILE, buf); console.log("wrote", OUTFILE, buf.length); });
