// title: Payment came back from the bank
// plain: One payment can settle several invoices and leave the bank as several debits. If a debit is later returned, the books still say "paid" but the money never reached the vendor.
// graph: Invoice <-SETTLES- Payment <-CLEARS- BankLine, then a quantified path pattern follows any chain of REVERSES lines back. The shortfall is charged to the latest invoices first.
MATCH (p:Payment)<-[:CLEARS]-(out:BankLine)
OPTIONAL MATCH (out)((:BankLine)<-[:REVERSES]-(:BankLine)){1,3}(back:BankLine)
WITH p, collect(DISTINCT out) AS debits, collect(DISTINCT back) AS returns
WITH p, debits, returns,
     reduce(s = 0, b IN debits | s + b.amount) - reduce(s = 0, b IN returns | s + b.amount) AS net
WHERE size(returns) > 0 AND net < p.amount
MATCH (p)-[a:SETTLES]->(i:Invoice)
WITH p, debits, returns, net, i, a ORDER BY i.date DESC
WITH p, debits, returns, net, collect({inv: i, amt: a.amount}) AS allocs
UNWIND range(0, size(allocs) - 1) AS k
WITH p, debits, returns, net, allocs, k,
     p.amount - net - reduce(s = 0, x IN allocs[0..k] | s + x.amt) AS left_before
WITH p, debits, returns, net, allocs, allocs[k].inv AS i,
     CASE WHEN left_before <= 0 THEN 0
          WHEN left_before >= allocs[k].amt THEN allocs[k].amt
          ELSE left_before END AS unpaid
WHERE unpaid > 0
RETURN 'payment-returned' AS check,
       'high' AS severity,
       i.id AS invoice,
       'Marked paid, Rs ' + toString(unpaid) + ' came back' AS headline,
       p.id + ' settles ' + toString(size(allocs)) + ' invoices for Rs ' + toString(p.amount) + '. It left the bank as ' +
       toString(size(debits)) + ' debits; ' + reduce(s = '', b IN returns | s + b.id + ' (' + b.date + ', Rs ' + toString(b.amount) + ') ') +
       'returned the money: "' + returns[0].narration + '". Only Rs ' + toString(net) + ' actually left. ' +
       i.id + ' is the latest invoice on the payment, so Rs ' + toString(unpaid) + ' of it is still owed.' AS detail,
       unpaid AS amount,
       [i.id, p.id] + [b IN debits | b.id] + [b IN returns | b.id] AS path,
       null AS missing,
       null AS suggestion
