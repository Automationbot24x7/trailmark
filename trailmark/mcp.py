"""Trailmark as MCP tools for AI agents (stdio, newline-delimited JSON-RPC 2.0).

Register with any MCP host as:  python -m trailmark mcp   (see .mcp.json)

Reads open the store read-only; the single write tool (link_receipt) runs one
guarded Cypher statement and records who made the change and why. Raw Cypher is
read-only and capped at 100 rows with an explicit truncation flag, so an agent
never mistakes a partial answer for a complete one.
"""
from __future__ import annotations

import json
import sys
import traceback

import relate

from . import checks, graph
from .render import node_line, rupees_in_text

SERVER = {"name": "trailmark", "version": "0.1.0"}
ROW_CAP = 100

SCHEMA_TEXT = """Trailmark: an accounts-payable graph (SAMPLE DATA, invented).
Flow: (:PurchaseOrder)-[:PLACED_WITH]->(:Vendor); (:GoodsReceipt)-[:RECEIVED_AGAINST]->(:PurchaseOrder);
(:Invoice)-[:BILLS]->(:PurchaseOrder); (:Invoice)-[:ISSUED_BY]->(:Vendor);
(:Payment)-[:SETTLES {amount}]->(:Invoice)  (one payment may settle many invoices);
(:BankLine)-[:CLEARS]->(:Payment)  (one payment may leave the bank as several debits);
(:BankLine)-[:REVERSES]->(:BankLine)  (a returned debit);
(:GstrLine)-[:REPORTS]->(:Invoice)  (supplier's GSTR-2B filing);
(:Payment)-[:PAID_TO]->(:BankAccount)<-[:HAS_ACCOUNT {since}]-(:Vendor|:Employee);
(:Employee)-[:APPROVED]->(:Payment|:BankChange); (:Employee)-[:ENTERED]->(:BankChange);
(:BankChange)-[:FOR_VENDOR|NEW_ACCOUNT|OLD_ACCOUNT]->(...).
Every node has an `id`. Amounts are whole rupees. Dates are ISO strings (use date(x) for arithmetic)."""

TOOLS = [
    {"name": "scan_exceptions",
     "description": "Run every reconciliation check over the AP graph. Returns totals and each finding: invoice, check, severity, plain-English detail, amount at risk, the evidence path (node ids) and, when the graph can see one, a suggested fix.",
     "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"name": "explain_invoice",
     "description": "Why does this invoice (not) reconcile? Returns its status, the findings, and its trail: vendor, PO, receipts, payments, bank lines, GSTR-2B lines, beneficiary account and any people the evidence touches, as nodes with one-line summaries and the relationships between them.",
     "inputSchema": {"type": "object", "properties": {"invoice_id": {"type": "string", "description": "e.g. INV-1042"}},
                     "required": ["invoice_id"], "additionalProperties": False}},
    {"name": "link_receipt",
     "description": "WRITE. Link a goods receipt to the purchase order it belongs to, e.g. when stores keyed the wrong PO number. Only links a receipt that is linked to nothing, to a PO of the same vendor. Records linked_by, note and the original PO reference. Ask the user before calling.",
     "inputSchema": {"type": "object", "properties": {
         "grn_id": {"type": "string"}, "po_id": {"type": "string"},
         "note": {"type": "string", "description": "why the link is right, for the audit trail"}},
         "required": ["grn_id", "po_id", "note"], "additionalProperties": False}},
    {"name": "read_cypher",
     "description": "Run a read-only Cypher query on the AP graph (Relate, current Cypher: quantified path patterns, SHORTEST, CALL subqueries, vector SEARCH). At most 100 rows; `truncated` says if more existed. Call get_schema first.",
     "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}, "params": {"type": "object"}},
                     "required": ["query"], "additionalProperties": False}},
    {"name": "get_schema",
     "description": "Node labels and relationship types with counts, and what each relationship means in accounts-payable terms.",
     "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
]


def _ro():
    return relate.connect(str(graph.STORE), read_only=True)


def _clean(obj):
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items() if k not in ("item_vec",)}
    if isinstance(obj, list):
        return [_clean(x) for x in obj]
    return obj


def _finding(f):
    return {"invoice": f["invoice"], "check": f["check"], "title": f["title"], "severity": f["severity"],
            "headline": rupees_in_text(f["headline"]), "detail": rupees_in_text(f["detail"]),
            "amount_at_risk": f["amount"], "evidence_path": f["path"], "expected_but_missing": f.get("missing"),
            "suggested_fix": f.get("suggestion"), "cypher": f["query_file"]}


