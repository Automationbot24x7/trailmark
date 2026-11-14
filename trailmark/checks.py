"""Run the Cypher checks and assemble per-invoice answers. Shared by the CLI and the agent server."""
from __future__ import annotations

import re
from datetime import date, datetime, timezone
from pathlib import Path

from .graph import CYPHER, open_store, run

CHECKS_DIR = CYPHER / "checks"
AS_OF = "2026-10-31"  # the sample books are closed as of this date


def check_files() -> list[Path]:
    return sorted(CHECKS_DIR.glob("*.cypher"))


def header(path: Path) -> dict:
    """Read the '// key: value' lines at the top of a .cypher file."""
    meta = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"//\s*(\w+):\s*(.*)", line)
        if not m:
            break
        meta[m.group(1)] = m.group(2)
    return meta


def query(name: str) -> str:
    return (CYPHER / name).read_text(encoding="utf-8")


def scan(db=None) -> list[dict]:
    """Every finding from every check, most severe and largest first."""
    def go(db):
        out = []
        for f in check_files():
            meta = header(f)
            for row in run(db, f.read_text(encoding="utf-8")):
                row["title"] = meta.get("title", f.stem)
                row["query_file"] = f.relative_to(CYPHER.parent).as_posix()
                out.append(row)
        out.sort(key=lambda r: (r["severity"] != "high", -int(r["amount"] or 0)))
        return out
    if db is not None:
        return go(db)
    with open_store(read_only=True) as db:
        return go(db)


def invoices(db) -> list[dict]:
    return run(db, """
        MATCH (i:Invoice)-[:ISSUED_BY]->(v:Vendor)
        OPTIONAL MATCH (p:Payment)-[:SETTLES]->(i)
        WITH i, v, collect(p.id) AS payments
        RETURN i.id AS id, v.name AS vendor, i.vendor_inv_no AS vendor_no, i.date AS date,
               i.total AS total, payments, v.terms_days AS terms
        ORDER BY i.id""")


def status(inv: dict, findings: list[dict]) -> str:
    if findings:
        return "exception"
    if inv["payments"]:
        return "reconciled"
    due = date.fromisoformat(inv["date"]).toordinal() + int(inv["terms"])
    return "matched" if due > date.fromisoformat(AS_OF).toordinal() else "overdue"


def explain(invoice_id: str, db=None) -> dict | None:
    """Findings for one invoice plus its trail (nodes and relationships)."""
    def go(db):
        inv = [r for r in invoices(db) if r["id"] == invoice_id]
        if not inv:
            return None
        inv = inv[0]
        found = [f for f in scan(db) if f["invoice"] == invoice_id]
        extra = sorted({x for f in found for x in (f.get("path") or [])} |
                       {f["suggestion"]["grn"] for f in found if f.get("suggestion")})
        t = run(db, query("trail.cypher"), {"id": invoice_id, "extra": extra})[0]
        for n in t["nodes"]:
            n["props"].pop("item_vec", None)
        due = date.fromordinal(date.fromisoformat(inv["date"]).toordinal() + int(inv["terms"])).isoformat()
        inv["due"] = due
        return {"invoice": inv, "status": status(inv, found), "findings": found,
                "nodes": t["nodes"], "rels": [r for r in t["rels"] if r]}
    if db is not None:
        return go(db)
    with open_store(read_only=True) as db:
        return go(db)


def link_receipt(grn: str, po: str, note: str = "", by: str = "trailmark-cli") -> dict:
    at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with open_store() as db:
        rows = run(db, query("link_receipt.cypher"), {"grn": grn, "po": po, "note": note, "by": by, "at": at})
    if not rows:
        return {"ok": False, "error": f"Not linked: {grn} must exist, be linked to no PO yet, and come from the same vendor as {po}."}
    return {"ok": True, **rows[0]}


def summary(db) -> dict:
    found = scan(db)
    invs = invoices(db)
    by_inv = {}
    for f in found:
        by_inv.setdefault(f["invoice"], []).append(f)
    states = {i["id"]: status(i, by_inv.get(i["id"], [])) for i in invs}
    return {"as_of": AS_OF, "invoices": len(invs),
            "reconciled": sum(1 for s in states.values() if s == "reconciled"),
            "matched": sum(1 for s in states.values() if s == "matched"),
            "exceptions": sum(1 for s in states.values() if s == "exception"),
            "at_risk": sum(int(f["amount"] or 0) for f in found),
            "findings": found, "states": states}
