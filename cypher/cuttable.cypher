// Receipt links the browser lets you cut to test the checks: the PO is billed by one invoice,
// has one receipt, and that receipt is linked to nothing else. Cutting one must raise exactly one finding.
MATCH (i:Invoice)-[:BILLS]->(po:PurchaseOrder)<-[:RECEIVED_AGAINST]-(g:GoodsReceipt)
WHERE COUNT { (po)<-[:BILLS]-(:Invoice) } = 1
  AND COUNT { (po)<-[:RECEIVED_AGAINST]-() } = 1
  AND COUNT { (g)-[:RECEIVED_AGAINST]->() } = 1
RETURN i.id AS inv, po.id AS po, g.id AS grn, i.total AS total
ORDER BY inv
