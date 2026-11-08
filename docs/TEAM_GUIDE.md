# Team guide: what we built, in plain words

Setup and open tasks are in [../HANDOFF.md](../HANDOFF.md). This guide explains the problem, what we did, why, and what is left. Numbers below come from the pipeline's output tables, so they are what the dashboard shows.

---

## 1. The two challenges we are entering with one project

**Challenge A: Dashboard Royale (The Gilded Ace).** A made-up casino with 300 slot machines. The manager wants to throw out the 10 machines that made the least money from January to June 2025. Our job: build an interactive dashboard that checks whether those machines are really bad, or just **unlucky**, in a **bad spot**, **often broken**, or **paying out wrong** (a "leak"). We also have to say how we would spend a pretend $100,000.

**Challenge B: Databricks.** Build something that uses Databricks well. It can be part of another challenge's solution, so we use Databricks as the engine behind Challenge A.

One codebase, **two Devpost submissions**:

| | Dashboard Royale submission | Databricks submission |
|---|---|---|
| Judges care about | Correct analysis, clear dashboard, a validated model, priced recommendations | Creativity, technical build, how much Databricks improves the solution |
| Main text | [WRITEUP_DASHBOARD_ROYALE.md](WRITEUP_DASHBOARD_ROYALE.md) (≤ 400 words) | [WRITEUP_DATABRICKS.md](WRITEUP_DATABRICKS.md) |
| Also attach | Dashboard link, 2-min video ([script](VIDEO_SCRIPT.md)), [Claims & Evidence](CLAIMS_EVIDENCE.md), [AI disclosure](AI_DISCLOSURE.md), repo link | Repo link, dashboard link, screenshots of the Databricks pipeline graph / MLflow / Genie, short video |

---

## 2. The idea in one picture

A machine can earn little for six different reasons. We measure all six, in dollars, for every machine. The six numbers **add up exactly** to how far the machine is below a typical one.

| Reason | Plain meaning | How we measure it |
|---|---|---|
| **Luck** | Slots are random; a machine can just have a bad run | Actual house win minus *theo* (what the game math says it should win on the money played) |
| **Location** | Some parts of the floor are quiet | How much an average machine in that zone earns vs. the whole floor, same days |
| **Downtime** | Broken machines can't earn | Extra hours down vs. its zone neighbours |
| **Game appeal** | People just don't play it | Money played vs. its zone neighbours |
| **Hold setting** | Some games are set to pay back more (keep less) | Theo lost because its payout setting is more generous than its neighbours' |
| **Time on floor** | It was only installed for part of the period | Days it wasn't on the floor |

Then two statistical checks:
- **Is the bad luck believable?** We know each game's payout variance from the published game math, so we compute a **luck z-score**. Across 310 machines, anything beyond about ±3.6 is too extreme for chance. Only one machine is that extreme. Over short periods (a week, a month) one big jackpot can push an honest machine past −3.6, so the luck test only counts over 150+ days; the **hit-rate test** (how often a spin pays vs. the paytable) works on any period.
- **Is it weak *for its spot*?** The **fair index** compares a machine's theo with what machines in the same zone earned on the same days, per hour it was working. 1.0 = normal for that spot. 0.5 = half.

---

## 3. What we found

**The manager's bottom 10 are the wrong machines to spend on.**
- **2 are already retired** (M-1118, M-1120). You can't replace them again.
- **1 is brand new** (M-5076, on the floor 49 days). It ranks low mostly because it had fewer days (per day it is a low-hold Royal Draw, fair index 0.54).
- **1 looks like a leak** (M-1158). Its paytable says 31.5% of spins should pay, but 38.6% did, over 674,000 spins. Chance can't explain that (z = +124). **Inspect it, don't replace it.** We call it a lead to check, not cheating.
- **6 sit in "Back Forty"**, the quietest corner. Any machine there earns about **$26.7K less** over six months. Proof that it's the location: when the walkway from the main entrance to Back Forty was closed for renovation (Mar 3–Apr 6), play there fell **29%** compared with the rest of the floor, and the door counter fell by the same amount. A new machine in the same spot keeps that part of the gap.
- **Careful, those six are also weak for their spot.** Compared with other Back Forty machines they earn 0.58–0.67 of par (verdict "Weak earner"); three are Royal Draws. But a new title only lifts them to *Back Forty's* par: about **$103/day** of extra theo each, against **$226/day** for a weak machine in a busy zone. So they are real but cheap fixes, and the money goes further elsewhere.

