"""Build and open the Trailmark store: sample CSV ledgers -> one Relate .rl file."""
from __future__ import annotations

import csv
import hashlib
import math
import os
import re
from contextlib import contextmanager
from pathlib import Path

import relate

ROOT = Path(__file__).resolve().parent.parent
STORE = Path(os.environ.get("TRAILMARK_STORE") or ROOT / "store" / "trailmark.rl")
SAMPLE = ROOT / "data" / "sample"
CYPHER = ROOT / "cypher"

INT_COLS = {"qty", "rate", "taxable", "gst", "total", "amount", "tax", "terms_days"}
VEC_DIM = 64

# label -> csv file, for documents and master data
NODE_TABLES = [
    ("Vendor", "vendors"),
    ("Employee", "employees"),
    ("BankAccount", "bank_accounts"),
    ("BankChange", "bank_changes"),
    ("PurchaseOrder", "purchase_orders"),
    ("GoodsReceipt", "goods_receipts"),
    ("Invoice", "invoices"),
    ("Payment", "payments"),
    ("BankLine", "bank_lines"),
    ("GstrLine", "gstr2b"),
]

# relationships that come straight from a link table rather than from key matching
EDGE_TABLES = [
    ("vendor_accounts", "MATCH (v:Vendor {id: r.vendor_id}), (a:BankAccount {id: r.account_id}) "
                        "CREATE (v)-[:HAS_ACCOUNT {since: r.since}]->(a)"),
    ("employee_accounts", "MATCH (e:Employee {id: r.employee_id}), (a:BankAccount {id: r.account_id}) "
                          "CREATE (e)-[:HAS_ACCOUNT {purpose: r.purpose}]->(a)"),
    ("allocations", "MATCH (p:Payment {id: r.payment_id}), (i:Invoice {id: r.invoice_id}) "
                    "CREATE (p)-[:SETTLES {amount: r.amount}]->(i)"),
    ("bank_changes", "MATCH (c:BankChange {id: r.id}), (v:Vendor {id: r.vendor_id}), "
                     "(new:BankAccount {id: r.new_account_id}), (old:BankAccount {id: r.old_account_id}), "
                     "(by:Employee {id: r.entered_by}), (ok:Employee {id: r.approved_by}) "
                     "CREATE (c)-[:FOR_VENDOR]->(v), (c)-[:NEW_ACCOUNT]->(new), (c)-[:OLD_ACCOUNT]->(old), "
                     "(by)-[:ENTERED]->(c), (ok)-[:APPROVED]->(c)"),
]


def norm_no(s: str) -> str:
    """Invoice numbers as people type them: 'BOS/889', 'bos-889' and 'BOS 889' are the same."""
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())


def text_vec(text: str) -> list[float]:
    """A tiny deterministic text vector: hashed character trigrams, L2-normalised.
    No model, no network - enough to tell 'MS angle bracket' from 'pallet'."""
    t = f"  {text.lower()}  "
    v = [0.0] * VEC_DIM
    for k in range(len(t) - 2):
        h = int.from_bytes(hashlib.blake2b(t[k:k + 3].encode(), digest_size=4).digest(), "little")
        v[h % VEC_DIM] += 1.0 if (h >> 16) & 1 else -1.0
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [round(x / n, 6) for x in v]


def read_rows(name: str) -> list[dict]:
    with open(SAMPLE / f"{name}.csv", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        for k, val in list(r.items()):
            if k in INT_COLS:
                r[k] = int(val)
            elif val in ("true", "false"):
                r[k] = val == "true"
        if "vendor_inv_no" in r:
            r["norm_no"] = norm_no(r["vendor_inv_no"])
        if name == "goods_receipts":
            r["item_vec"] = text_vec(r["item"])
        if name == "purchase_orders":
            r["item_vec"] = text_vec(r["item"])
        r["sample"] = True
    return rows


def statements(path: Path) -> list[str]:
    """Split a .cypher file on ';' (line ends), dropping // comments."""
    out, buf = [], []
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s.startswith("//") or not s:
            continue
        if s == ";":
            out.append("\n".join(buf)); buf = []
            continue
        if s.endswith(";"):
            buf.append(line.rstrip()[:-1]); out.append("\n".join(buf)); buf = []
            continue
        buf.append(line)
    if buf:
        out.append("\n".join(buf))
    return [x for x in out if x.strip()]


@contextmanager
def open_store(path: Path = STORE, read_only: bool = False):
    """Short-lived connection: Relate allows one process per store, so the CLI,
    the agent server and scripts each open, work, and close. Reads pass
    read_only=True so looking at the books never rewrites the file."""
    db = relate.connect(str(path), read_only=read_only)
    try:
        yield db
    finally:
        db.close()


def run(db, query: str, params: dict | None = None) -> list[dict]:
    return [dict(r) for r in db.execute(query, params or {})]


def build(path: Path = STORE, quiet: bool = False) -> dict:
    """(Re)create the store from data/sample/*.csv. Deterministic: same CSVs, same graph."""
    path.parent.mkdir(parents=True, exist_ok=True)
    for p in path.parent.glob(path.name + "*"):
        p.unlink()
    with open_store(path) as db:
        for q in statements(CYPHER / "schema.cypher"):
            db.execute(q)
        for label, table in NODE_TABLES:
            db.execute(f"UNWIND $rows AS r CREATE (n:{label}) SET n = r", {"rows": read_rows(table)})
        for table, q in EDGE_TABLES:
            db.execute(f"UNWIND $rows AS r {q}", {"rows": read_rows(table)})
        for q in statements(CYPHER / "link.cypher"):
            db.execute(q)
        stats = counts(db)
    if not quiet:
        print(f"built {_rel(path)}: {stats['nodes']} nodes, {stats['relationships']} relationships")
    return stats


def _rel(p: Path) -> str:
    try:
        return p.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(p)


def counts(db) -> dict:
    n = run(db, "MATCH (n) RETURN count(n) AS c")[0]["c"]
    r = run(db, "MATCH ()-[r]->() RETURN count(r) AS c")[0]["c"]
    return {"nodes": n, "relationships": r}
