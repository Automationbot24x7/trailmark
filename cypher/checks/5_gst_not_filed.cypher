// title: Tax credit claimed, supplier never filed
// plain: We claimed the GST input credit on this invoice, but the supplier never reported it in their return, so the credit can be reversed with interest.
// graph: Invoice {itc_claimed: true} with no incoming REPORTS from a GstrLine, while the same supplier's other invoices are reported - so it is this invoice, not the supplier, that is missing.
MATCH (i:Invoice {itc_claimed: true})-[:ISSUED_BY]->(v:Vendor)
WHERE NOT EXISTS { (:GstrLine)-[:REPORTS]->(i) }
OPTIONAL MATCH (other:GstrLine)-[:REPORTS]->(:Invoice)-[:ISSUED_BY]->(v)
OPTIONAL MATCH (p:Payment)-[:SETTLES]->(i)
WITH i, v, collect(DISTINCT other) AS filed, collect(DISTINCT p.id) AS payments
RETURN 'gst-not-filed' AS check,
       'medium' AS severity,
       i.id AS invoice,
       'GST credit Rs ' + toString(i.gst) + ' at risk' AS headline,
       'We claimed Rs ' + toString(i.gst) + ' input tax credit on ' + i.id + ' (' + v.name + ' ' + i.vendor_inv_no + ', ' + i.date +
       '), but the supplier never reported it in GSTR-2B. ' +
       CASE WHEN size(filed) > 0 THEN 'They did report ' + toString(size(filed)) + ' other invoice(s) to us, so this one was skipped. '
            ELSE 'They have not reported any invoice to us. ' END +
       CASE WHEN size(payments) > 0 THEN 'The invoice is already paid (' + payments[0] + '), so ask the supplier to file or hold the credit.'
            ELSE 'Hold the payment until they file.' END AS detail,
       i.gst AS amount,
       [v.id, i.id] + payments AS path,
       {after: i.id, label: 'GstrLine', text: 'expected: supplier reports ' + i.vendor_inv_no + ' in GSTR-2B'} AS missing,
       null AS suggestion
