// Trailmark linking rules: flat ledgers in, relationships out.
// Each statement infers one kind of link from the keys an accountant would use
// (PO number, bank reference/UTR, GSTIN + invoice number). Statements are
// separated by a line holding only ";".

// Who placed / delivered / issued what
MATCH (po:PurchaseOrder) MATCH (v:Vendor {id: po.vendor_id}) CREATE (po)-[:PLACED_WITH]->(v)
;
MATCH (g:GoodsReceipt) MATCH (v:Vendor {id: g.vendor_id}) CREATE (g)-[:DELIVERED_BY]->(v)
;
MATCH (i:Invoice) MATCH (v:Vendor {id: i.vendor_id}) CREATE (i)-[:ISSUED_BY]->(v)
;
// Three-way match links: a receipt counts against a PO only if its PO number exists
MATCH (g:GoodsReceipt) MATCH (po:PurchaseOrder {id: g.po_ref}) CREATE (g)-[:RECEIVED_AGAINST]->(po)
;
MATCH (i:Invoice) MATCH (po:PurchaseOrder {id: i.po_id}) CREATE (i)-[:BILLS]->(po)
;
// Money out: payment -> beneficiary account, approver
MATCH (p:Payment) MATCH (a:BankAccount {id: p.account_id}) CREATE (p)-[:PAID_TO]->(a)
;
MATCH (p:Payment) MATCH (e:Employee {id: p.approved_by}) CREATE (e)-[:APPROVED]->(p)
;
// Bank statement: a debit clears the payment with the same UTR; a RETURN credit reverses the debit it refunds
MATCH (b:BankLine {direction: 'debit'}) MATCH (p:Payment {utr: b.utr}) CREATE (b)-[:CLEARS]->(p)
;
MATCH (r:BankLine {direction: 'credit'}), (b:BankLine {direction: 'debit'})
WHERE r.utr = b.utr AND r.amount = b.amount AND r.narration CONTAINS 'RETURN'
CREATE (r)-[:REVERSES]->(b)
;
// GSTR-2B (our statement, built from suppliers' GSTR-1 filings) reports our invoice when GSTIN and invoice number agree
MATCH (l:GstrLine) MATCH (v:Vendor {gstin: l.supplier_gstin})<-[:ISSUED_BY]-(i:Invoice)
WHERE i.norm_no = l.norm_no
CREATE (l)-[:REPORTS]->(i)
