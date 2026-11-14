// title: The trail of one invoice
// plain: Everything an accountant would pull to tie out one invoice: the vendor, the PO, every receipt on it, every payment and the other invoices it covers, every bank line, returns, the GSTR-2B line, and where the money went.
// graph: A quantified path pattern of 0-3 hops over the document links, which never walks through another invoice or a bank account (so a vendor's other work stays out), plus any extra nodes a finding points at ($extra).
MATCH (i:Invoice {id: $id})-[:ISSUED_BY]->(v:Vendor)
MATCH p = (i)(()-[:BILLS|RECEIVED_AGAINST|SETTLES|CLEARS|REVERSES|REPORTS|PAID_TO]-()){0,3}(n)
WHERE none(x IN nodes(p)[1..-1] WHERE x:Invoice OR x:BankAccount)
WITH v, collect(DISTINCT n) AS walked
OPTIONAL MATCH (x) WHERE x.id IN $extra
WITH walked, v, collect(DISTINCT x) AS pointed
UNWIND walked + [v] + pointed AS a
WITH collect(DISTINCT a) AS ns
UNWIND ns AS a
OPTIONAL MATCH (a)-[r]->(b) WHERE b IN ns
WITH ns, collect(DISTINCT CASE WHEN r IS NULL THEN null ELSE {from: a.id, to: b.id, type: type(r), props: properties(r)} END) AS rels
RETURN [n IN ns | {id: n.id, label: labels(n)[0], props: properties(n)}] AS nodes, rels
