# Run it on your Databricks workspace

About 20 minutes. Works on Databricks Free Edition, where the catalog is called `workspace`.

## 1. Create the schemas and the upload volume

1. In Databricks, click **SQL Editor** in the left sidebar, then **+ New query** (or the **+** tab).
2. Open `databricks/01_setup.sql` from this repo, copy everything, and paste it into the editor.
3. Click **Run all**. You get five schemas (`vehicle_safety`, `fuel_economy`, `customer_care`, `dealer_service`, `steward_kit`) and a volume called `raw`.

## 2. Upload the five CSV files

1. Click **Catalog** in the left sidebar, then **workspace > steward_kit > raw**.
2. Click **Upload to this volume**.
3. Select these files from your copy of the repo:
   - `data\raw\nhtsa_recalls.csv`
   - `data\raw\nhtsa_complaints.csv`
   - `data\raw\epa_vehicles_gm.csv`
   - `data\synthetic\owner_contacts.csv`
   - `data\synthetic\service_appointments.csv`
4. Click **Upload**.

The two synthetic files exist only after you run `python -m steward_kit build-demo` on your laptop.

## 3. Load the tables and the starting metadata

In **SQL Editor**, paste and **Run all** for each file in order:

1. `databricks/02_load_tables.sql` creates the five tables from the uploaded files.
2. `databricks/03_starting_metadata.sql` adds the comments and tags the demo starts with.

Check it worked: **Catalog > workspace > vehicle_safety > recalls**. The **Overview** tab shows the description and tags.

## 4. Scan the workspace from your laptop

1. Get the connection details: **SQL Warehouses** in the left sidebar, click your warehouse (Free Edition has one, usually **Serverless Starter Warehouse**), then the **Connection details** tab. Copy **Server hostname** and **HTTP path**.
2. Create a token: click your profile icon (top right), **Settings > Developer > Access tokens > Manage > Generate new token**. Copy it. You will not see it again.
3. In Command Prompt, from the repo folder, with `.venv` activated:

```
pip install -r requirements-databricks.txt
set DATABRICKS_HOST=paste-server-hostname-here
set DATABRICKS_HTTP_PATH=paste-http-path-here
set DATABRICKS_TOKEN=paste-token-here
python -m steward_kit scan --target databricks
python -m http.server -d site 8000
```

4. Open http://localhost:8000. The work queue now shows your workspace.

The token is only stored in that Command Prompt window. Close it when you are done.

## 5. Apply decisions and rescan

1. Work through the queue, then click **Download SQL**.
2. Open the downloaded `.sql` file, paste it into **SQL Editor**, and click **Run all**.
3. Run `python -m steward_kit scan --target databricks` again and refresh the page. The items you decided are gone and the governance-ready count goes up.
