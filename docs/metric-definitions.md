# Metric definitions

Every number on the review screen, how it is calculated, and where it comes from.

| Metric | Definition | Source |
|---|---|---|
| Governance-ready tables | Tables with a description, a `data_owner` tag, a `classification` tag and no open PII reviews | `information_schema.tables` (comment), `information_schema.table_tags`, classifier output |
| PII reviews open | Text columns without a `classification` tag whose PII score is at or above `pii_suggestion_threshold` (0.5) | `information_schema.columns`, `column_tags`, sampled values |
| Failing quality checks | Rules in `governance.yml` whose query returns at least one failing row, or whose freshness limit is exceeded | Rule SQL run against each table |
| Stewards ready to review | Stewards with required learning, catalog access and first review all marked done | `stewards` in `governance.yml` |
| Columns described | Columns with a non-empty comment, out of all columns in the table | `information_schema.columns.comment` |

## PII score

`score = 0.35 x (column name matches a PII pattern) + 0.65 x (share of sampled values that match the pattern)`

- Up to 300 non-null values are sampled per column.
- A name match alone scores 0.35, which is below the threshold, so a column needs evidence in its values.
- Free-text columns score `0.35 + 0.65 x min(1, 8 x share of entries containing an email or phone number)`, because even a few entries with personal data put the column at risk.
- Toll-free numbers (800, 833, 844, 855, 866, 877, 888) are business lines and never count as personal data. This keeps the NHTSA hotline printed in every recall notice from being flagged.
- Priority is high at 0.8 or above, and medium from 0.5 to 0.8.

## Quality rule results

| Check | Failing rows means |
|---|---|
| `not_null` | Rows where the column is null |
| `unique` | Rows beyond the first for each duplicated key |
| `accepted_values` | Non-null values outside the list |
| `range` | Non-null values below `min` or above `max` |
| `pattern` | Non-null values that do not fully match the regular expression |
| `relationship` | Non-null values with no match in the referenced column |
| `condition` | Rows where the condition is false |
| `freshness` | No row count. Fails when the newest date is older than `max_age_days` |

A rule that cannot run (missing column, bad SQL) is reported as **Error**, not as a failure, and does not stop the scan.
