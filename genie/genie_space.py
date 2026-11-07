"""Keep the Genie agent "Gilded Ace floor analyst" in git.

Genie agents have no code; Databricks stores each one as a serialized config (tables,
column settings, instructions, sample questions, example SQL). This script moves that
config between the workspace and `genie/gilded_ace_floor_analyst.json`.

    python genie/genie_space.py export            # workspace -> JSON (run after editing the agent in the UI)
    python genie/genie_space.py create            # JSON -> new agent (fresh workspace / teammate's workspace)
    python genie/genie_space.py update SPACE_ID   # JSON -> overwrite an existing agent

Uses the Databricks CLI (`databricks auth login` first), so no token handling here.
Needs only the Python standard library.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

CONFIG = Path(__file__).with_name("gilded_ace_floor_analyst.json")
TITLE = "Gilded Ace floor analyst"


def api(method: str, path: str, body: dict | None = None) -> dict:
    cmd = ["databricks", "api", method, path]
    if body is not None:
        cmd += ["--json", json.dumps(body)]
    out = subprocess.run(cmd, check=True, capture_output=True, text=True).stdout
    return json.loads(out) if out.strip() else {}


def find_space_id() -> str:
    spaces = api("get", "/api/2.0/genie/spaces").get("spaces", [])
    ids = [s["space_id"] for s in spaces if s.get("title") == TITLE]
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


def export() -> None:
    space_id = find_space_id()
    r = api("get", f"/api/2.0/genie/spaces/{space_id}?include_serialized_space=true")
    doc = {
        "title": r["title"],
        "description": r.get("description", ""),
        "serialized_space": strip_ids(json.loads(r["serialized_space"])),
    }
    CONFIG.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"exported agent {space_id} -> {CONFIG}")


def warehouse_id() -> str:
    whs = api("get", "/api/2.0/sql/warehouses").get("warehouses", [])
    if not whs:
        sys.exit("no SQL warehouse in this workspace")
    return whs[0]["id"]


def body() -> dict:
    doc = json.loads(CONFIG.read_text(encoding="utf-8"))
    return {
        "title": doc["title"],
        "description": doc.get("description", ""),
        "warehouse_id": warehouse_id(),
        "serialized_space": json.dumps(doc["serialized_space"]),
    }


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "export":
        export()
    elif cmd == "create":
        r = api("post", "/api/2.0/genie/spaces", body())
        print(f"created agent {r.get('space_id')}")
    elif cmd == "update" and len(sys.argv) == 3:
        api("patch", f"/api/2.0/genie/spaces/{sys.argv[2]}", body())
        print(f"updated agent {sys.argv[2]}")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
