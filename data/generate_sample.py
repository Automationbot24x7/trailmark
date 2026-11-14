"""Generate the SAMPLE accounts-payable ledgers in data/sample/*.csv.

Everything here is invented: the buyer, the vendors, the people, GSTINs, bank
accounts and amounts. GSTINs carry "SAMPL" in the PAN slot and IFSC codes start
with "SMPL" so nothing can be mistaken for a real registration or account.

The six broken trails are written out by hand (one block each, marked SCENARIO);
the clean trails around them come from a small seeded helper so the graph has
ordinary, reconciling work around the exceptions.

Run:  python data/generate_sample.py   (rewrites data/sample/*.csv)
"""
import csv
import random
from datetime import date, timedelta
from pathlib import Path

OUT = Path(__file__).resolve().parent / "sample"
AS_OF = date(2026, 10, 31)
GST = 0.18
rng = random.Random(1142)

tables = {k: [] for k in [
    "vendors", "employees", "bank_accounts", "vendor_accounts", "employee_accounts",
    "bank_changes", "purchase_orders", "goods_receipts", "invoices", "payments",
    "allocations", "bank_lines", "gstr2b",
]}


def d(s):
    return date.fromisoformat(s)


def iso(x):
    return x.isoformat()


def gstin(state, n):
    return f"{state}SAMPL{n:04d}{'ABCDEFGHJK'[n % 10]}1Z{n % 9 + 1}"


def money(x):
    return int(round(x))


# ---------------------------------------------------------------- master data
VENDORS = [
    ("V-101", "Kaveri Packaging Works", "Pune", "27", 30),
    ("V-102", "Northline Logistics", "Nashik", "27", 15),
    ("V-103", "Sahyadri Steel Fabricators", "Satara", "27", 30),
    ("V-104", "Bluefin Office Supplies", "Mumbai", "27", 15),
    ("V-105", "Meridian Chemicals", "Vapi", "24", 30),
    ("V-106", "Tapti Electricals", "Surat", "24", 30),
    ("V-107", "Coastal Print House", "Panaji", "30", 30),
    ("V-108", "Arjun Facility Services", "Pune", "27", 15),
    ("V-109", "Greenleaf Pallets", "Nagpur", "27", 30),
    ("V-110", "Ridgeway Tools & Hardware", "Bengaluru", "29", 30),
    ("V-111", "Saffron Canteen Services", "Pune", "27", 15),
    ("V-112", "Orbit IT Peripherals", "Hyderabad", "36", 30),
]
for i, (vid, name, city, state, terms) in enumerate(VENDORS, start=1):
    tables["vendors"].append(dict(id=vid, name=name, city=city, gstin=gstin(state, 100 + i), terms_days=terms))
GSTIN = {v["id"]: v["gstin"] for v in tables["vendors"]}
TERMS = {v["id"]: v["terms_days"] for v in tables["vendors"]}

EMPLOYEES = [
    ("E-01", "Neha Joshi", "Finance Controller"),
    ("E-02", "Karan Mehta", "AP Lead"),
    ("E-03", "Priya Nair", "Purchase Manager"),
    ("E-04", "Arvind Rao", "Treasury"),
    ("E-05", "Divya Menon", "Stores In-charge"),
    ("E-06", "Sameer Patil", "AP Clerk"),
    ("E-07", "Pooja Kulkarni", "AP Clerk"),
    ("E-08", "Imran Sheikh", "Admin"),
]
for eid, name, role in EMPLOYEES:
    tables["employees"].append(dict(id=eid, name=name, role=role))

BANKS = ["Western Coast Bank", "Deccan Co-operative Bank", "Konkan Commercial Bank"]


def account(last4, bank_i):
    acc = dict(id=f"BA-{last4}", bank=BANKS[bank_i % 3], last4=last4, ifsc=f"SMPL000{last4}")
    tables["bank_accounts"].append(acc)
    return acc["id"]


for i, v in enumerate(VENDORS):
    acc = account(f"{4400 + i * 7:04d}", i)
    tables["vendor_accounts"].append(dict(vendor_id=v[0], account_id=acc, since="2025-04-01"))
for i, e in enumerate(EMPLOYEES):
    acc = account(f"{8800 + i * 13:04d}", i + 1)
    tables["employee_accounts"].append(dict(employee_id=e[0], account_id=acc, purpose="salary"))

