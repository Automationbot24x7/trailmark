// title: Same invoice paid twice
// plain: The vendor's invoice number was keyed twice in slightly different forms (BOS/889 and BOS-889). Both copies were approved and both were paid.
// graph: Two Invoice nodes share a Vendor, a normalised invoice number, an amount and a PurchaseOrder; each has its own Payment and BankLine.
// next: Recover the second payment from the vendor and cancel the duplicate invoice.
MATCH (a:Invoice)-[:ISSUED_BY]->(v:Vendor)<-[:ISSUED_BY]-(b:Invoice)
WHERE a.id < b.id AND a.norm_no = b.norm_no AND a.total = b.total
OPTIONAL MATCH (b)-[:BILLS]->(po:PurchaseOrder)<-[:BILLS]-(a)
OPTIONAL MATCH (pa:Payment)-[:SETTLES]->(a)
OPTIONAL MATCH (pb:Payment)-[:SETTLES]->(b)
OPTIONAL MATCH (la:BankLine)-[:CLEARS]->(pa)
OPTIONAL MATCH (lb:BankLine)-[:CLEARS]->(pb)
WITH a, b, v, po, collect(DISTINCT pa) AS pas, collect(DISTINCT pb) AS pbs, collect(DISTINCT la) AS las, collect(DISTINCT lb) AS lbs
RETURN 'duplicate-invoice' AS check,
       CASE WHEN size(pas) > 0 AND size(pbs) > 0 THEN 'high' ELSE 'medium' END AS severity,
       b.id AS invoice,
       'Duplicate of ' + a.id + CASE WHEN size(pas) > 0 AND size(pbs) > 0 THEN ', both paid' ELSE '' END AS headline,
       b.id + ' (' + b.vendor_inv_no + ', ' + b.date + ') and ' + a.id + ' (' + a.vendor_inv_no + ', ' + a.date + ') are the same ' +
       v.name + ' invoice for Rs ' + toString(a.total) +
       CASE WHEN po IS NULL THEN '' ELSE ' against ' + po.id END + '. ' +
       CASE WHEN size(pas) > 0 AND size(pbs) > 0
         THEN 'It was paid twice: ' + pas[0].id + CASE WHEN size(las) > 0 THEN ' (' + las[0].id + ')' ELSE '' END + ' and ' + pbs[0].id + CASE WHEN size(lbs) > 0 THEN ' (' + lbs[0].id + ')' ELSE '' END + '. Recover Rs ' + toString(b.total) + ' from the vendor.'
         ELSE 'Block the second copy before it is paid.' END AS detail,
       CASE WHEN size(pbs) > 0 THEN b.total ELSE 0 END AS amount,
       [a.id] + [p IN pas | p.id] + [l IN las | l.id] + CASE WHEN po IS NULL THEN [] ELSE [po.id] END + [b.id] + [p IN pbs | p.id] + [l IN lbs | l.id] AS path,
       null AS missing,
       null AS suggestion