**Where replacement pays.** 67 machines are clearly weak for their spot (23 Royal Draw, 24 Comet Cash, 20 Lucky Lanterns). We pick the 10 where a new title at par gains the most, and they are all **Royal Draw** cabinets set to pay back 95%, so they keep only 5% vs. about 10% for the floor. They sit in busy zones (Center Pit, Main Entrance) and players use them about as much as their neighbours, so the generous setting isn't attracting extra play. **None of them is on the manager's list.** That's the "0 of 10" headline: 0 of the manager's 10 make our *replacement list*, not "all 10 are fine".

**The other five questions:**
- **Demand (Q2):** Back Forty dropped during the walkway closure. Big weekends (Super Bowl, March Madness, EDC) lifted play 16–23%. Our own Winter Slot Tournament lifted it 18% without stealing from the weeks around it. June was the weakest month, when real Las Vegas visitor numbers fell 11% year on year. The 8 new Aurora Link machines (March) earn 1.37× normal for their spot without taking play from neighbours.
- **Downtime (Q3):** about **$102K** of theo lost over six months, only 0.4% of the total. **Ridgeline** machines break 3–4× as often as other brands and cause 55% of it. The night (grave) shift has only one technician, so faults wait about 2 hours. But night hours are worth little, so an extra night tech ($11,520) would recover only about $1K. Not worth it.
- **Players (Q4):** tracked (loyalty-card) play only. The top 5% of players produce 52% of the expected house win. Only 16% of players ended the six months ahead.
- **Comps (Q5):** on **May 1** comps suddenly cost 53% fewer points overnight (12.3 → 5.7 points per dollar of menu value, April 30 → May 1). Measured on Jan–Apr vs. May–Jun averages (13.1 → 5.8), the drop is 56%. Comp spending went up about $78/day with no clear increase in play. It's too early to be sure, so the next step is a controlled pilot.

---

## 4. The model (required by Dashboard Royale)

A simple **forecast of daily floor coin-in** (total money bet per day), based on day of the week.
- Picked using **April only** (trained on Jan–Mar), then **frozen on April 30**, then tested **once** on May–June. That's a fair, time-based test with no peeking.
- Error: **$68.7K/day** vs. **$218K/day** for the required simple baseline (just the average), so 69% better.
- After testing we saw a different model would have scored better. We **did not switch**, because switching after seeing the test results is cheating, and we say so openly.
- **The decision it changes:** the forecast's normal weekend error means one promotion weekend can only prove itself if it lifts play by **11%+**. So we buy **one** promotion weekend, check it against the forecast, and buy a second only if it beats 11%. Honest caveat: our base-case lift (11%, the average of our two promotions) is right at that bar, so one weekend has about even odds of proving a lift that is really there. A result under 11% means "not proven yet", not "failed".

---

## 5. The $100,000 plan (spend $50K, keep $50K)

| Action | Cost | Expected extra house win in July | Why |
|---|---|---|---|
| Inspect M-1158's payout | $1,200 | ~$5.8K | It's the only machine off spec beyond chance |
| Lease new titles for the 10 weak Royal Draws that gain most | $33,800 | ~$36K (range $16K–$66K) | They earn half of normal for their spot; new titles (Aurora Link) earned 1.37× |
| One slot-tournament weekend, Jul 18–20 | $15,000 | ~$49K (range $18K–$80K) | Our tournament lifted play 18% with no borrowed demand |

We also priced the other options. Replacing the manager's 10 would cost ~$27K for ~$12K back. Back Forty signage is the runner-up. An extra night tech and the Ridgeline maintenance sweep both lose money, and the comp pilot is next month's step. Costs follow the catalogue formula exactly, including lead times.

---

## 6. How Databricks fits (what to show the Databricks judges)

```
Challenge files (GitHub) → 01 ingest notebook → Unity Catalog volume (checksums verified)
   → Lakeflow pipeline: bronze (22 raw tables, Auto Loader) → silver (10 cleaned) → gold (20 answer tables)
   → 02 notebook: forecast with MLflow, model registered in Unity Catalog
   → 03 notebook: data-quality log + JSON export → public dashboard
   → Genie space: the manager asks questions in plain English
```

