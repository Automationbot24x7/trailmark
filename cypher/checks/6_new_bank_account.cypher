// title: Large payment to a just-changed bank account
// plain: The vendor's bank details changed shortly before a large payment. Then follow every short path from that payment to our own people: who approved it, who entered the new account, who owns it.
// graph: Payment -PAID_TO-> BankAccount <-HAS_ACCOUNT {since}- Vendor, then a quantified path pattern of 1-3 hops over PAID_TO|HAS_ACCOUNT|NEW_ACCOUNT|ENTERED|APPROVED from the Payment to any Employee.
// next: Hold further payments to this account, call the vendor on a known number to confirm the change, and escalate to internal audit.
MATCH (i:Invoice)<-[:SETTLES]-(p:Payment)-[:PAID_TO]->(ba:BankAccount)<-[h:HAS_ACCOUNT]-(v:Vendor)
WHERE p.amount >= 500000 AND duration.inDays(date(h.since), date(p.date)).days <= 14
OPTIONAL MATCH (c:BankChange)-[:NEW_ACCOUNT]->(ba)
OPTIONAL MATCH path = (p)((x)-[:PAID_TO|HAS_ACCOUNT|NEW_ACCOUNT|ENTERED|APPROVED]-(y)){1,3}(e:Employee)
WITH i, p, ba, h, v, c, e, collect(DISTINCT [r IN relationships(path) | type(r)]) AS routes
WITH i, p, ba, h, v, c, e, routes,
     CASE WHEN any(rt IN routes WHERE rt = ['PAID_TO', 'HAS_ACCOUNT']) THEN 'owns the receiving account' END AS owns,
     CASE WHEN any(rt IN routes WHERE rt = ['APPROVED']) THEN 'approved the payment' END AS approved,
     CASE WHEN any(rt IN routes WHERE rt = ['PAID_TO', 'NEW_ACCOUNT', 'ENTERED']) THEN 'entered the new bank details' END AS entered,
     CASE WHEN any(rt IN routes WHERE rt = ['PAID_TO', 'NEW_ACCOUNT', 'APPROVED']) THEN 'approved the bank change' END AS ok_change
WITH i, p, ba, h, v, c,
     collect(CASE WHEN e IS NULL THEN null ELSE {id: e.id, name: e.name, role: e.role,
                  roles: [x IN [owns, approved, entered, ok_change] WHERE x IS NOT NULL]} END) AS people
WITH i, p, ba, h, v, c, people, [x IN people WHERE 'owns the receiving account' IN x.roles] AS owners
RETURN 'new-bank-account' AS check,
       CASE WHEN size(owners) > 0 THEN 'high' ELSE 'medium' END AS severity,
       i.id AS invoice,
       CASE WHEN size(owners) > 0 THEN 'Paid to an employee\'s account' ELSE 'Paid to a bank account added ' +
            toString(duration.inDays(date(h.since), date(p.date)).days) + ' days earlier' END AS headline,
       p.id + ' paid Rs ' + toString(p.amount) + ' to account ' + ba.id + ' on ' + p.date + '. ' + v.name + ' switched to that account on ' +
       h.since + ', ' + toString(duration.inDays(date(h.since), date(p.date)).days) + ' days earlier' +
       CASE WHEN c IS NULL THEN '. ' ELSE ' (' + c.id + ': "' + c.reason + '"). ' END +
       reduce(s = '', x IN people | s + x.name + ' (' + x.role + ') ' +
              reduce(t = '', r IN x.roles | t + CASE WHEN t = '' THEN '' ELSE ', ' END + r) + '. ') AS detail,
       p.amount AS amount,
       [i.id, p.id, ba.id] + CASE WHEN c IS NULL THEN [] ELSE [c.id] END + [x IN people | x.id] + [v.id] AS path,
       null AS missing,
       null AS suggestion
