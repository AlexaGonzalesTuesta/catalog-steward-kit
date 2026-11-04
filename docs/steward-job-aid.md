# Steward job aid (one page)

## Classification levels

| Level | Use it when | Examples in this catalog |
|---|---|---|
| `public` | The data is already published or meant to be | NHTSA recalls, EPA fuel economy ratings |
| `internal` | Business data with no personal data, not for outside sharing | Dealer codes, appointment status |
| `confidential` | Harmful to the business if leaked | Supplier pricing, unreleased product plans |
| `restricted` | Any column identifies or contacts a person | Owner names, emails, phones, addresses, VINs tied to an owner |

A table takes the level of its most sensitive column.

## Is this column personal data?

Choose **Confirm PII** when the value, alone or joined with the rest of the row, points to one person:

- Names, emails, phone numbers, street addresses and postal codes in a customer table
- VINs in a table that also holds owner details (a VIN in a public recall table is not tied to a person)
- Free-text notes where people typed phone numbers or emails

Choose **Not PII** for shared business contacts (`support@`, a dealer's main line), partial VINs, and public data.

If you are not sure, do not guess. Escalate.

## Writing a table description

Answer three things in one or two sentences: what the table holds, what one row is, and where it comes from.

> NHTSA safety recall campaigns for GM vehicles, one row per campaign per make, model and model year. Loaded weekly from the NHTSA Recalls API.

## Escalation

| Question | Route to |
|---|---|
| Can we keep or share this personal data? | Privacy office |
| Who should get access to this table? | Data owner, then the access request process |
| A quality rule keeps failing | Data producer named in the table description |
| The kit flagged something odd or a rule errors | Governance engineering |
| Policy or classification is unclear | Governance lead |
