"""trailmark - why doesn't this invoice reconcile?

  python -m trailmark scan                 every exception in the sample books
  python -m trailmark explain INV-1042     one invoice's trail, and where it breaks
  python -m trailmark link GRN-5520 PO-7713 --note "PO digits swapped"
  python -m trailmark view                 open the graph in your browser (WebAssembly)
  python -m trailmark mcp                  serve the tools to an AI agent over MCP (stdio)
  python -m trailmark cypher "MATCH (n:Vendor) RETURN n.name"
  python -m trailmark build                rebuild store/trailmark.rl from data/sample/*.csv
"""
from __future__ import annotations

import argparse
import json
import sys

from . import checks, graph, render
from .render import bold, dim, green, inr, red


def cmd_build(a):
    graph.build()
    from .export import export
    export()


def cmd_scan(a):
    import relate
    db = relate.connect(str(graph.STORE), read_only=True)
    s = checks.summary(db)
    db.close()
    if a.json:
        print(json.dumps(s, indent=2, default=str)); return
    print()
    print(f"  {bold('Trailmark')}  accounts payable as of {s['as_of']}   {dim('SAMPLE DATA - all names and numbers are invented')}")
    print("  " + "─" * 78)
    print(f"  {s['invoices']} invoices   {green(str(s['reconciled']) + ' reconciled')}   {s['matched']} matched, not yet due   "
          f"{red(str(s['exceptions']) + ' exceptions')}   {inr(s['at_risk'])} at risk")
    print("  " + "─" * 78)
    for f in s["findings"]:
        sev = red("●") if f["severity"] == "high" else render.amber("●")
        print(f"  {sev} {bold(f['invoice']):<10} {f['title']:<44} {inr(f['amount']):>12}")
        print(f"      {dim(render.rupees_in_text(f['headline']))}")
    print()
    print(dim("  Explain one:  python -m trailmark explain INV-1042"))
    print()


def cmd_explain(a):
    ex = checks.explain(a.invoice.upper())
    if ex is None:
        sys.exit(f"No invoice {a.invoice}. Try: python -m trailmark scan")
    if a.json:
        print(json.dumps(ex, indent=2, default=str)); return
    print(render.trail(ex))
    if not ex["findings"]:
        msg = {"reconciled": "Every link holds: received, billed, paid, cleared and reported.",
               "matched": f"Matched: ordered, received and billed agree. Due {ex['invoice']['due']}, so no payment yet.",
               "overdue": "Received and billed, past due and unpaid."}[ex["status"]]
        print(f"\n  {green('✓') if ex['status'] in ('reconciled', 'matched') else '·'} {msg}\n")
        return
    print()
    for f in ex["findings"]:
        print(render.finding(f))
        print()


def cmd_link(a):
    r = checks.link_receipt(a.grn.upper(), a.po.upper(), a.note or "", by=a.by)
    if not r["ok"]:
        sys.exit(r["error"])
    print(f"\n  Linked {bold(r['grn'])} -RECEIVED_AGAINST-> {bold(r['po'])}  (was keyed as {r['was_keyed_as']}, by {r['linked_by']})")
    import relate
    db = relate.connect(str(graph.STORE), read_only=True)
    invs = graph.run(db, "MATCH (i:Invoice)-[:BILLS]->(:PurchaseOrder {id: $po}) RETURN i.id AS id", {"po": r["po"]})
    db.close()
    for i in invs:
        cmd_explain(argparse.Namespace(invoice=i["id"], json=False))
    print(dim("  Undo all changes:  python -m trailmark build\n"))


def cmd_cypher(a):
    import relate
    db = relate.connect(str(graph.STORE), read_only=True)
    rows = graph.run(db, a.query, json.loads(a.params) if a.params else {})
    db.close()
    for r in rows[:100]:
        r.pop("item_vec", None)
        print(json.dumps(r, ensure_ascii=False, default=str))
    if len(rows) > 100:
        print(f"... {len(rows) - 100} more rows not shown")


def cmd_view(a):
    from .view import serve
    serve(a.port, open_browser=not a.no_browser)


def cmd_mcp(a):
    from .mcp import main
    main()


def cmd_export(a):
    from .export import export
    export()


def main(argv=None):
    p = argparse.ArgumentParser(prog="trailmark", description="Why doesn't this invoice reconcile? A Relate graph of the AP trail.")
    sub = p.add_subparsers(dest="cmd")
    s = sub.add_parser("scan", help="list every exception"); s.add_argument("--json", action="store_true"); s.set_defaults(fn=cmd_scan)
    s = sub.add_parser("explain", help="trail and breaks for one invoice"); s.add_argument("invoice")
    s.add_argument("--json", action="store_true"); s.set_defaults(fn=cmd_explain)
    s = sub.add_parser("link", help="link a goods receipt to its PO (writes to the store)")
    s.add_argument("grn"); s.add_argument("po"); s.add_argument("--note", default="")
    s.add_argument("--by", default="trailmark-cli"); s.set_defaults(fn=cmd_link)
    s = sub.add_parser("cypher", help="run a read-only Cypher query"); s.add_argument("query")
    s.add_argument("--params", help="JSON object of parameters"); s.set_defaults(fn=cmd_cypher)
    s = sub.add_parser("view", help="open the browser view"); s.add_argument("--port", type=int, default=8765)
    s.add_argument("--no-browser", action="store_true"); s.set_defaults(fn=cmd_view)
    s = sub.add_parser("mcp", help="MCP server on stdio for AI agents"); s.set_defaults(fn=cmd_mcp)
    s = sub.add_parser("build", help="rebuild the store from the sample CSVs"); s.set_defaults(fn=cmd_build)
    s = sub.add_parser("export", help="write web/data/graph.json from the store"); s.set_defaults(fn=cmd_export)
    a = p.parse_args(argv)
    if not getattr(a, "fn", None):
        print(__doc__); return
    a.fn(a)


if __name__ == "__main__":
    main()
