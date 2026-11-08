"""Hackathon judge guardrails: checks the repo against the Dashboard Royale rules and our own invariants.

It reads what a judge would see (the committed export, the docs, the dashboard source) and checks:
  A. submission package (guide section 8)       E. every quoted number traces to a gold value
  B. the six questions and the judges' 4 tasks   F. wording rules (no accusations, fictional casino)
  C. the $100,000 plan rules                     G. engineering invariants (SQL on Spark + DuckDB,
  D. the forecast protocol (no leakage)             secrets, links, generated files)
  H. (with --fresh) the committed export matches a fresh pipeline run

Usage (repo root):
    python local/judge_check.py [--fresh local/_work/fresh_export.json]

Exits 1 if any FAIL. WARN = a judge would notice, but it does not block a merge. Needs only the
standard library, so it also runs without the challenge data (everything except H).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPORT = ROOT / "dashboard" / "data" / "gilded_ace.json"
APP = ROOT / "dashboard" / "app.html"
DOCS = ROOT / "docs"
WRITEUP = DOCS / "WRITEUP_DASHBOARD_ROYALE.md"
WORD_LIMIT = 400
BUDGET = 100_000
MAX_ACTION_TYPES = 3
FREEZE = "2025-04-30"

results: list[tuple[str, str, str, str]] = []  # (section, level, name, detail)
_section = ""


def section(title: str) -> None:
    global _section
    _section = title
    print(f"\n=== {title} ===")


def report(level: str, name: str, detail: str = "") -> None:
    results.append((_section, level, name, detail))
    print(f"[{level}] {name}" + (f"  {detail}" if detail else ""))


def check(name: str, ok: bool, detail: str = "", warn_only: bool = False) -> bool:
    report("PASS" if ok else ("WARN" if warn_only else "FAIL"), name, detail)
    return ok


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def rel(p: Path) -> str:
    return p.relative_to(ROOT).as_posix()


def tracked_files() -> list[Path]:
    try:
        out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
        return [ROOT / f for f in out.splitlines() if (ROOT / f).is_file()]
    except Exception:
        return [p for p in ROOT.rglob("*") if p.is_file() and ".git" not in p.parts and ".venv" not in p.parts]


def word_count(md: str) -> int:
    """Words in the rendered text, counted strictly: markdown markup (bullets, #, **) is dropped, but
    stand-alone symbols a word counter may count (→, =, —, ×) are kept, so we never under-count."""
    text = re.sub(r"(?m)^\s*(?:[-*+]|\d+\.|#+)\s+", " ", md)  # list bullets and heading marks
    text = re.sub(r"[*#`|>_]", " ", text)
    return len(text.split())


def visible_app_text() -> str:
    """Static copy in the dashboard source (headings, ledes, hard-coded sentences)."""
    html = read(APP)
    html = re.sub(r"<style[\s\S]*?</style>", " ", html)
    return re.sub(r"<[^>]+>", " ", html)


# ---------------------------------------------------------------------------------------------
# A. Submission package (participant guide section 8)
# ---------------------------------------------------------------------------------------------
def submission_package() -> None:
    section("A. submission package (guide section 8)")
    wc = word_count(read(WRITEUP))
    check("write-up is at most 400 words", wc <= WORD_LIMIT, f"{wc} words in {rel(WRITEUP)}")
    if wc <= WORD_LIMIT:
        check("write-up leaves a small margin for Devpost's counter", wc <= WORD_LIMIT - 5,
              f"{WORD_LIMIT - wc} words to spare", warn_only=True)

    idx = ROOT / "dashboard" / "index.html"
    check("standalone dashboard exists", idx.exists() and EXPORT.exists(), "dashboard/index.html + data/gilded_ace.json")
    size_mb = EXPORT.stat().st_size / 1e6 if EXPORT.exists() else 0
    check("dashboard data is small enough to host", size_mb < 50, f"{size_mb:.1f} MB")

    ai = read(DOCS / "AI_DISCLOSURE.md") if (DOCS / "AI_DISCLOSURE.md").exists() else ""
    check("AI-use disclosure names the tool and what it did",
          bool(re.search(r"\btool\b", ai, re.I)) and bool(re.search(r"what it did|used (it )?for", ai, re.I)),
          "docs/AI_DISCLOSURE.md")

    claims_ok = claims_appendix()
    check("Claims & Evidence appendix has the five required columns on every row", claims_ok, "docs/CLAIMS_EVIDENCE.md")

    vs = read(DOCS / "VIDEO_SCRIPT.md") if (DOCS / "VIDEO_SCRIPT.md").exists() else ""
    ends = [int(m) * 60 + int(s) for m, s in re.findall(r"\d+:\d+\s*[–-]\s*(\d+):(\d\d)", vs)]
    check("video script fits in 2:00", bool(ends) and max(ends) <= 120,
          f"ends at {max(ends) // 60}:{max(ends) % 60:02d}" if ends else "no timings found")

    model = ROOT / "src" / "gilded_ace" / "forecast.py"
    check("one ML / time-series method is in the code", model.exists(), rel(model))

    # Links that only exist once task 4/5 are done: a judge must be able to click them.
    for doc in (WRITEUP, DOCS / "WRITEUP_DATABRICKS.md"):
        text = read(doc)
        urls = re.findall(r"https?://[^\s)>\]]+", text)
        check(f"{doc.name} links a public dashboard", any("github.io" in u or "dashboard" in u.lower() for u in urls),
              "add the GitHub Pages link before submitting", warn_only=True)
        check(f"{doc.name} links the video", any(re.search(r"youtu|vimeo|loom|drive\.google", u) for u in urls),
              "add the video link before submitting", warn_only=True)


def claims_appendix() -> bool:
    text = read(DOCS / "CLAIMS_EVIDENCE.md")
    rows = [r for r in text.splitlines() if r.startswith("|")]
    if len(rows) < 3:
        return False
    header = [c.strip().lower() for c in re.split(r"(?<!\\)\|", rows[0])[1:-1]]
    need = ["claim", "table", "result", "alternative", "limitation"]
    if not all(any(n in h for h in header) for n in need):
        return False
    ok = True
    alt_col = next(i for i, h in enumerate(header) if "alternative" in h)
    tables = defined_tables()
    for r in rows[2:]:
        cells = [c.strip() for c in re.split(r"(?<!\\)\|", r)[1:-1]]
        if len(cells) != len(header) or any(not c for c in cells):
            report("FAIL", f"claims row malformed: {cells[:2]}")
            ok = False
            continue
        if cells[alt_col] in ("—", "-", "–"):
            report("WARN", f"claim {cells[0]} has no alternative explanation", cells[1][:60])
        for t in re.findall(r"`((?:gold|silver|bronze)_\w+)", r):
            if t not in tables:
                report("FAIL", f"claim {cells[0]} cites a table that does not exist", t)
                ok = False
        for f in re.findall(r"`((?:local|src|dashboard|genie)/[\w./-]+)`", r):
            if not (ROOT / f).exists():
                report("FAIL", f"claim {cells[0]} cites a missing file", f)
                ok = False
    return ok


def defined_tables() -> set[str]:
    names: set[str] = set()
    for p in (ROOT / "src").rglob("*"):
        if p.suffix in (".sql", ".py"):
            t = read(p)
            names |= set(re.findall(r"(?:MATERIALIZED VIEW|STREAMING TABLE|TABLE|VIEW)\s+(?:IF NOT EXISTS\s+)?(\w+)", t, re.I))
            names |= set(re.findall(r"""["'`]((?:gold|silver|bronze)_\w+)["'`]""", t))
            names |= set(re.findall(r"def ((?:gold|silver|bronze)_\w+)\(", t))
    return names


# ---------------------------------------------------------------------------------------------
# B. The six questions and the four things judges do with every dashboard
# ---------------------------------------------------------------------------------------------
def questions_and_judge_tasks() -> None:
    section("B. six questions + the judges' four tasks")
    html = read(APP)
    for n in range(1, 7):
        check(f"dashboard answers question {n}", f"Question {n} ·" in html)
    check("judge task 1: change the analysis period", all(s in html for s in ('id="p-start"', 'id="p-end"')),
          "period start/end controls")
    check("judge task 2a: drill into one bank", 'id="f-bank"' in html)
    check("judge task 2b: drill into one guest group", all(s in html for s in ("opening_tier", "age_band", "home_region")))
    check("judge task 3: model validation is visible", 'id="model"' in html and re.search(r"holdout|baseline", html, re.I) is not None)
    check("judge task 4: each recommendation shows evidence, assumption and measurement",
          all(f".{k}" in html for k in ("evidence", "assumption", "measurement")))
    svgs = re.findall(r"<svg[^>]*>", html)
    unlabeled = [s for s in svgs if "aria-label" not in s and "aria-hidden" not in s]
    check("charts are labelled for screen readers", not unlabeled, f"{len(svgs) - len(unlabeled)}/{len(svgs)} svg tags labelled")
    check("dashboard states the casino is fictional", "fictional" in html.lower())
    ext = re.findall(r"<script[^>]+src=[\"']https?://", html)
    check("dashboard runs without external scripts", not ext, "judges may open it offline")


# ---------------------------------------------------------------------------------------------
# C. The $100,000 plan
# ---------------------------------------------------------------------------------------------
def plan_rules(d: dict) -> None:
    section("C. $100,000 plan rules")
    cat = {r["action_type_id"]: r for r in d["action_catalog"]}
    opts = d["action_options"]
    rec = [o for o in opts if o["recommended"]]
    types = {o["action_type_id"].split(" ")[0] for o in rec}
    total = sum(o["cost_usd"] for o in rec)
    check("at most 3 action types funded", len(types) <= MAX_ACTION_TYPES, f"{len(types)}: {', '.join(sorted(types))}")
    check("total cost within $100,000", total <= BUDGET, f"${total:,.0f}")
    worst = 0.0
    for o in opts:
        c = cat.get(o["action_type_id"].split(" ")[0])
        if c is None:
            report("FAIL", "option is not in the action catalogue", o["action_type_id"])
            continue
        expect = o["quantity"] * (c["unit_cost_cents"] + c["recurring_cost_cents_per_day"] * max(0, 30 - c["lead_days"])) / 100
        worst = max(worst, abs(expect - o["cost_usd"]))
        if o["recommended"]:
            check(f"{o['action_type_id']}: quantity within limit", o["quantity"] <= c["quantity_limit"],
                  f"{o['quantity']} of {c['quantity_limit']}")
            lo, base, hi = o["benefit_low_usd"], o["benefit_base_usd"], o["benefit_high_usd"]
            check(f"{o['action_type_id']}: has a range (low <= base <= high)", lo <= base <= hi and hi > lo,
                  f"${lo:,.0f} / ${base:,.0f} / ${hi:,.0f}")
            for k in ("evidence", "assumption", "measurement", "targets"):
                check(f"{o['action_type_id']}: states its {k}", bool(str(o.get(k) or "").strip()))
            check(f"{o['action_type_id']}: lead time leaves days to act in July", o["lead_days"] < 30, f"{o['lead_days']} lead days")
    check("catalogue cost formula holds on every option", worst < 0.01, f"max diff ${worst:.4f}")
    groups = [cat[t]["incompatibility_group"] for t in types if cat[t].get("incompatibility_group")]
    check("no two funded actions share an incompatibility group", len(groups) == len(set(groups)), str(groups or "none"))
    targets = {}
    for o in rec:
        for m in re.findall(r"M-\d+", str(o.get("targets") or "")):
            targets.setdefault(m, []).append(o["action_type_id"])
    clash = {m: a for m, a in targets.items() if len(a) > 1}
    check("no machine gets two conflicting actions", not clash, str(clash or ""))
    plan = d["action_plan"][0]
    check("plan totals equal the sum of funded rows",
          abs(plan["total_cost_usd"] - total) < 0.01 and plan["action_types"] == len(types)
          and abs(plan["budget_kept_usd"] - (BUDGET - total)) < 0.01,
          f"cost ${plan['total_cost_usd']:,.0f}, kept ${plan['budget_kept_usd']:,.0f}")
    mgr = [o for o in opts if "manager" in o["action_type_id"]]
    check("the manager's own list is priced as a comparison", bool(mgr), "lets judges see the counterfactual")
    sc = {r["machine_id"]: r for r in d["scorecard"]}
    bad = [m for m, a in targets.items() if "A-REPLACE-LEASE" in a and sc.get(m, {}).get("verdict", "").startswith(("Unlucky", "Leak", "Already", "New install"))]
    check("nothing replaced that is only unlucky, retired, new or a leak lead", not bad, ", ".join(bad))


# ---------------------------------------------------------------------------------------------
# D. Forecast protocol
# ---------------------------------------------------------------------------------------------
def forecast_protocol(d: dict) -> None:
    section("D. forecast protocol (time split, no leakage)")
    p = d["forecast_params"][0]
    check("forecast frozen on 2025-04-30", p["freeze_date"] == FREEZE, p["freeze_date"])
    sel = d["forecast_selection"]
    best = min(sel, key=lambda r: r["mae"])["model"]
    check("chosen model = lowest April-validation MAE", best == p["chosen_model"], f"chosen {p['chosen_model']}, best on April {best}")
    rows = [r for r in d["forecast"] if r["model"] == p["chosen_model"]]
    hold = [r for r in rows if "holdout" in str(r["split"]).lower()]
    train = [r for r in rows if r not in hold]
    check("every holdout day is after the freeze", bool(hold) and min(r["gaming_date"] for r in hold) > FREEZE,
          f"{len(hold)} days from {min(r['gaming_date'] for r in hold) if hold else '-'}")
    in_window = [r for r in train if r["gaming_date"] <= "2025-06-30"]
    check("no training/validation day is in the holdout", all(r["gaming_date"] <= FREEZE for r in in_window),
          f"{len(in_window)} pre-freeze days")
    if hold:
        mae = sum(abs(r["actual_coin_in_usd"] - r["model_coin_in_usd"]) for r in hold) / len(hold)
        base = sum(abs(r["actual_coin_in_usd"] - r["baseline_coin_in_usd"]) for r in hold) / len(hold)
        check("holdout MAE recomputes from the daily rows", abs(mae - p["holdout_mae_model"]) < 1, f"${mae:,.0f}")
        check("baseline MAE recomputes from the daily rows", abs(base - p["holdout_mae_baseline"]) < 1, f"${base:,.0f}")
        bases = {round(r["baseline_coin_in_usd"], 2) for r in hold}
        check("baseline is a constant (training-period mean)", len(bases) == 1, f"{len(bases)} distinct values")
        cover = sum(r["lower_80_usd"] <= r["actual_coin_in_usd"] <= r["upper_80_usd"] for r in hold) / len(hold)
        check("80% band is honest on the holdout (65-95% coverage)", 0.65 <= cover <= 0.95, f"{cover:.0%}")
    posthoc = [m for m in d["forecast_metrics"] if "post-hoc" in m["period"]]
    check("post-hoc variants are labelled as not used to choose", all("not used" in m["period"] for m in posthoc),
          f"{len(posthoc)} post-hoc rows")


# ---------------------------------------------------------------------------------------------
# E. Every number we quote traces to a gold value
# ---------------------------------------------------------------------------------------------
def gold_facts(d: dict) -> list[tuple[str, list[float], str, str]]:
    """(name, accepted values, regex with one group capturing the quoted number, unit)
    unit: "usd", "k" (thousands), "pct" (fraction shown as %), "x" (plain number)."""
    sc = {r["machine_id"]: r for r in d["scorecard"]}
    opt = {o["action_type_id"]: o for o in d["action_options"]}
    fp = d["forecast_params"][0]
    plan = d["action_plan"][0]
    m1158 = sc["M-1158"]
    pc = d["player_concentration"]
    top = {r["band"].split(".")[0]: r for r in pc}
    ahead = sum(r["players"] * r["share_ahead"] for r in pc) / sum(r["players"] for r in pc)
    dt_total = sum(r["lost_theo_usd"] for r in d["downtime_lost"])
    by_mfr: dict[str, float] = {}
    for r in d["downtime_lost"]:
        by_mfr[r["manufacturer"]] = by_mfr.get(r["manufacturer"], 0) + r["lost_theo_usd"]
    floor_theo = sum(r["theo_usd"] for r in d["floor_day"])
    cct = {r["period"]: r for r in d["comp_change_test"]}
    cpd = {r["gaming_date"]: r for r in d["comp_price_day"]}
    step = 1 - cpd["2025-05-01"]["points_per_face_dollar"] / cpd["2025-04-30"]["points_per_face_dollar"]
    avg = 1 - cct["after"]["points_per_face_dollar"] / cct["before"]["points_per_face_dollar"]
    gain = lambda r: r["theo_usd"] / r["days_on_floor"] * (1 / r["fair_index"] - 1)
    mgr_weak = [r for r in d["scorecard"] if r["manager_rank"] and r["manager_rank"] <= 10 and r["verdict"].startswith("Weak")]
    lease = opt["A-REPLACE-LEASE"]
    lease_t = [sc[m] for m in re.findall(r"M-\d+", lease["targets"])]
    mgr = next(o for o in d["action_options"] if "manager" in o["action_type_id"])
    exp_bf = next(e for e in d["experiments"] if "walkway" in e["experiment"].lower())
    tourn = next(e for e in d["event_lift"] if "Tournament" in e["name"])
    aurora = [r for r in d["scorecard"] if "Aurora" in str(r["theme"])]
    hold_m = next(m for m in d["forecast_metrics"] if m["model"] == fp["chosen_model"] and m["period"].startswith("holdout"))
    promo, insp = opt["A-PROMO"], opt["A-INSPECT"]
    N = r"(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    return [
        ("forecast holdout MAE", [fp["holdout_mae_model"]], rf"MAE \${N}K", "k"),
        ("forecast holdout MAE (video)", [fp["holdout_mae_model"]], rf"\${N}K error", "k"),
        ("forecast holdout MAPE", [fp["holdout_mape_model"]], rf"\$[\d.]+K \({N}%\) vs", "pct"),
        ("baseline holdout MAE", [fp["holdout_mae_baseline"]], rf"\${N}K for the (?:constant )?baseline", "k"),
        ("baseline holdout MAE (claims)", [fp["holdout_mae_baseline"]], rf"\(5\.0%\) vs \${N}K", "k"),
        ("forecast bias", [hold_m["bias"]], rf"bias \+\${N}K", "k"),
        ("smallest provable promo lift", [fp["min_detectable_promo_lift"]], rf"lift of {N}%", "pct"),
        ("smallest provable promo lift (claims)", [fp["min_detectable_promo_lift"]], rf"detectable lift \({N}%\)", "pct"),
        ("M-1158 hit rate", [m1158["observed_hit_rate"]], rf"{N}% (?:of spins )?(?:against|vs\.?) (?:a )?[\d.]+% spec", "pct"),
        ("M-1158 spec hit rate", [m1158["spec_hit_probability"]], rf"[\d.]+% (?:of spins )?(?:against|vs\.?) (?:a )?{N}% spec", "pct"),
        ("M-1158 hit-rate z", [m1158["hit_rate_z"]], r"z (?:= \+|of )(\d{3})\b", "x"),
        ("M-1158 spins", [m1158["paid_spins"]], rf"over {N} spins", "x"),
        ("M-5076 days on floor", [sc["M-5076"]["days_on_floor"]], r"(\d+)-day-old install", "x"),
        ("Back Forty location drag", [-sc["M-1238"]["location_usd"]], rf"earns \${N}K less", "k"),
        ("Back Forty location drag (claims)", [-sc["M-1238"]["location_usd"]], rf"−\${N}K per Back Forty machine", "k"),
        ("walkway closure effect", [-exp_bf["did_effect"]], rf"cut play there {N}%", "pct"),
        ("walkway closure effect (claims)", [-exp_bf["did_effect"]], rf"−{N}% coin-in", "pct"),
        ("new title gain in Back Forty", [sum(map(gain, mgr_weak)) / len(mgr_weak)], rf"(?:adds|about) \*?\*?(?:≈ )?\${N}/day(?:\*\*)? (?:of (?:extra )?theo)", "usd"),
        ("new title gain in Back Forty (claims)", [sum(map(gain, mgr_weak)) / len(mgr_weak)], rf"adds ≈ \${N}/day", "usd"),
        ("new title gain in busy zones (guide)", [sum(map(gain, lease_t)) / len(lease_t)], rf"against \*\*\${N}/day\*\*", "usd"),
        ("extra comp spend per day", [cct["after"]["comp_cost_per_day"] - cct["before"]["comp_cost_per_day"]], rf"went up about \${N}/day", "usd"),
        ("new title gain in busy zones", [sum(map(gain, lease_t)) / len(lease_t)], rf"vs \${N} in busy zones", "usd"),
        ("new title gain in busy zones (claims)", [sum(map(gain, lease_t)) / len(lease_t)], rf"≈ \${N}/day for our ten", "usd"),
        ("downtime theo lost", [dt_total], rf"[Dd]owntime cost \${N}K", "k"),
        ("downtime theo lost (claims)", [dt_total], rf"\${N} theo; Ridgeline", "usd"),
        ("downtime share of theo", [dt_total / floor_theo], rf"of theo \({N}%\)", "pct"),
        ("Ridgeline share of downtime", [by_mfr.get("Ridgeline", 0) / dt_total], rf"{N}% of it", "pct"),
        ("Ridgeline downtime (claims)", [by_mfr.get("Ridgeline", 0)], rf"Ridgeline \${N}K", "k"),
        ("top 5% share of theo", [top["1"]["share_of_theo"] + top["2"]["share_of_theo"]], rf"top 5% (?:of players generate |= ){N}%", "pct"),
        ("top 1% share of theo", [top["1"]["share_of_theo"]], rf"[Tt]op 1% = {N}%", "pct"),
        ("players who finished ahead", [ahead], rf"{N}% of players finished ahead", "pct"),
        # 53% = the overnight step (Apr 30 -> May 1); 56% = Jan-Apr vs May-Jun averages. Each number must
        # be quoted with its own definition.
        ("comp price drop, overnight Apr 30 → May 1", [step], rf"(?i)comps (?:got|suddenly cost) {N}% (?:cheaper|fewer points)", "pct"),
        ("comp price drop, overnight Apr 30 → May 1 (claims)", [step], rf"(?:Apr 30 → May 1\), a |step is |{N}% is the overnight step)(?:{N}%)?", "pct"),
        ("comp price drop, period averages", [avg], rf"(?:{N}% on Jan–Apr vs\. May–Jun averages|averages \([\d.]+ → [\d.]+(?:, first tile)?\),? the drop is {N}%)", "pct"),
        ("points per comp dollar, Jan–Apr average", [cct["before"]["points_per_face_dollar"]], rf"averages \({N} → [\d.]+", "x"),
        ("points per comp dollar, May–Jun average", [cct["after"]["points_per_face_dollar"]], rf"averages \([\d.]+ → {N}", "x"),
        ("points per comp dollar before", [cpd["2025-04-30"]["points_per_face_dollar"]], rf"{N} → [\d.]+ points per", "x"),
        ("points per comp dollar after", [cpd["2025-05-01"]["points_per_face_dollar"]], rf"[\d.]+ → {N} points per", "x"),
        ("comp reinvestment before", [cct["before"]["comp_reinvestment"]], rf"reinvestment rose {N}% →", "pct"),
        ("comp reinvestment after", [cct["after"]["comp_reinvestment"]], rf"reinvestment rose [\d.]+% → {N}%", "pct"),
        ("tournament lift", [tourn["lift"]], rf"Winter Slot Tournament \+{N}%", "pct"),
        ("Aurora Link fair index", [sum(r["fair_index"] for r in aurora) / max(1, len(aurora))], rf"Aurora Link[^.|]*?{N}× (?:par|normal)", "x"),
        ("plan spend", [plan["total_cost_usd"]], rf"\${N} spent", "usd"),
        ("plan kept", [plan["budget_kept_usd"]], rf"\${N} kept", "usd"),
        ("plan spend (video)", [plan["total_cost_usd"]], rf"spend \${N} and keep", "usd"),
        ("inspection cost", [insp["cost_usd"]], rf"Inspect M-1158(?::| for) \${N}", "usd"),
        ("inspection benefit", [insp["benefit_base_usd"]], rf"Inspect M-1158: \$[\d,]+, expected \${N}K", "k"),
        ("lease cost", [lease["cost_usd"]], rf"10 Royal Draws that gain most(?::|,)? (?:for )?\${N}", "usd"),
        ("lease benefit", [lease["benefit_base_usd"]], rf"gain most[^\n]*?expected \${N}K", "k"),
        ("lease benefit low", [lease["benefit_low_usd"]], rf"gain most[^\n]*?expected \$[\d.]+K \(\${N}K", "k"),
        ("lease benefit high", [lease["benefit_high_usd"]], rf"gain most[^\n]*?expected \$[\d.]+K \(\$[\d.]+K–\${N}K", "k"),
        ("promotion cost", [promo["cost_usd"]], rf"weekend(?:, Jul \d+–\d+)?(?::| for) \${N}", "usd"),
        ("promotion benefit", [promo["benefit_base_usd"]], rf"weekend[^\n]*?expected \${N}K", "k"),
        ("promotion benefit low", [promo["benefit_low_usd"]], rf"weekend[^\n]*?expected \$[\d.]+K \(\${N}K", "k"),
        ("promotion benefit high", [promo["benefit_high_usd"]], rf"weekend[^\n]*?expected \$[\d.]+K \(\$[\d.]+K–\${N}K", "k"),
        ("manager list cost", [mgr["cost_usd"]], rf"own list would cost \${N}K", "k"),
        ("manager list return", [mgr["benefit_base_usd"]], rf"return about \${N}K", "k"),
    ]


def matches_quote(quoted: str, values: list[float], unit: str) -> tuple[bool, str]:
    q = float(quoted.replace(",", ""))
    scale = {"k": 1000, "pct": 0.01}.get(unit, 1)
    decimals = len(quoted.split(".")[1]) if "." in quoted else 0
    shown = []
    for v in values:
        x = abs(v) / scale
        if decimals == 0 and "," in quoted or (decimals == 0 and quoted.endswith("000")):
            zeros = len(quoted.replace(",", "")) - len(quoted.replace(",", "").rstrip("0"))
            r = round(x, -zeros) if zeros else round(x)
        else:
            r = round(x, decimals)
        shown.append(f"{r:,.{decimals}f}")
        if abs(r - q) < 1e-9:
            return True, ""
    return False, " or ".join(shown)


def traceability(d: dict) -> None:
    section("E. quoted numbers trace to gold values")
    sources = {p: read(p) for p in sorted(DOCS.glob("*.md"))}
    sources[APP] = visible_app_text()
    sources[ROOT / "README.md"] = read(ROOT / "README.md")
    covered: dict[Path, list[tuple[int, int]]] = {p: [] for p in sources}
    for name, values, pattern, unit in gold_facts(d):
        hits, bad = 0, []
        for p, text in sources.items():
            for m in re.finditer(pattern, text):
                g = next((i for i in range(1, (m.re.groups or 0) + 1) if m.group(i)), None)
                if g is None:
                    continue
                hits += 1
                covered[p].append(m.span(g))
                ok, want = matches_quote(m.group(g), values, unit)
                if not ok:
                    bad.append(f"{rel(p)} says {m.group(g)}, gold gives {want}")
        if hits == 0:
            report("WARN", f"{name}: not quoted anywhere (pattern may need updating)")
        else:
            check(f"{name}", not bad, "; ".join(bad) if bad else f"{hits} quote(s) match")
    # Numbers in the write-up that no fact covers: not wrong, but nobody has traced them.
    text = sources[WRITEUP]
    loose = []
    for m in re.finditer(r"\$[\d,.]+K?|\b\d+(?:\.\d+)?%", text):
        if not any(a <= m.start() + 1 < b or m.start() <= a < m.end() for a, b in covered[WRITEUP]):
            loose.append(m.group(0))
    report("INFO", "write-up numbers without an automatic trace", ", ".join(loose) if loose else "none")


# ---------------------------------------------------------------------------------------------
# F. Wording rules
# ---------------------------------------------------------------------------------------------
ACCUSE = re.compile(r"\b(cheat\w*|fraud\w*|theft|thie[fv]\w*|steal\w*|stole\w*|rigg(?:ed|ing)|tamper\w*|crimin\w*|embezzl\w*|scam\w*|skim\w*|collu\w*)\b", re.I)
NEGATE = re.compile(r"\b(not|never|no|without|nor|rather than|instead of|isn't|aren't|don't|doesn't|cannot|can't)\b|n't\b", re.I)
HARM = re.compile(r"\b(heav(?:y|ier|iest)|big(?:gest)?|frequent|problem)\s+(losers?|losing players|gamblers)\b", re.I)
PROTECT = re.compile(r"\b(protect\w*|limit\w*|responsib\w*|cool(?:ing)?[- ]off|self-exclu\w*|not|never|no|nothing)\b", re.I)
REAL_CASINOS = re.compile(r"\b(Bellagio|Caesars Palace|MGM Grand|Wynn|Venetian|Aria|Mandalay Bay|Cosmopolitan|Treasure Island|Harrah'?s|Ameristar|Argosy)\b")


def sentences(text: str):
    for line in text.splitlines():
        for s in re.split(r"(?<=[.!?])\s+|\s\|\s", line):
            if s.strip():
                yield s


def wording(d: dict) -> None:
    section("F. wording rules (fictional casino, no accusations, protect players)")
    files = sorted(DOCS.glob("*.md")) + [ROOT / "README.md", ROOT / "genie" / "GENIE_SPACE.md"]
    texts = {rel(p): read(p) for p in files if p.exists()}
    texts["dashboard/app.html"] = visible_app_text()
    texts["export: action text"] = "\n".join(f"{o.get('evidence', '')}. {o.get('assumption', '')}. {o.get('measurement', '')}." for o in d["action_options"])
    texts["export: verdicts"] = "\n".join(sorted({r["verdict"] + "." for r in d["scorecard"]}))
    accuse, harm, real = [], [], []
    for name, text in texts.items():
        for s in sentences(text):
            if ACCUSE.search(s) and not NEGATE.search(s):
                accuse.append(f"{name}: “{s.strip()[:110]}”")
            if HARM.search(s) and not PROTECT.search(s):
                harm.append(f"{name}: “{s.strip()[:110]}”")
            if REAL_CASINOS.search(s):
                real.append(f"{name}: {REAL_CASINOS.search(s).group(0)}")
    check("no accusatory wording (unusual payouts are leads to inspect)", not accuse, "\n      ".join([""] + accuse) if accuse else "")
    check("no idea pushes heavy losers to gamble more", not harm, "\n      ".join([""] + harm) if harm else "")
    check("no real casino named as our property", not real, "; ".join(real))
    lead = [v for v in {r["verdict"] for r in d["scorecard"]} if re.search(r"leak", v, re.I)]
    check("payout verdicts are phrased as an inspection", all(re.search(r"inspect|\?", v, re.I) for v in lead), ", ".join(lead))
    wu = read(WRITEUP)
    check("write-up says unusual payouts are inspected, not accused", re.search(r"inspect", wu, re.I) is not None)
    check("README states the casino is fictional", "fictional" in texts.get("README.md", "").lower(), warn_only=True)


# ---------------------------------------------------------------------------------------------
# G. Engineering invariants
# ---------------------------------------------------------------------------------------------
def sql_code(text: str) -> tuple[str, list[str]]:
    """Strip comments; return code outside strings and a list of problems inside string literals."""
    out, problems, i, n = [], [], 0, len(text)
    while i < n:
        c = text[i]
        if text.startswith("--", i):
            i = text.find("\n", i)
            i = n if i < 0 else i
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            i = n if j < 0 else j + 2
        elif c == "'":
            j = i + 1
            while j < n:
                if text[j] == "'" and j + 1 < n and text[j + 1] == "'":
                    if j == i + 1:  # '' : the empty string literal, fine
                        break
                    line = text.count("\n", 0, j) + 1
                    problems.append(f"line {line}: '' inside a string (Spark drops the quote; use ’)")
                    j += 2
                    continue
                if text[j] == "'":
                    break
                j += 1
            out.append("''")
            i = j + 1
        else:
            out.append(c)
            i += 1
    return "".join(out), problems


def engineering() -> None:
    section("G. engineering invariants")
    sql_files = sorted((ROOT / "src" / "pipeline").glob("*.sql"))
    for p in sql_files:
        code, problems = sql_code(read(p))
        if re.search(r"\b(percentile_approx|approx_percentile)\b", code, re.I):
            problems.append("PERCENTILE_APPROX disagrees between Spark and DuckDB; use PERCENTILE")
        if "::" in code:
            problems.append(":: cast is not Spark SQL; use CAST(x AS type)")
        for m in re.finditer(r"\bCAST\s*\(\s*ROUND\s*\((?:(?!\bAS\b)[^;])*?\)\s+AS\s+STRING\s*\)", code, re.I):
            problems.append("ROUND(...) cast straight to STRING writes 29.0 on DuckDB; cast to INT first")
        check(f"{rel(p)} runs on Spark and DuckDB", not problems, "; ".join(problems))
    pipe = read(ROOT / "resources" / "gilded_ace.pipeline.yml")
    run_local = read(ROOT / "local" / "run_local.py") + read(ROOT / "local" / "lakeflow_duckdb.py") + read(ROOT / "src" / "gilded_ace" / "tables.py")
    for p in sql_files:
        check(f"{p.name} is in the Databricks pipeline", p.name in pipe)
        check(f"{p.name} is run locally", p.name in run_local or "*.sql" in run_local or "glob(" in run_local, warn_only=True)

    bad_py = []
    for p in tracked_files():
        if p.suffix == ".py":
            try:
                compile(p.read_text(encoding="utf-8"), str(p), "exec")
            except SyntaxError as e:
                bad_py.append(f"{rel(p)}:{e.lineno}: {e.msg}")
    check("every Python file compiles", not bad_py, "; ".join(bad_py))

    secret = re.compile(r"(dapi[0-9a-f]{32}|sk-ant-[\w-]{20,}|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{36}|github_pat_\w{40,}|xox[bp]-[\w-]{10,}|-----BEGIN [A-Z ]*PRIVATE KEY-----)")
    leaks, risky = [], []
    for p in tracked_files():
        name = rel(p)
        if re.search(r"(^|/)(\.env|\.databrickscfg|.*\.pem|credentials.*)$", name):
            risky.append(name)
        if p.stat().st_size > 5_000_000:
            continue
        try:
            t = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for m in secret.finditer(t):
            leaks.append(f"{name}: {m.group(0)[:8]}…")
    check("no secrets or tokens committed", not leaks and not risky, "; ".join(leaks + risky))

    broken = []
    for p in [ROOT / "README.md", ROOT / "HANDOFF.md", ROOT / "CLAUDE.md"] + sorted(DOCS.glob("*.md")) + sorted((ROOT / "genie").glob("*.md")):
        for target in re.findall(r"\]\(([^)#\s]+)(?:#[^)]*)?\)", read(p)):
            if re.match(r"(https?|mailto):", target):
                continue
            if not (p.parent / target).resolve().exists():
                broken.append(f"{rel(p)} -> {target}")
    check("relative links in the docs resolve", not broken, "; ".join(broken))

    idx = ROOT / "dashboard" / "index.html"
    before = idx.read_bytes() if idx.exists() else b""
    subprocess.run([sys.executable, str(ROOT / "local" / "build_pages.py")], cwd=ROOT, capture_output=True)
    after = idx.read_bytes() if idx.exists() else b""
    check("dashboard/index.html is rebuilt from app.html", before == after,
          "" if before == after else "it was stale; build_pages.py just rebuilt it: commit dashboard/index.html")


# ---------------------------------------------------------------------------------------------
# H. Committed export vs a fresh run
# ---------------------------------------------------------------------------------------------
IGNORE_KEYS = {"_rescued_data", "_source_file", "_ingested_at", "generated_at"}


def norm(x):
    if isinstance(x, dict):
        return {k: norm(v) for k, v in x.items() if k not in IGNORE_KEYS}
    if isinstance(x, list):
        x = [norm(v) for v in x]
        if x and all(isinstance(v, dict) for v in x):
            def key(r):
                ident = {k: v for k, v in r.items() if isinstance(v, str) or isinstance(v, bool) or v is None}
                nums = {k: round(float(v), 3) for k, v in r.items() if isinstance(v, (int, float)) and not isinstance(v, bool)}
                return json.dumps(ident, sort_keys=True, default=str) + json.dumps(nums, sort_keys=True)
            x.sort(key=key)
        return x
    if isinstance(x, str) and re.fullmatch(r"(M-\d+)(, M-\d+)+", x):
        return ", ".join(sorted(x.split(", ")))  # target lists: order is not meaningful
    if isinstance(x, int) and not isinstance(x, bool):
        return float(x)
    return x


def diff(a, b, path="", out=None):
    out = [] if out is None else out
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                out.append(f"{path}/{k}: only in {'fresh' if k in b else 'committed'}")
            else:
                diff(a[k], b[k], f"{path}/{k}", out)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            out.append(f"{path}: {len(a)} rows committed vs {len(b)} fresh")
        else:
            for i, (u, v) in enumerate(zip(a, b)):
                diff(u, v, f"{path}[{i}]", out)
    elif isinstance(a, float) and isinstance(b, float):
        if abs(a - b) / max(1.0, abs(a), abs(b)) > 1e-5:
            out.append(f"{path}: {a} committed vs {b} fresh")
    elif a != b:
        out.append(f"{path}: {str(a)[:50]!r} committed vs {str(b)[:50]!r} fresh")
    return out


def export_matches(committed: dict, fresh_path: Path) -> None:
    section("H. committed export matches a fresh pipeline run")
    fresh = json.loads(fresh_path.read_text(encoding="utf-8"))
    problems = diff(norm(committed), norm(fresh))
    tables = sorted({p.split("/")[1].split("[")[0] for p in problems})
    check("dashboard/data/gilded_ace.json matches the current pipeline", not problems,
          f"{len(problems)} differences in: {', '.join(tables)} (e.g. {problems[0]})" if problems else "same numbers to 1e-5")


# ---------------------------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fresh", help="export written by a fresh run_local.py, compared with the committed one")
    args = ap.parse_args()
    d = json.loads(EXPORT.read_text(encoding="utf-8"))

    for step in (submission_package, questions_and_judge_tasks, lambda: plan_rules(d), lambda: forecast_protocol(d),
                 lambda: traceability(d), lambda: wording(d), engineering):
        try:
            step()
        except Exception as e:  # a crash in one section must not hide the others
            report("FAIL", f"check crashed: {type(e).__name__}", str(e)[:200])
    if args.fresh:
        export_matches(d, Path(args.fresh))

    n = {lvl: sum(1 for r in results if r[1] == lvl) for lvl in ("PASS", "WARN", "FAIL")}
    print(f"\njudge: {n['PASS']} passed, {n['WARN']} warnings, {n['FAIL']} failed")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(f"### Judge guardrails: {n['PASS']} passed, {n['WARN']} warnings, {n['FAIL']} failed\n\n")
            for sec, lvl, name, detail in results:
                if lvl in ("FAIL", "WARN"):
                    f.write(f"- {'❌' if lvl == 'FAIL' else '⚠️'} **{sec.split('.')[0]}.** {name} {('— ' + detail.strip()) if detail else ''}\n")
            f.write("\n")
    return 1 if n["FAIL"] else 0


if __name__ == "__main__":
    sys.exit(main())