# ---------------------------------------------------------------- helpers
counter = {"po": 7600, "grn": 5400, "pay": 3200, "bl": 800, "g2b": 100, "inv": 1000}


def nxt(kind, prefix, width=4):
    counter[kind] += 1
    return f"{prefix}-{counter[kind]:0{width}d}"


def po(vendor, day, item, qty, rate, pid=None):
    taxable = qty * rate
    row = dict(id=pid or nxt("po", "PO"), vendor_id=vendor, date=day, item=item, qty=qty, rate=rate,
               taxable=money(taxable), gst=money(taxable * GST), total=money(taxable * (1 + GST)))
    tables["purchase_orders"].append(row)
    return row


def grn(po_ref, vendor, day, item, qty, gid=None):
    row = dict(id=gid or nxt("grn", "GRN"), po_ref=po_ref, vendor_id=vendor, date=day, item=item, qty=qty)
    tables["goods_receipts"].append(row)
    return row


def invoice(iid, vendor, vendor_no, po_id, day, qty, rate, itc=True, kind="invoice"):
    taxable = qty * rate
    row = dict(id=iid, vendor_id=vendor, vendor_inv_no=vendor_no, po_id=po_id, date=day, qty=qty,
               taxable=money(taxable), gst=money(taxable * GST), total=money(taxable * (1 + GST)),
               itc_claimed="true" if itc else "false", kind=kind)
    tables["invoices"].append(row)
    return row


def payment(day, amount, account_id, approved_by, pid=None, utr=None):
    row = dict(id=pid or nxt("pay", "PAY"), date=day, amount=money(amount), account_id=account_id,
               approved_by=approved_by, utr=utr or f"SMPLN{rng.randint(10**9, 10**10 - 1)}")
    tables["payments"].append(row)
    return row


def allocate(pay, inv, amount):
    tables["allocations"].append(dict(payment_id=pay["id"], invoice_id=inv["id"], amount=money(amount)))


def bank_line(day, amount, direction, narration, utr, bid=None):
    row = dict(id=bid or nxt("bl", "BL", 4), date=day, amount=money(amount), direction=direction,
               narration=narration, utr=utr)
    tables["bank_lines"].append(row)
    return row


def g2b(vendor, inv, period=None):
    tables["gstr2b"].append(dict(id=nxt("g2b", "G2B", 4), period=period or inv["date"][:7],
                                 supplier_gstin=GSTIN[vendor], vendor_inv_no=inv["vendor_inv_no"],
                                 taxable=inv["taxable"], tax=inv["gst"]))


VENDOR_ACC = {r["vendor_id"]: r["account_id"] for r in tables["vendor_accounts"]}
VNAME = {v[0]: v[1] for v in VENDORS}


def pay_full(invs, day, vendor, approved_by="E-04", pid=None):
    amt = sum(i["total"] for i in invs)
    p = payment(day, amt, VENDOR_ACC[vendor], approved_by, pid=pid)
    for i in invs:
        allocate(p, i, i["total"])
    bank_line(day, amt, "debit", f"NEFT {p['utr']} {VNAME[vendor].upper()[:24]}", p["utr"])
    return p


def clean_trail(vendor, po_day, item, qty, rate, inv_no):
    """An ordinary trail: PO -> receipt -> invoice -> (payment -> bank) -> GSTR-2B."""
    p = po(vendor, po_day, item, qty, rate)
    g_day = d(po_day) + timedelta(days=rng.randint(4, 8))
    grn(p["id"], vendor, iso(g_day), item, qty)
    i_day = g_day + timedelta(days=rng.randint(1, 4))
    inv = invoice(nxt("inv", "INV"), vendor, inv_no, p["id"], iso(i_day), qty, rate)
    g2b(vendor, inv)
    due = i_day + timedelta(days=TERMS[vendor])
    if due <= AS_OF:
        pay_full([inv], iso(due - timedelta(days=rng.randint(0, 3))), vendor)
    return inv