def tool_scan_exceptions(_):
    db = _ro()
    try:
        s = checks.summary(db)
    finally:
        db.close()
    return {"as_of": s["as_of"], "invoices": s["invoices"], "reconciled": s["reconciled"],
            "matched_not_due": s["matched"], "exceptions": s["exceptions"], "amount_at_risk": s["at_risk"],
            "findings": [_finding(f) for f in s["findings"]], "data": "SAMPLE - invented"}


def tool_explain_invoice(args):
    db = _ro()
    try:
        ex = checks.explain(args["invoice_id"].strip().upper(), db)
    finally:
        db.close()
    if ex is None:
        return {"error": f"No invoice {args['invoice_id']}. Invoice ids look like INV-1042; call scan_exceptions to list problem invoices."}
    return {"invoice": ex["invoice"], "status": ex["status"],
            "findings": [_finding(f) for f in ex["findings"]],
            "trail": {"nodes": [{"id": n["id"], "label": n["label"], "summary": node_line(n)} for n in ex["nodes"]],
                      "relationships": [f"({r['from']})-[:{r['type']}]->({r['to']})" for r in ex["rels"]]}}


def tool_link_receipt(args):
    r = checks.link_receipt(args["grn_id"].strip().upper(), args["po_id"].strip().upper(),
                            args.get("note", ""), by="agent (mcp)")
    if not r["ok"]:
        return r
    db = _ro()
    try:
        affected = graph.run(db, "MATCH (i:Invoice)-[:BILLS]->(:PurchaseOrder {id: $po}) RETURN i.id AS id", {"po": r["po"]})
        after = [checks.explain(a["id"], db) for a in affected]
    finally:
        db.close()
    return {**r, "invoices_now": [{"invoice": a["invoice"]["id"], "status": a["status"],
                                   "remaining_findings": [_finding(f) for f in a["findings"]]} for a in after],
            "undo": "python -m trailmark build  (rebuilds the store from the sample CSVs)"}


def tool_read_cypher(args):
    db = _ro()
    try:
        rows = graph.run(db, args["query"], args.get("params") or {})
    except Exception as e:  # the engine's message says how to fix the query
        return {"error": str(e)}
    finally:
        db.close()
    return {"rows": _clean(rows[:ROW_CAP]), "row_count": min(len(rows), ROW_CAP), "truncated": len(rows) > ROW_CAP}


def tool_get_schema(_):
    db = _ro()
    try:
        labels = graph.run(db, "MATCH (n) RETURN labels(n)[0] AS label, count(*) AS count ORDER BY label")
        rels = graph.run(db, "MATCH ()-[r]->() RETURN type(r) AS type, count(*) AS count ORDER BY type")
    finally:
        db.close()
    return {"description": SCHEMA_TEXT, "labels": labels, "relationship_types": rels}


HANDLERS = {t["name"]: globals()[f"tool_{t['name']}"] for t in TOOLS}


def handle(msg):
    method, mid = msg.get("method"), msg.get("id")
    if mid is None:  # notification
        return None
    if method == "initialize":
        ver = (msg.get("params") or {}).get("protocolVersion", "2025-06-18")
        result = {"protocolVersion": ver, "capabilities": {"tools": {}}, "serverInfo": SERVER,
                  "instructions": "Start with scan_exceptions or explain_invoice. Quote the evidence path. "
                                  "Ask the user before link_receipt. All data is invented sample data."}
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "tools/call":
        p = msg.get("params") or {}
        fn = HANDLERS.get(p.get("name"))
        if fn is None:
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32602, "message": f"unknown tool {p.get('name')}"}}
        try:
            out = fn(p.get("arguments") or {})
            is_err = isinstance(out, dict) and ("error" in out or out.get("ok") is False)
        except Exception as e:
            traceback.print_exc(file=sys.stderr)
            out, is_err = {"error": str(e)}, True
        result = {"content": [{"type": "text", "text": json.dumps(out, ensure_ascii=False, indent=1, default=str)}],
                  "isError": is_err}
    else:
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"method not found: {method}"}}
    return {"jsonrpc": "2.0", "id": mid, "result": result}


def main():
    try:
        sys.stdin.reconfigure(encoding="utf-8")
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            reply = handle(json.loads(line))
        except Exception as e:
            reply = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": str(e)}}
        if reply is not None:
            sys.stdout.write(json.dumps(reply, ensure_ascii=False) + "\n")
            sys.stdout.flush()
