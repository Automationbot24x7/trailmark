// title: Link a goods receipt to the PO it belongs to
// plain: The one write Trailmark makes. It only links a receipt that is linked to nothing, to a PO from the same vendor, and it records who linked it, why, and what the receipt was keyed as.
MATCH (g:GoodsReceipt {id: $grn})
MATCH (po:PurchaseOrder {id: $po})
WHERE g.vendor_id = po.vendor_id AND NOT EXISTS { (g)-[:RECEIVED_AGAINST]->() }
CREATE (g)-[r:RECEIVED_AGAINST {linked_by: $by, note: $note, at: $at, was_keyed_as: g.po_ref}]->(po)
RETURN g.id AS grn, po.id AS po, r.was_keyed_as AS was_keyed_as, r.linked_by AS linked_by