What makes it more than "a notebook on Databricks":
1. **The data-quality rules guard the analysis.** The guide's common mistakes (counting days before install as zero sales, wrong daily ratios, and so on) are written as Lakeflow **expectations**. The pipeline fails if meters don't balance or go negative, if a payout setting is impossible, if a machine-day is duplicated or missing, if our six reasons don't add up, or if the plan breaks the budget rules. `local/stress_test.py` feeds deliberately broken data through the pipeline to prove each rule fires.
2. **Re-runnable.** The data is a draft release (0.9.0). When 1.0.0 lands, one job run redoes everything.
3. **MLflow + Unity Catalog** make the model choice auditable (you can see it was chosen before testing).
4. **Genie** lets a non-technical manager ask follow-up questions.
5. **Same SQL everywhere.** The pipeline's SQL files also run on a laptop with DuckDB, so anyone can verify the numbers without a Databricks account.

---

## 7. What's done vs. what's left

**Done (verified locally and on Databricks Free Edition)**
- Full pipeline (bronze/silver/gold) and all analysis: runs in about 3 s with `python local/run_local.py`
- Forecast with honest validation
- Priced action plan
- Interactive dashboard (`dashboard/`). It recomputes everything in the browser for any date range and matches the pipeline exactly; `node local/check_dashboard.js` proves it.
- Write-ups, claims appendix, AI disclosure draft, video script, Genie setup notes

**Also done**
- Runs on Databricks Free Edition and matches the local numbers (the committed export is the Databricks one)
- Genie agent "Gilded Ace floor analyst" created, tested and kept in git (`genie/`)
- Dashboard published: https://chintan-22.github.io/tamu_databricks/ (redeploys after every successful CI run on `main`)
- CI: `python local/ci.py` and GitHub Actions run every check, including the judge guardrails in `local/judge_check.py`

**Left to do before submitting**

| Task | Notes |
|---|---|
| Add the six Genie sample questions | In the Databricks UI (list in `genie/GENIE_SPACE.md`), then `python genie/genie_space.py export` and commit |
| Screenshots for the Databricks submission | Into `docs/screenshots/`: pipeline graph, expectation results, MLflow runs, registered model, Genie answering a question |
| Record the 2-minute video | Script in `docs/VIDEO_SCRIPT.md`; add the link to both write-ups (the Dashboard Royale write-up has 2 words to spare, so put the link in Devpost's field if it won't fit) |
| Confirm the AI disclosure | `docs/AI_DISCLOSURE.md` lists who did what from the git history; each of us checks our line |
| Submit both Devposts | Checklist in HANDOFF.md §7; test every link in a private window |
| (Optional) AI/BI dashboard inside Databricks | Nice extra for the Databricks judges, built on the same gold tables |

---|---|
| **Run it on Databricks** | Done (branch `databricks-run`): runs end to end on Free Edition and matches the local numbers. To redeploy: install the Databricks CLI, `databricks auth login`, then `databricks bundle deploy -t dev` and `databricks bundle run gilded_ace_job -t dev`. Forecast tables land in `workspace.gilded_ace_ml` (Free Edition caps a schema at 100 tables) |
| Create the Genie space | Follow `genie/GENIE_SPACE.md`; take screenshots |
| Screenshots for the Databricks submission | Pipeline graph, expectation results, MLflow runs, registered model, Genie answering a question |
| Publish the dashboard publicly | GitHub Pages from the `dashboard/` folder; test the link in a private window |
| Record the 2-minute video | Script in `docs/VIDEO_SCRIPT.md` |
| Fix up the AI disclosure | Make it say exactly what each of us did |
| (Optional) AI/BI dashboard inside Databricks | Nice extra for the Databricks judges, built on the same gold tables |

---

## 8. How to run it

```sh
# next to this repo, get the challenge data once
git clone --depth 1 https://github.com/tamu-datathon-org/dashboard-royale.git ../dashboard-royale

python -m venv .venv
.venv\Scripts\pip install -r requirements.txt        # Windows  (macOS/Linux: .venv/bin/pip)
.venv\Scripts\python local\run_local.py              # rebuilds every table + dashboard/data/gilded_ace.json
.venv\Scripts\python local\build_pages.py            # rebuilds dashboard/index.html from dashboard/app.html
node local\check_dashboard.js                        # dashboard maths == pipeline maths
.venv\Scripts\python local\stress_test.py            # re-checks, robustness tests, broken-data guards
cd dashboard && ..\.venv\Scripts\python -m http.server   # open http://localhost:8000
```

Use Python 3.11+. The project was built on 3.14.
