// title: Invoice has no goods receipt
// plain: The vendor billed us against a purchase order that shows nothing received. Before chasing the vendor, look for a receipt keyed against the wrong PO.
// graph: Invoice -BILLS-> PurchaseOrder <-RECEIVED_AGAINST- (nothing). Candidates come from a vector search over receipt item text, filtered to the same vendor, then kept only if unlinked and the quantity agrees.
MATCH (i:Invoice)-[:BILLS]->(po:PurchaseOrder)-[:PLACED_WITH]->(v:Vendor)
WHERE NOT EXISTS { (po)<-[:RECEIVED_AGAINST]-(:GoodsReceipt) }
OPTIONAL CALL (po) {
  MATCH (g:GoodsReceipt)
  SEARCH g IN (VECTOR INDEX grn_item FOR po.item_vec WHERE g.vendor_id = po.vendor_id LIMIT 10) SCORE AS sim
  WITH g, sim
  WHERE NOT EXISTS { (g)-[:RECEIVED_AGAINST]->() } AND g.qty = po.qty
  RETURN g AS candidate, sim
  ORDER BY sim DESC
  LIMIT 1
}
RETURN 'missing-receipt' AS check,
       'medium' AS severity,
       i.id AS invoice,
       'No goods receipt for ' + po.id AS headline,
       CASE WHEN candidate IS NULL
         THEN i.id + ' bills ' + toString(po.qty) + ' x ' + po.item + ' on ' + po.id + ', but nothing has been received against that PO.'
         ELSE i.id + ' bills ' + toString(po.qty) + ' x ' + po.item + ' on ' + po.id + '. Nothing was received against ' + po.id +
              ', but ' + candidate.id + ' (same vendor, same item, same quantity, ' + candidate.date + ') was keyed against ' +
              candidate.po_ref + ', a PO number that does not exist.'
       END AS detail,
       i.total AS amount,
       [v.id, po.id, i.id] AS path,
       {after: po.id, label: 'GoodsReceipt', text: 'expected: a receipt against ' + po.id} AS missing,
       CASE WHEN candidate IS NULL THEN null
         ELSE {action: 'link_receipt', grn: candidate.id, po: po.id, similarity: round(sim, 3),
               text: 'Link ' + candidate.id + ' to ' + po.id + ' (keyed as ' + candidate.po_ref + ')'}
       END AS suggestion
