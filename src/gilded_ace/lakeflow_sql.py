"""Parse the small subset of Lakeflow (DLT) SQL this project uses.

Shared by the local DuckDB runner and the Databricks export notebook (which joins the
expectation definitions with the pipeline event log's pass/fail counts).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class Expectation:
    name: str
    expr: str
    action: str  # warn | drop | fail


@dataclass
class Dataset:
    name: str
    kind: str
    expectations: list[Expectation] = field(default_factory=list)
    comment: str = ""
    body: str = ""


def _matching_paren(text: str, start: int) -> int:
    depth = 0
    in_str = False
    for i in range(start, len(text)):
        ch = text[i]
        if ch == "'":
            in_str = not in_str
        elif not in_str:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    return i
    raise ValueError("unbalanced parentheses")


def _split_top_level(text: str, sep: str = ",") -> list[str]:
    parts, depth, cur, in_str = [], 0, [], False
    for ch in text:
        if ch == "'":
            in_str = not in_str
        if not in_str:
            depth += ch == "("
            depth -= ch == ")"
            if ch == sep and depth == 0:
                parts.append("".join(cur))
                cur = []
                continue
        cur.append(ch)
    parts.append("".join(cur))
    return [p.strip() for p in parts if p.strip()]


def _strip_comments(sql: str) -> str:
    return "\n".join(re.sub(r"--.*$", "", line) for line in sql.splitlines())


def parse_pipeline_sql(sql: str) -> list[Dataset]:
    sql = _strip_comments(sql)
    datasets = []
    for stmt in [s.strip() for s in re.split(r";\s*(?:\n|$)", sql) if s.strip()]:
        m = re.match(r"CREATE\s+OR\s+REFRESH\s+(MATERIALIZED\s+VIEW|STREAMING\s+TABLE)\s+(\w+)\s*", stmt, re.I)
        if not m:
            raise ValueError(f"Unsupported statement: {stmt[:80]}")
        ds = Dataset(name=m.group(2), kind=m.group(1).upper())
        rest = stmt[m.end():]
        if rest.startswith("("):
            close = _matching_paren(rest, 0)
            for c in _split_top_level(rest[1:close]):
                cm = re.match(r"CONSTRAINT\s+(\w+)\s+EXPECT\s*", c, re.I)
                if not cm:
                    raise ValueError(f"Bad constraint: {c}")
                after = c[cm.end():]
                ec = _matching_paren(after, 0)
                expr = after[1:ec]
                tail = after[ec + 1:].upper()
                action = "drop" if "DROP ROW" in tail else "fail" if "FAIL UPDATE" in tail else "warn"
                ds.expectations.append(Expectation(cm.group(1), expr, action))
            rest = rest[close + 1:].lstrip()
        cm = re.match(r"COMMENT\s+'((?:[^']|'')*)'\s*", rest, re.I)
        if cm:
            ds.comment = cm.group(1)
            rest = rest[cm.end():]
        am = re.match(r"AS\s+", rest, re.I)
        if not am:
            raise ValueError(f"{ds.name}: expected AS")
        ds.body = rest[am.end():]
        datasets.append(ds)
    return datasets
