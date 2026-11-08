"""Keep the Genie agent "Gilded Ace floor analyst" in git.

Genie agents have no code; Databricks stores each one as a serialized config (tables,
column settings, instructions, sample questions, example SQL). This script moves that
config between the workspace and `genie/gilded_ace_floor_analyst.json`.

    python genie/genie_space.py export            # workspace -> JSON (run after editing the agent in the UI)
    python genie/genie_space.py create            # JSON -> new agent (fresh workspace / teammate's workspace)
    python genie/genie_space.py update SPACE_ID   # JSON -> overwrite an existing agent

Options: --catalog NAME (default `workspace`, the catalog the JSON is written for),
         --warehouse ID (default: a running SQL warehouse, else a serverless one, else the first).

Uses the Databricks CLI (`databricks auth login` first), so no token handling here.
Needs only the Python standard library.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

CONFIG = Path(__file__).with_name("gilded_ace_floor_analyst.json")
TITLE = "Gilded Ace floor analyst"
JSON_CATALOG = "workspace"  # table identifiers in the JSON use this catalog


def api(method: str, path: str, body: dict | None = None) -> dict:
    cmd = ["databricks", "api", method, path]
    tmp = None
    try:
        if body is not None:
            # Pass the body as a file: the config is tens of KB, and Windows caps a command line at ~32K characters.
            fd, tmp = tempfile.mkstemp(suffix=".json")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(body, f)
            cmd += ["--json", "@" + tmp]
        out = subprocess.run(cmd, check=True, capture_output=True, text=True, encoding="utf-8").stdout
    finally:
        if tmp:
            os.unlink(tmp)
    return json.loads(out) if out.strip() else {}


def find_space_id() -> str:
    ids, token = [], None
    while True:
        r = api("get", "/api/2.0/genie/spaces" + (f"?page_token={token}" if token else ""))
        ids += [s["space_id"] for s in r.get("spaces", []) if s.get("title") == TITLE]
        token = r.get("next_page_token")
        if not token:
            break
    if len(ids) != 1:
        sys.exit(f"expected one agent titled {TITLE!r}, found {len(ids)}; pass its id to `update`")
    return ids[0]


def strip_ids(obj):
    """Drop server-assigned ids so the config can create a new agent."""
    if isinstance(obj, dict):
        return {k: strip_ids(v) for k, v in obj.items() if k != "id"}
    if isinstance(obj, list):
        return [strip_ids(v) for v in obj]
    return obj


def set_catalog(space: dict, old: str, new: str) -> dict:
    for t in space.get("data_sources", {}).get("tables", []):
        if t["identifier"].startswith(old + "."):
            t["identifier"] = new + t["identifier"][len(old):]
    return space


def export(catalog: str) -> None:
    space_id = find_space_id()
    r = api("get", f"/api/2.0/genie/spaces/{space_id}?include_serialized_space=true")
    doc = {
        "title": r["title"],
        "description": r.get("description", ""),
        "serialized_space": set_catalog(strip_ids(json.loads(r["serialized_space"])), catalog, JSON_CATALOG),
    }
    with open(CONFIG, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
    print(f"exported agent {space_id} -> {CONFIG}")


def warehouse_id() -> str:
    whs = api("get", "/api/2.0/sql/warehouses").get("warehouses", [])
    if not whs:
        sys.exit("no SQL warehouse in this workspace")
    whs.sort(key=lambda w: (w.get("state") != "RUNNING", not w.get("enable_serverless_compute", False)))
    return whs[0]["id"]


def body(catalog: str, warehouse: str | None) -> dict:
    doc = json.loads(CONFIG.read_text(encoding="utf-8"))
    return {
        "title": doc["title"],
        "description": doc.get("description", ""),
        "warehouse_id": warehouse or warehouse_id(),
        "serialized_space": json.dumps(set_catalog(doc["serialized_space"], JSON_CATALOG, catalog)),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["export", "create", "update"])
    ap.add_argument("space_id", nargs="?", help="required for update")
    ap.add_argument("--catalog", default=JSON_CATALOG)
    ap.add_argument("--warehouse")
    a = ap.parse_args()
    if a.command == "export":
        export(a.catalog)
    elif a.command == "create":
        r = api("post", "/api/2.0/genie/spaces", body(a.catalog, a.warehouse))
        print(f"created agent {r.get('space_id')}")
    else:
        if not a.space_id:
            ap.error("update needs SPACE_ID")
        api("patch", f"/api/2.0/genie/spaces/{a.space_id}", body(a.catalog, a.warehouse))
        print(f"updated agent {a.space_id}")


if __name__ == "__main__":
    main()
