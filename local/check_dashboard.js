// Parity check: runs the dashboard's in-browser scorecard maths in Node and compares it with the
// pipeline's gold_machine_scorecard (exported in dashboard/data/gilded_ace.json).
// Usage (repo root):  node local/check_dashboard.js
const fs = require("fs"), path = require("path");
const root = path.resolve(__dirname, "..");
const html = fs.readFileSync(path.join(root, "dashboard/app.html"), "utf8");
const js = html.match(/<script>([\s\S]*)<\/script>/)[1].replace('fetch("data/gilded_ace.json")', 'globalThis.__fetch("data/gilded_ace.json")');
const data = JSON.parse(fs.readFileSync(path.join(root, "dashboard/data/gilded_ace.json"), "utf8"));
const el = () => ({ innerHTML: "", style: {}, dataset: {}, addEventListener() {}, querySelector: () => el(), querySelectorAll: () => [], getBoundingClientRect: () => ({ width: 0, height: 0 }), classList: { toggle() {} }, scrollIntoView() {} });
const app = { innerHTML: "" };
Object.assign(global, {
  document: { querySelector: s => (s === "#app" ? app : el()), querySelectorAll: () => [], addEventListener() {}, documentElement: { dataset: {} } },
  getComputedStyle: () => ({ getPropertyValue: () => "" }), matchMedia: () => ({ matches: false }),
  localStorage: { getItem: () => null, setItem() {} }, scrollTo() {}, scrollY: 0, innerWidth: 1200, innerHeight: 800,
  __fetch: () => Promise.resolve({ ok: true, json: () => Promise.resolve(data) }),
});
eval(js + `
;setTimeout(() => {
  const full = computeScorecard(0, NDAYS - 1); let mg = 0, mf = 0; const mm = [];
  full.rows.forEach(s => { const q = D.sqlScore[s.machine_id]; mg = Math.max(mg, Math.abs(q.gap_usd - s.gap_usd)); mf = Math.max(mf, Math.abs(q.fair_index - s.fair_index)); if (q.verdict !== s.verdict) mm.push(s.machine_id + ": sql=" + q.verdict + " js=" + s.verdict); });
  console.log("machines", full.rows.length, "| max gap diff $" + mg.toExponential(1), "| max fair-index diff", mf.toExponential(1), "| verdict mismatches", mm.length);
  mm.forEach(m => console.log("  " + m));
  // Short windows must not raise leak flags on machines that are clean over the full period
  // (one jackpot can push an honest machine's luck z past -3.6 in a week).
  const fullLeaks = new Set(full.rows.filter(s => s.verdict.startsWith("Leak")).map(s => s.machine_id));
  let spurious = 0, windows = 0; const eg = [];
  for (const len of [1, 7, 30]) for (let a = 0; a + len <= NDAYS; a += len) {
    windows++;
    computeScorecard(a, a + len - 1).rows.forEach(s => { if (s.verdict.startsWith("Leak") && !fullLeaks.has(s.machine_id)) { spurious++; if (eg.length < 3) eg.push(s.machine_id + " in " + CAL[a] + " +" + len + "d"); } });
  }
  console.log("short-window leak flags on clean machines", spurious, "over", windows, "windows" + (eg.length ? " e.g. " + eg.join(", ") : ""));
  console.log("dashboard rendered:", app.innerHTML.includes("Luck, location") ? "ok" : "FAILED");
  process.exit(mm.length || mg > 1 || spurious || !app.innerHTML.includes("Luck, location") ? 1 : 0);
}, 50);`);
