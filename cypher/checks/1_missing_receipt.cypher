// title: Invoice has no goods receipt
// plain: The vendor billed us against a purchase order that shows nothing received. Before chasing the vendor, look for a receipt keyed against the wrong PO.
// graph: Invoice -BILLS-> PurchaseOrder <-RECEIVED_AGAINST- (nothing). A vector search over receipt item text (same vendor) finds lookalike receipts; the graph then rejects any already received against another PO or with a different quantity.
// next: Ask stores to confirm the goods arrived, then link the receipt to the right PO. Do not pay until it is linked.
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
WITH i, po, v, candidate, [c IN considered WHERE candidate IS NULL OR (c.id <> candidate.id AND c.sim >= candidate.sim)] AS rejected
RETURN 'missing-receipt' AS check,
       'medium' AS severity,
       i.id AS invoice,
       'No goods receipt for ' + po.id AS headline,
       i.id + ' bills ' + toString(po.qty) + ' x ' + po.item + ' on ' + po.id + ', but nothing has been received against that PO. ' +
       CASE WHEN candidate IS NULL THEN 'No unlinked receipt from this vendor looks like it.'
         ELSE candidate.id + ' ("' + candidate.item + '", ' + toString(candidate.qty) + ' received on ' + candidate.date +
              ') is from the same vendor and linked to no PO. ' +
              CASE WHEN candidate.ref = po.id THEN 'It was keyed against ' + po.id + ' itself, so the link to the PO is what went missing.'
                   ELSE 'It was keyed against ' + candidate.ref + ', a PO number that does not exist.' END +
              reduce(s = '', r IN rejected | s + ' ' + r.id + CASE WHEN r.sim > candidate.sim THEN ' scores higher (' ELSE ' also matches (' END + toString(toInteger(r.sim)) + '.' + right('0' + toString(toInteger(round(r.sim * 100)) % 100), 2) + ') but ' +
                     CASE WHEN r.linked_to IS NOT NULL THEN 'is already received against ' + r.linked_to + '.'
                          ELSE 'has a different quantity (' + toString(r.qty) + ').' END)
       END AS detail,
       i.total AS amount,
       [v.id, po.id, i.id] AS path,
       {after: po.id, label: 'GoodsReceipt', text: 'expected: a receipt against ' + po.id} AS missing,
       CASE WHEN candidate IS NULL THEN null
         ELSE {action: 'link_receipt', grn: candidate.id, po: po.id, similarity: candidate.sim,
               rejected: [r IN rejected | r.id + ' (' + toString(toInteger(r.sim)) + '.' + right('0' + toString(toInteger(round(r.sim * 100)) % 100), 2) + CASE WHEN r.linked_to IS NOT NULL THEN ', already received against ' + r.linked_to ELSE ', quantity ' + toString(r.qty) END + ')'],
               text: 'Link ' + candidate.id + ' to ' + po.id + CASE WHEN candidate.ref = po.id THEN '' ELSE ' (keyed as ' + candidate.ref + ')' END}
       END AS suggestion