# ---------------------------------------------------------------- clean work
CLEAN = [
    ("V-101", "2026-09-01", "Corrugated box 5-ply 18x12x12", 800, 42, "KPW/1981"),
    ("V-101", "2026-10-12", "Stretch film roll 23 micron", 60, 950, "KPW/2033"),
    ("V-102", "2026-09-04", "Line haul Pune-Nashik, 9T truck", 6, 18000, "NL-288"),
    ("V-103", "2026-09-08", "MS angle bracket 50x50", 300, 210, "SSF/0987"),
    ("V-104", "2026-09-10", "Toner cartridge 88A", 24, 1450, "BOS/861"),
    ("V-105", "2026-09-03", "Isopropyl alcohol 99%, 200L drum", 6, 21500, "MC-2181"),
    ("V-106", "2026-09-15", "LED panel light 2x2 40W", 120, 1350, "TE/4410"),
    ("V-106", "2026-10-14", "Copper cable 4 sq mm, 90m coil", 15, 6200, "TE/4472"),
    ("V-107", "2026-09-18", "Product leaflet A5, 4 colour", 20000, 2, "CPH-731"),
    ("V-108", "2026-09-01", "Housekeeping contract, September", 1, 145000, "AFS-541"),
    ("V-109", "2026-09-06", "Heat-treated pallet 1200x1000", 250, 780, "GP/3302"),
    ("V-109", "2026-10-09", "Heat-treated pallet 1200x1000", 300, 780, "GP/3367"),
    ("V-110", "2026-09-12", "Torque wrench 40-200 Nm", 8, 7400, "RTH-1190"),
    ("V-111", "2026-09-01", "Canteen services, September", 1, 212000, "SCS/09-26"),
    ("V-111", "2026-10-01", "Canteen services, October", 1, 218000, "SCS/10-26"),
    ("V-112", "2026-09-20", "USB-C docking station", 30, 8900, "OIP/7716"),
    ("V-112", "2026-10-15", "27-inch monitor IPS", 20, 14500, "OIP/7790"),
]
for row in CLEAN:
    clean_trail(*row)

# ---------------------------------------------------------------- SCENARIO 1
# Missing receipt that is really a keying error. The goods arrived, but stores
# keyed the receipt against PO-7731 (does not exist) instead of PO-7713.
p1 = po("V-103", "2026-10-06", "MS angle bracket 50x50", 400, 210, pid="PO-7713")
grn("PO-7731", "V-103", "2026-10-15", "MS angle brkt 50 x 50 mm", 400, gid="GRN-5520")
i1 = invoice("INV-1042", "V-103", "SSF/1042", "PO-7713", "2026-10-20", 400, 210)
g2b("V-103", i1)

# ---------------------------------------------------------------- SCENARIO 2
# Billed for 1,000 boxes, two partial receipts add up to 900. Paid in full.
p2 = po("V-101", "2026-09-26", "Corrugated box 5-ply 18x12x12", 1000, 42, pid="PO-7720")
grn("PO-7720", "V-101", "2026-10-03", "Corrugated box 5-ply 18x12x12", 600, gid="GRN-5531")
grn("PO-7720", "V-101", "2026-10-10", "Corrugated box 5-ply 18x12x12", 300, gid="GRN-5538")
i2 = invoice("INV-1038", "V-101", "KPW/2290", "PO-7720", "2026-10-11", 1000, 42)
g2b("V-101", i2)
pay_full([i2], "2026-10-25", "V-101", pid="PAY-3388")

# ---------------------------------------------------------------- SCENARIO 3
# One payment covers three invoices. The bank split it into two debits and the
# second one came back three days later (beneficiary account closed).
trips = []
for inv_id, po_day, inv_no, inv_day, trips_n in [("INV-1033", "2026-09-22", "NL-311", "2026-09-30", 5),
                                         ("INV-1035", "2026-09-29", "NL-317", "2026-10-04", 7),
                                         ("INV-1036", "2026-10-02", "NL-322", "2026-10-07", 9)]:
    pp = po("V-102", po_day, "Line haul Pune-Nashik, 9T truck", trips_n, 20000)
    grn(pp["id"], "V-102", inv_day, "Line haul Pune-Nashik, 9T truck", trips_n)
    inv = invoice(inv_id, "V-102", inv_no, pp["id"], inv_day, trips_n, 20000)
    g2b("V-102", inv)
    trips.append(inv)
p3 = payment("2026-10-18", sum(i["total"] for i in trips), VENDOR_ACC["V-102"], "E-04", pid="PAY-3301",
             utr="SMPLN4718830192")
for inv in trips:
    allocate(p3, inv, inv["total"])
