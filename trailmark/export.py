"""Export the store for the browser view.

The WebAssembly build of Relate runs in memory (or OPFS) and cannot open a .rl
file, so the browser rebuilds the same graph from this export: every node and
relationship, read back out of store/trailmark.rl, grouped so each group loads
with one UNWIND statement.
"""
from __future__ import annotations

import json
from collections import defaultdict

import relate

from .graph import ROOT, STORE, run

OUT = ROOT / "web" / "data" / "graph.json"


def export(path=STORE, out=OUT, quiet=False) -> dict:
    db = relate.connect(str(path), read_only=True)
    try:
        nodes = defaultdict(list)
        for r in run(db, "MATCH (n) RETURN labels(n)[0] AS label, properties(n) AS props ORDER BY n.id"):
            nodes[r["label"]].append(r["props"])
        rels = defaultdict(list)
        for r in run(db, """MATCH (a)-[r]->(b)
                           RETURN labels(a)[0] AS fl, a.id AS a, type(r) AS type, labels(b)[0] AS tl, b.id AS b,
                                  properties(r) AS props ORDER BY a, type, b"""):
            rels[(r["type"], r["fl"], r["tl"])].append({"a": r["a"], "b": r["b"], "props": r["props"]})
    finally:
        db.close()
    data = {
        "source": "store/trailmark.rl",
        "note": "SAMPLE DATA - every name, GSTIN, account and amount is invented.",
        "nodes": [{"label": k, "rows": v} for k, v in sorted(nodes.items())],
        "rels": [{"type": t, "from": fl, "to": tl, "rows": v} for (t, fl, tl), v in sorted(rels.items())],
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, separators=(",", ":"), default=str), encoding="utf-8")
    export_queries(out.parent / "queries.json")
    n = sum(len(x["rows"]) for x in data["nodes"]); r = sum(len(x["rows"]) for x in data["rels"])
    if not quiet:
        print(f"exported {n} nodes, {r} relationships -> {out.relative_to(ROOT).as_posix()}")
    return data


def export_queries(out):
    """The browser runs the very same .cypher files; copy them in so the page needs one fetch."""
    from .checks import AS_OF, check_files, header
    from .graph import CYPHER, statements

    def entry(p):
        return {"file": p.relative_to(ROOT).as_posix(), **header(p), "text": p.read_text(encoding="utf-8")}

    data = {
        "as_of": AS_OF,
        "schema": statements(CYPHER / "schema.cypher"),
        "checks": [entry(p) for p in check_files()],
        "trail": entry(CYPHER / "trail.cypher"),
        "link_receipt": entry(CYPHER / "link_receipt.cypher"),
        "cuttable": entry(CYPHER / "cuttable.cypher"),
    }
    out.write_text(json.dumps(data, indent=1), encoding="utf-8")
