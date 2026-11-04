# Data steward quick start

For new data stewards. Finish all three onboarding steps before you take review work. Plan on about two hours in total.

## 1. Required learning (about 60 minutes)

| Module | You can answer |
|---|---|
| Data classification levels | What makes a table `public`, `internal`, `confidential` or `restricted`? |
| Personal data basics | Why is a VIN personal data in an owner table but not in a recall table? |
| Writing catalog descriptions | What does a good table description say in its first sentence? |
| Quality rules | What is the difference between a failing rule and a broken rule? |

Your governance lead marks this step done in `governance.yml` (`required_learning: true`).

## 2. Catalog access (requested on day 1, approved within about 2 business days)

Ask your governance lead to grant you these privileges on your domain's schema:

| Privilege | Why you need it |
|---|---|
| `USE CATALOG`, `USE SCHEMA` | To see the schema |
| `SELECT` | To check sample values and run failing-rows queries |
| `APPLY TAG` | To write classification and owner tags |
| `MODIFY` | To write table and column comments |

Never ask for access to a domain you do not steward. Approval is recorded as `catalog_access: true`.

## 3. First review with a mentor (about 45 minutes)

Open the work queue, set the **Steward** filter to your name, and resolve five items while a mentor watches:

1. One **PII review**: read the evidence and the masked samples, then choose **Confirm PII** or **Not PII**.
2. One **Data owner**: confirm the suggested owner with the business, or enter the right one.
3. One **Description**: write what the table holds, its grain (what one row is) and its source.
4. One **Classification**: accept or change the suggested level using the job aid.
5. One **Quality check**: open the failing-rows query, run it, and send the rows to the data producer.

Click **Download SQL** and run the file in a Databricks SQL editor. Your mentor marks `first_review: true`.

## Your weekly routine (about 30 minutes)

1. The scan runs every Monday. Open the work queue and filter to your name.
2. Clear high-priority items first. PII reviews come before everything else.
3. Download the SQL and run it in Databricks the same day.
4. Route anything you cannot decide using the escalation table in the [job aid](steward-job-aid.md).