bank_line("2026-10-18", 300000, "debit", "NEFT SMPLN4718830192 NORTHLINE LOGISTICS 1/2", p3["utr"], bid="BL-0918")
bank_line("2026-10-18", p3["amount"] - 300000, "debit", "NEFT SMPLN4718830192 NORTHLINE LOGISTICS 2/2",
          p3["utr"], bid="BL-0919")
bank_line("2026-10-21", p3["amount"] - 300000, "credit",
          "NEFT RETURN SMPLN4718830192 BENEFICIARY A/C CLOSED", p3["utr"], bid="BL-0961")

# ---------------------------------------------------------------- SCENARIO 4
# The same invoice keyed twice (once from the courier copy, once from email).
p4 = po("V-104", "2026-09-28", "A4 copier paper 75 gsm, ream", 240, 200, pid="PO-7702")
grn("PO-7702", "V-104", "2026-10-03", "A4 copier paper 75 gsm, ream", 240, gid="GRN-5512")
i4a = invoice("INV-1039", "V-104", "BOS/889", "PO-7702", "2026-10-05", 240, 200)
i4b = invoice("INV-1040", "V-104", "BOS-889", "PO-7702", "2026-10-09", 240, 200)
g2b("V-104", i4a)
pay_full([i4a], "2026-10-14", "V-104", approved_by="E-04", pid="PAY-3352")
pay_full([i4b], "2026-10-16", "V-104", approved_by="E-04", pid="PAY-3361")

# ---------------------------------------------------------------- SCENARIO 5
# We claimed the input tax credit; the supplier never reported the invoice.
p5 = po("V-105", "2026-09-24", "Isopropyl alcohol 99%, 200L drum", 10, 24000, pid="PO-7724")
grn("PO-7724", "V-105", "2026-10-01", "Isopropyl alcohol 99%, 200L drum", 10, gid="GRN-5527")
i5 = invoice("INV-1041", "V-105", "MC-2207", "PO-7724", "2026-10-02", 10, 24000)
pay_full([i5], "2026-10-28", "V-105", pid="PAY-3399")
# (no g2b line for MC-2207 on purpose)

# ---------------------------------------------------------------- SCENARIO 6
# Vendor bank details changed six days before a large payment; the new account
# is also on an employee's record. Contrast: Tapti's change in August is routine.
new_acc = "BA-8865"  # Sameer Patil's salary account (E-06)
assert any(r["account_id"] == new_acc and r["employee_id"] == "E-06" for r in tables["employee_accounts"])
tables["vendor_accounts"].append(dict(vendor_id="V-108", account_id=new_acc, since="2026-10-17"))
tables["bank_changes"].append(dict(id="BC-0077", vendor_id="V-108", old_account_id=VENDOR_ACC["V-108"],
                                   new_account_id=new_acc, date="2026-10-17", entered_by="E-06",
                                   approved_by="E-02", reason="Vendor letter: bank migrated"))
tapti_new = account("4471", 2)
tables["vendor_accounts"].append(dict(vendor_id="V-106", account_id=tapti_new, since="2026-08-04"))
tables["bank_changes"].append(dict(id="BC-0061", vendor_id="V-106", old_account_id=VENDOR_ACC["V-106"],
                                   new_account_id=tapti_new, date="2026-08-04", entered_by="E-07",
                                   approved_by="E-02", reason="Cancelled cheque on file, call-back done"))
p6 = po("V-108", "2026-10-01", "Housekeeping contract, Q4 advance", 1, 754237, pid="PO-7730")
grn("PO-7730", "V-108", "2026-10-01", "Housekeeping contract, Q4 advance", 1, gid="GRN-5523")
i6 = invoice("INV-1037", "V-108", "AFS-560", "PO-7730", "2026-10-05", 1, 754237)
g2b("V-108", i6)
p6pay = payment("2026-10-23", i6["total"], new_acc, "E-06", pid="PAY-3410", utr="SMPLN5530917744")
allocate(p6pay, i6, i6["total"])
bank_line("2026-10-23", i6["total"], "debit", "NEFT SMPLN5530917744 ARJUN FACILITY SERVICES", p6pay["utr"],
          bid="BL-0977")

# ---------------------------------------------------------------- write
OUT.mkdir(parents=True, exist_ok=True)
for name, rows in tables.items():
    with open(OUT / f"{name}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"{name:18} {len(rows):4} rows")
