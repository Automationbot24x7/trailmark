// title: Billed more than was received
// plain: Add up every receipt on the purchase order and every invoice billed against it. If the vendor billed more units than arrived, the difference was paid for nothing.
// graph: Many receipts and many invoices meet at one PurchaseOrder; both sides are summed across the fan-in. Duplicate invoices are left to check 4.
MATCH (po:PurchaseOrder)<-[:BILLS]-(i:Invoice)
WHERE NOT EXISTS {
  MATCH (po)<-[:BILLS]-(j:Invoice)
  WHERE j.id < i.id AND j.norm_no = i.norm_no AND j.vendor_id = i.vendor_id
}
WITH po, collect(i) AS invoices, sum(i.qty) AS billed
MATCH (g:GoodsReceipt)-[:RECEIVED_AGAINST]->(po)
WITH po, invoices, billed, collect(g) AS receipts, sum(g.qty) AS received
WHERE billed > received
UNWIND invoices AS i
OPTIONAL MATCH (p:Payment)-[:SETTLES]->(i)
WITH po, i, billed, received, receipts, collect(p.id) AS payments
WITH po, i, billed, received, receipts, payments,
     toInteger(round((billed - received) * po.rate * 1.18)) AS excess
RETURN 'over-billed' AS check,
       CASE WHEN size(payments) > 0 THEN 'high' ELSE 'medium' END AS severity,
       i.id AS invoice,
       'Billed ' + toString(billed) + ', received ' + toString(received) AS headline,
       i.id + ' bills ' + toString(billed) + ' units on ' + po.id + '. ' + toString(size(receipts)) +
       ' receipts (' + reduce(s = '', g IN receipts | s + CASE WHEN s = '' THEN '' ELSE ', ' END + g.id + ': ' + toString(g.qty)) +
       ') add up to ' + toString(received) + '. ' +
       CASE WHEN size(payments) > 0 THEN 'It was paid in full, so ' ELSE '' END +
       toString(billed - received) + ' units, Rs ' + toString(excess) + ' with GST, have no goods behind them.' AS detail,
       excess AS amount,
       [r IN receipts | r.id] + [po.id, i.id] + payments AS path,
       {after: po.id, label: 'GoodsReceipt', text: 'expected: ' + toString(billed - received) + ' more units received'} AS missing,
       null AS suggestion
