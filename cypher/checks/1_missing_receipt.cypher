// title: Invoice has no goods receipt
// plain: The vendor billed us against a purchase order that shows nothing received. Before chasing the vendor, look for a receipt keyed against the wrong PO.
// graph: Invoice -BILLS-> PurchaseOrder <-RECEIVED_AGAINST- (nothing). A vector search over receipt item text (same vendor) finds lookalike receipts; the graph then rejects any already received against another PO or with a different quantity.
MATCH (i:Invoice)-[:BILLS]->(po:PurchaseOrder)-[:PLACED_WITH]->(v:Vendor)
WHERE NOT EXISTS { (po)<-[:RECEIVED_AGAINST]-(:GoodsReceipt) }
OPTIONAL CALL (po) {
  MATCH (g:GoodsReceipt)
  SEARCH g IN (VECTOR INDEX grn_item FOR po.item_vec WHERE g.vendor_id = po.vendor_id LIMIT 5) SCORE AS sim
  OPTIONAL MATCH (g)-[:RECEIVED_AGAINST]->(other:PurchaseOrder)
  WITH g, sim, other
  ORDER BY sim DESC
  RETURN collect({id: g.id, sim: round(sim, 2), qty: g.qty, ref: g.po_ref, date: g.date, item: g.item, linked_to: other.id}) AS considered
}
WITH i, po, v, considered, [c IN considered WHERE c.linked_to IS NULL AND c.qty = po.qty] AS eligible
WITH i, po, v, considered, CASE WHEN size(eligible) > 0 THEN eligible[0] END AS candidate
WITH i, po, v, candidate, [c IN considered WHERE candidate IS NULL OR c.id <> candidate.id] AS rejected
RETURN 'missing-receipt' AS check,
       'medium' AS severity,
       i.id AS invoice,
       'No goods receipt for ' + po.id AS headline,
       i.id + ' bills ' + toString(po.qty) + ' x ' + po.item + ' on ' + po.id + ', but nothing has been received against that PO. ' +
       CASE WHEN candidate IS NULL THEN 'No unlinked receipt from this vendor looks like it.'
         ELSE candidate.id + ' ("' + candidate.item + '", ' + toString(candidate.qty) + ' received on ' + candidate.date +
              ') is from the same vendor, linked to no PO, and was keyed against ' + candidate.ref + ', a PO number that does not exist.' +
              reduce(s = '', r IN rejected | s + ' ' + r.id + ' looks closer (' + toString(r.sim) + ') but ' +
                     CASE WHEN r.linked_to IS NOT NULL THEN 'is already received against ' + r.linked_to + '.'
                          ELSE 'has a different quantity (' + toString(r.qty) + ').' END)
       END AS detail,
       i.total AS amount,
       [v.id, po.id, i.id] AS path,
       {after: po.id, label: 'GoodsReceipt', text: 'expected: a receipt against ' + po.id} AS missing,
       CASE WHEN candidate IS NULL THEN null
         ELSE {action: 'link_receipt', grn: candidate.id, po: po.id, similarity: candidate.sim,
               rejected: [r IN rejected | r.id + ' ' + toString(r.sim) + CASE WHEN r.linked_to IS NOT NULL THEN ', already on ' + r.linked_to ELSE ', qty ' + toString(r.qty) END],
               text: 'Link ' + candidate.id + ' to ' + po.id + ' (keyed as ' + candidate.ref + ')'}
       END AS suggestion
