// Trailmark schema: one uniqueness constraint per document type, plus a vector
// index over receipt item text (used to suggest which receipt belongs to a PO).
CREATE CONSTRAINT vendor_id IF NOT EXISTS FOR (n:Vendor) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT employee_id IF NOT EXISTS FOR (n:Employee) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT account_id IF NOT EXISTS FOR (n:BankAccount) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT change_id IF NOT EXISTS FOR (n:BankChange) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT po_id IF NOT EXISTS FOR (n:PurchaseOrder) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT grn_id IF NOT EXISTS FOR (n:GoodsReceipt) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT invoice_id IF NOT EXISTS FOR (n:Invoice) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT payment_id IF NOT EXISTS FOR (n:Payment) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT bankline_id IF NOT EXISTS FOR (n:BankLine) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT gstr_id IF NOT EXISTS FOR (n:GstrLine) REQUIRE n.id IS UNIQUE;
CREATE VECTOR INDEX grn_item IF NOT EXISTS FOR (g:GoodsReceipt) ON g.item_vec WITH [g.vendor_id];
