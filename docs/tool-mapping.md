# How this maps to enterprise governance tools

Enterprise teams usually split this work across several products. This kit does the core of each one on Unity Catalog, so the concepts carry over directly.

| Steward task | In this kit | Atlan | Immuta | Anomalo | Databricks native |
|---|---|---|---|---|---|
| Find tables with no owner or description | Catalog scan, work queue | Asset profile, completeness | | | Catalog Explorer |
| Suggest PII classifications | Name and value classifier with masked samples | Auto-classification | Sensitive data discovery | | Data classification (where enabled) |
| Human approval before tagging | Confirm PII / Not PII, then SQL | Approval workflows | Policy approvals | | |
| Write tags and comments | `ALTER TABLE ... SET TAGS`, `COMMENT ON` | Syncs tags to Databricks | Reads tags for policies | | Unity Catalog tags |
| Quality rules and failing rows | `governance.yml` rules run as SQL | Shows results from DQ tools | | Rules, anomaly detection, root cause | Lakeflow expectations, data quality monitoring |
| Steward onboarding and readiness | Stewards page, quick start | Personas, onboarding | | | |
| Governance metrics | KPI strip, catalog health | Reporting center | Audit | Monitoring | System tables |

## What a production version adds

- Column masks on `restricted` columns once a steward confirms PII (Unity Catalog `SET MASK`, or Immuta policies)
- Lineage, so a PII tag on a source flags its downstream tables
- Statistical anomaly detection on volumes and distributions, not only fixed rules
- Writing decisions straight to Unity Catalog with an approval log, instead of downloading SQL
