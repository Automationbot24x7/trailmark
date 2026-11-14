"""Terminal rendering: plain text with a little colour, readable in any terminal."""
from __future__ import annotations

import os
import re
import sys

STAGES = [
    ("Vendor", "Vendor"),
    ("PurchaseOrder", "Purchase order"),
    ("GoodsReceipt", "Goods receipt"),
    ("Invoice", "Invoice"),
    ("Payment", "Payment"),
    ("BankLine", "Bank statement"),
    ("GstrLine", "Our GSTR-2B"),
    ("BankAccount", "Paid to account"),
    ("BankChange", "Bank detail change"),
    ("Employee", "People"),
]
STAGE_NAME = dict(STAGES)
STAGE_ORDER = {k: i for i, (k, _) in enumerate(STAGES)}


def _enable_ansi() -> bool:
    if not sys.stdout.isatty() or os.environ.get("NO_COLOR"):
        return False
    if os.name == "nt":
        os.system("")  # turns on VT processing in the Windows console
    return True


try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
COLOR = _enable_ansi()


def c(code: str, s: str) -> str:
    return f"\033[{code}m{s}\033[0m" if COLOR else s


def dim(s): return c("2", s)
def bold(s): return c("1", s)
def red(s): return c("31", s)
def green(s): return c("32", s)
def amber(s): return c("33", s)


def inr(n) -> str:
    """Indian digit grouping: 1295600 -> 12,95,600."""
    n = int(round(float(n)))
    neg, s = n < 0, str(abs(n))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        head = re.sub(r"(\d)(?=(\d\d)+$)", r"\1,", head)
        s = head + "," + tail
    return ("-" if neg else "") + "₹" + s


def rupees_in_text(text: str) -> str:
    text = re.sub(r"Rs (\d+)", lambda m: inr(m.group(1)), text or "")
    return re.sub(r"(^|[\s(])(\d{4,})(?=[\s,.)]|$)", lambda m: m.group(1) + f"{int(m.group(2)):,}", text)


def node_line(n: dict) -> str:
    p, k = n["props"], n["label"]
    if k == "Vendor":
        return f"{p['name']} · {p['city']} · GSTIN {p['gstin']}"
    if k == "PurchaseOrder":
        return f"{p['date']} · {p['qty']} × {p['item']} · {inr(p['total'])}"
    if k == "GoodsReceipt":
        return f"{p['date']} · {p['qty']} received · PO ref {p['po_ref']}"
    if k == "Invoice":
        return f"{p['vendor_inv_no']} · {p['date']} · {p['qty']} unit{'s' if p['qty'] != 1 else ''} · {inr(p['total'])}"
    if k == "Payment":
        return f"{p['date']} · {inr(p['amount'])} · UTR {p['utr']}"
    if k == "BankLine":
        return f"{p['date']} · {p['direction']} {inr(p['amount'])} · {p['narration']}"
    if k == "GstrLine":
        return f"period {p['period']} · {p['vendor_inv_no']} · tax {inr(p['tax'])}"
    if k == "BankAccount":
        return f"{p['bank']} ··{p['last4']}"
    if k == "BankChange":
        return f"{p['date']} · {p['reason']}"
    if k == "Employee":
        return f"{p['name']} · {p['role']}"
    return ""


def trail(ex: dict) -> str:
    inv = ex["invoice"]
    flagged = {x for f in ex["findings"] for x in (f.get("path") or [])}
    missing = [f["missing"] for f in ex["findings"] if f.get("missing")]
    sugg = {f["suggestion"]["grn"] for f in ex["findings"] if f.get("suggestion")}
    nodes = sorted(ex["nodes"], key=lambda n: (STAGE_ORDER.get(n["label"], 99), n["id"]))
    tone = {"exception": red, "reconciled": green, "matched": green, "overdue": amber}[ex["status"]]
    out = [
        "",
        f"  {bold(inv['id'])}  {inv['vendor']} {inv['vendor_no']}  {inr(inv['total'])}   "
        f"{tone(ex['status'].upper())}   {dim('SAMPLE DATA')}",
        "  " + "─" * 78,
    ]
    last = None
    for n in nodes:
        stage = STAGE_NAME.get(n["label"], n["label"])
        head = f"{stage:<19}" if stage != last else " " * 19
        last = stage
        mark = "  "
        if n["id"] in sugg:
            mark = amber("? ")
        elif n["id"] in flagged:
            mark = red("● ") if any(f["severity"] == "high" for f in ex["findings"]) else amber("● ")
        line = f"  {dim(head)}{mark}{bold(n['id']):<10} {node_line(n)}"
        out.append(line)
        for m in missing:
            if m["after"] == n["id"]:
                out.append(f"  {' ' * 19}{red('┄ ')}{red(m['text'])}")
    out.append("  " + "─" * 78)
    links = sorted({f"{r['from']} -{r['type']}-> {r['to']}" for r in ex["rels"]})
    out.append(dim(f"  {len(ex['nodes'])} nodes, {len(links)} relationships on this trail"))
    return "\n".join(out)


def finding(f: dict, n: int | None = None) -> str:
    sev = red("HIGH  ") if f["severity"] == "high" else amber("MEDIUM")
    lines = [
        f"  {sev} {bold(f['title'])} — {rupees_in_text(f['headline'])}",
        *[f"         {x}" for x in wrap(rupees_in_text(f["detail"]), 74)],
    ]
    if f.get("suggestion"):
        s = f["suggestion"]
        lines.append(f"         {amber('Suggested fix:')} {s['text']}  (text similarity {s['similarity']})")
        lines.append(f"         {dim('trailmark link ' + s['grn'] + ' ' + s['po'])}")
    lines.append(f"         {dim('query: ' + f['query_file'])}")
    return "\n".join(lines)


def wrap(text: str, width: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > width and cur:
            lines.append(cur); cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    return lines
