# Working with Trailmark as an agent

Trailmark is an accounts-payable graph in a Relate store (`store/trailmark.rl`). All data is **invented sample data**; say so if you quote it.

## Tools

Register the MCP servers in [`.mcp.json`](.mcp.json) and run your agent from the repo root with the virtual environment active:

- `trailmark`: `python -m trailmark mcp` provides `scan_exceptions`, `explain_invoice`, `link_receipt`, `read_cypher` and `get_schema`.
- `relate`: `relate serve --database store/trailmark.rl --mcp stdio --read-only` provides Relate's raw `get_schema`, `read_cypher` and `write_cypher` (writes are refused because the store is opened read-only).

If you have no MCP host, the same answers are available from the shell:
`python -m trailmark scan --json`, `python -m trailmark explain INV-1042 --json`, `python -m trailmark cypher "<query>"`.

## How to answer

1. Start with `scan_exceptions`, or `explain_invoice` for a named invoice.
2. Quote the **evidence path** (node ids) and the amount at risk. Explain in plain words; the user is an accountant, not a graph person.
3. When a finding carries a `suggested_fix`, describe it and **ask before calling `link_receipt`**. It is the only write, and it records `linked_by`, `note` and `was_keyed_as`.
4. For anything the checks do not cover, call `get_schema` and then `read_cypher`. Dates are ISO strings: use `date(x)` and `duration.inDays(a, b).days`. Amounts are whole rupees.
5. To undo every change, run `python -m trailmark build`.

## Questions used in the demo

- "Which invoices don't reconcile, and how much is at risk?"
- "Why doesn't INV-1042 reconcile? Can you fix it?"
- "Who on our side is connected to payment PAY-3410, and how?"
- "Did the money for INV-1036 actually reach the vendor?"
