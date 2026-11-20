"""End-to-end tests: build a fresh store from the sample CSVs, run every check,
apply the one fix, and talk to the agent server. Standard library only:

    python -m unittest -v
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="trailmark-test-"))
os.environ["TRAILMARK_STORE"] = str(TMP / "test.rl")
sys.path.insert(0, str(ROOT))

from trailmark import checks, graph  # noqa: E402

EXPECTED = {
    "INV-1042": "missing-receipt",
    "INV-1038": "over-billed",
    "INV-1036": "payment-returned",
    "INV-1040": "duplicate-invoice",
    "INV-1041": "gst-not-filed",
    "INV-1037": "new-bank-account",
}


# the same rule the browser uses to offer the "cut this link" experiment
CUTTABLE = (ROOT / "cypher" / "cuttable.cypher").read_text(encoding="utf-8")


class TrailmarkTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stats = graph.build(graph.STORE, quiet=True)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(TMP, ignore_errors=True)

    def test_1_graph_shape(self):
        self.assertEqual(self.stats, {"nodes": 184, "relationships": 265})

    def test_2_every_planted_break_is_found_and_nothing_else(self):
        found = {f["invoice"]: f["check"] for f in checks.scan()}
        self.assertEqual(found, EXPECTED)

    def test_3_evidence(self):
        by = {f["check"]: f for f in checks.scan()}
        self.assertEqual(by["missing-receipt"]["suggestion"]["grn"], "GRN-5520")
        self.assertEqual(by["payment-returned"]["amount"], 195600)
        self.assertEqual(by["over-billed"]["amount"], 4956)
        self.assertIn("Sameer Patil", by["new-bank-account"]["detail"])
        self.assertIn("owns the receiving account", by["new-bank-account"]["detail"])

    def test_4_clean_invoice_trail(self):
        ex = checks.explain("INV-1005")
        self.assertEqual(ex["status"], "reconciled")
        labels = sorted({n["label"] for n in ex["nodes"]})
        self.assertEqual(labels, ["BankAccount", "BankLine", "GoodsReceipt", "GstrLine", "Invoice", "Payment", "PurchaseOrder", "Vendor"])

    def test_5_link_fixes_invoice_1042(self):
        self.assertEqual(checks.explain("INV-1042")["status"], "exception")
        bad = checks.link_receipt("GRN-5520", "PO-7720", "wrong vendor")
        self.assertFalse(bad["ok"])
        ok = checks.link_receipt("GRN-5520", "PO-7713", "PO digits swapped", by="test")
        self.assertTrue(ok["ok"])
        self.assertEqual(ok["was_keyed_as"], "PO-7731")
        self.assertEqual(checks.explain("INV-1042")["status"], "matched")
        again = checks.link_receipt("GRN-5520", "PO-7713", "twice")
        self.assertFalse(again["ok"])

    def test_6_agent_server(self):
        msgs = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "explain_invoice", "arguments": {"invoice_id": "INV-1036"}}},
            {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "read_cypher", "arguments": {"query": "CREATE (:Nope)"}}},
        ]
        p = subprocess.run([sys.executable, "-m", "trailmark", "mcp"], cwd=ROOT, input="\n".join(json.dumps(m) for m in msgs) + "\n",
                           capture_output=True, text=True, encoding="utf-8", timeout=120, env=os.environ)
        replies = {r["id"]: r for r in map(json.loads, p.stdout.splitlines())}
        self.assertEqual({t["name"] for t in replies[2]["result"]["tools"]},
                         {"scan_exceptions", "explain_invoice", "link_receipt", "read_cypher", "get_schema"})
        body = json.loads(replies[3]["result"]["content"][0]["text"])
        self.assertEqual(body["findings"][0]["check"], "payment-returned")
        self.assertTrue(replies[4]["result"]["isError"])  # read_cypher is read-only

    def test_7_export_for_browser(self):
        from trailmark.export import export
        out = TMP / "graph.json"
        data = export(graph.STORE, out, quiet=True)
        self.assertEqual(sum(len(g["rows"]) for g in data["nodes"]), 184)
        q = json.loads((TMP / "queries.json").read_text(encoding="utf-8"))
        self.assertEqual(len(q["checks"]), 6)

    def test_8_every_cut_receipt_link_is_caught_once(self):
        """The browser's "cut this link" experiment: on every clean invoice whose PO has one receipt,
        deleting that RECEIVED_AGAINST link must raise exactly one new finding (missing receipt, for that
        invoice, suggesting the same receipt back) and leave every other finding as it was."""
        base = {f["invoice"]: f["check"] for f in checks.scan()}
        with graph.open_store() as db:
            eligible = [e for e in graph.run(db, CUTTABLE) if e["inv"] not in base]
        self.assertGreaterEqual(len(eligible), 15)
        for e in eligible:
            with self.subTest(invoice=e["inv"]), graph.open_store() as db:
                graph.run(db, "MATCH (:GoodsReceipt {id: $g})-[r:RECEIVED_AGAINST]->(:PurchaseOrder {id: $p}) DELETE r", {"g": e["grn"], "p": e["po"]})
                try:
                    got = {}
                    for f in checks.scan(db):
                        got.setdefault(f["invoice"], []).append(f)
                    new = got.pop(e["inv"], [])
                    self.assertEqual([f["check"] for f in new], ["missing-receipt"])
                    self.assertEqual(new[0]["amount"], e["total"])
                    self.assertEqual(new[0]["suggestion"]["grn"], e["grn"])
                    self.assertEqual({k: [f["check"] for f in v] for k, v in got.items()}, {k: [c] for k, c in base.items()})
                finally:
                    graph.run(db, "MATCH (g:GoodsReceipt {id: $g}), (p:PurchaseOrder {id: $p}) CREATE (g)-[:RECEIVED_AGAINST]->(p)", {"g": e["grn"], "p": e["po"]})


if __name__ == "__main__":
    unittest.main(verbosity=2)
