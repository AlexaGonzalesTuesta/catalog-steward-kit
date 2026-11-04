# Catalog Steward Kit

[![CI](https://github.com/AlexaGonzalesTuesta/catalog-steward-kit/actions/workflows/ci.yml/badge.svg)](https://github.com/AlexaGonzalesTuesta/catalog-steward-kit/actions/workflows/ci.yml)

Finds the governance gaps in a Databricks Unity Catalog (missing owners, missing descriptions, unreviewed personal data, failing quality rules), puts them in one work queue for data stewards, and turns every decision into SQL you can run in Databricks.

**[Open the live demo](https://alexagonzalestuesta.github.io/catalog-steward-kit/)**: a catalog of real NHTSA recall and complaint data and EPA fuel economy data for GM vehicles, plus two synthetic customer tables. Your decisions stay in your own browser.

![Steward confirming PII tags, assigning an owner, then checking catalog health and quality](https://alexagonzalestuesta.github.io/catalog-steward-kit/demo.gif)

## Why this exists

Every data catalog grows faster than its documentation. After a year, most tables have no accountable owner, no description, and nobody has checked whether they hold personal data. Data stewards usually find these gaps by clicking through the catalog table by table, and enterprise tools that automate it (Atlan, Immuta, Anomalo) cost far more than a small team can spend.

This kit gives a governance team the core of that workflow on the platform they already have:

1. **Scan** Unity Catalog's own `information_schema` for tables and columns with no owner, description or classification.
2. **Suggest** PII tags from column names and sampled values, with masked samples as evidence.
3. **Check** quality rules written in plain YAML, with a query that returns the failing rows.
4. **Review**: a steward confirms or rejects each suggestion and fills in owners and descriptions.
5. **Apply**: every decision becomes an `ALTER TABLE ... SET TAGS` or `COMMENT ON` statement for Databricks.

## What's different

- **A person approves every tag.** The classifier only suggests. Nothing is written to the catalog until a steward confirms it, and every decision is exported as reviewable SQL.
- **Evidence, not just a label.** Each suggestion shows why, for example "100% of 300 sampled values look like an email address", with masked samples such as `f***@example.net`, so the steward never sees the raw personal data.
- **Real data.** The public tables come from the NHTSA Recalls and Complaints APIs and EPA's fueleconomy.gov file, refreshed every Monday by GitHub Actions.
- **Same code, local or Databricks.** A DuckDB adapter mirrors Unity Catalog's `information_schema.tables`, `columns`, `table_tags` and `column_tags`, so the scan runs the same way on the demo and on a real workspace.
- **Measured.** The classifier and quality rules are scored against labeled ground truth on every CI run.

## 2-minute tour

1. Open the [live demo](https://alexagonzalestuesta.github.io/catalog-steward-kit/). The work queue lists every open item, highest priority first.
2. Click **confirm a suggested PII tag**. Read the evidence for `customer_care.owner_contacts.email`, look at the masked samples, and click **Confirm PII**. The **PII reviews open** count drops.
3. Find `dealer_service.service_appointments.customer_notes`. It is a free-text field, and the kit found phone numbers and emails typed into some notes. This is the kind of PII that column-name rules miss.
4. Click **assign a missing data owner**. The domain's default owner is filled in. Click **Set owner**.
5. Click **open a failing quality check**. The query shows the 7 service appointments that point to recall campaigns that do not exist.
6. Open **Catalog health** to see each table's description, owner, classification, PII review and quality status update as you decide.
7. Click **Download SQL**. The file contains one statement per decision, ready to run in a Databricks SQL editor.

## Results

From `python -m steward_kit eval` (also run in CI):

| Measure | Result |
|---|---|
| PII classifier on the demo catalog (67 columns, 9 PII) | Precision 1.00, recall 1.00, PII type correct for 9 of 9 |
| PII classifier on 20 hard cases (no name hints, business contacts, near-miss formats) | Precision 0.82, recall 1.00 |
| Quality rules vs. injected defects (duplicates, bad emails, bad VINs, orphan recall numbers, impossible dates, bad status values) | 6 of 6 rules found exactly the injected count |
| Governance-ready tables, before and after one full review | 1 of 5 before, 5 of 5 after |
| Scan time, local demo catalog | A few seconds |

The two hard-case false positives are `dealer_phone` and `support_email`: business contact details that look exactly like personal data. The kit flags them and the steward rejects them, which is the point of keeping a person in the loop.

## How it works

```
governance.yml ──┐
                 ▼
Unity Catalog ──► scan ──► classify (names + sampled values) ──► work queue ──► steward decisions ──► Databricks SQL
 (or DuckDB)      │                                                  ▲
                  └──────► quality rules (SQL) ──► failing rows ─────┘
```

| Path | What it does |
|---|---|
| `steward_kit/catalog.py` | Unity Catalog and DuckDB adapters with the same interface |
| `steward_kit/classify.py` | PII scoring, masking of samples |
| `steward_kit/quality.py` | Turns each rule into SQL for either dialect |
| `steward_kit/scan.py` | Builds the work queue, metrics and `site/data/snapshot.json` |
| `steward_kit/sources.py` | Downloads and normalizes NHTSA and EPA data |
| `steward_kit/synthetic.py` | Fictional customer and service tables with known defects |
| `governance.yml` | Domains, stewards, tag names, classification levels, quality rules |
| `site/` | The steward review screen (static HTML, CSS and JavaScript) |
| `databricks/` | SQL to recreate the demo catalog in a Databricks workspace |
| `docs/` | Steward quick start, job aid, metric definitions, tool mapping, Databricks setup |
| `evals/` | Ground-truth labels and hard cases |

## Run it locally

Windows Command Prompt, Python 3.9 or newer:

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt
python -m steward_kit fetch
python -m steward_kit build-demo
python -m steward_kit scan
python -m steward_kit eval
python -m pytest -q
python -m http.server -d site 8000
```

Then open http://localhost:8000. On macOS or Linux, activate with `source .venv/bin/activate`.

`fetch` downloads about 180 small API responses from NHTSA and one file from EPA, and takes a few minutes.

## Point it at your own Databricks workspace

Follow [docs/databricks-setup.md](docs/databricks-setup.md) to load the demo catalog into Databricks (Free Edition works), scan it from your laptop, and apply your decisions with the downloaded SQL.

To scan your own catalog instead, edit `governance.yml`: set `catalog`, list your schemas under `domains`, add your stewards, and write quality rules for your tables.

## Limitations and next steps

- **Sampling is simple.** The classifier reads the first 300 non-null values of each column, not a random sample. A column whose personal data starts deep in the table could be missed.
- **The rules are patterns, not a model.** Names in unusual formats, non-US phone numbers and addresses outside the US are likely to be missed. The hard-case eval shows where it is weakest.
- **Decisions are applied by running SQL.** The demo never writes to a catalog itself. A production version would write tags directly, with an approval log.
- **Steward onboarding status is typed into `governance.yml`.** A real team would pull it from its learning platform and access request system.
- **The customer and service tables are synthetic.** Every person is fictional, and the defects in those tables were injected on purpose so the quality rules can be measured.
- **Free Edition limits.** Databricks Free Edition has limited compute and no account-level APIs, so this demonstrates the workflow, not enterprise scale.

Next: column masks on confirmed PII columns, lineage so a PII tag on a source flags downstream tables, and anomaly checks on row counts.

## Why I built this

During my IT Business Analyst internship at Abbott, I built a Power BI dashboard on Azure Synapse query logs so the team could decide which BI views to migrate to Databricks, review or retire. I also wrote the development standards for the company's Power Apps governance documentation. Both projects taught me that the hard part of a platform move is not the technology. It is knowing who owns each dataset, what it is for, and whether it holds sensitive data. I wanted to build the tool I wished existed then: one place where a steward can see every gap, decide quickly with real evidence, and hand engineering something they can run.

## How I built it

I started from what a data steward actually does each week and wrote the work queue around those decisions. To make it work on Unity Catalog without a paid workspace, I mirrored Unity Catalog's `information_schema` in DuckDB, then wrote a second adapter for a Databricks SQL warehouse, so the same scan runs in both places. I used real NHTSA and EPA data for GM vehicles because those are tables an automotive data team would actually hold, and I generated the customer tables synthetically so no real person's data is ever in the repo. I measured the classifier against labeled columns and a set of deliberately tricky cases, and I kept the false positives in the results because they show why a person has to approve every tag.
