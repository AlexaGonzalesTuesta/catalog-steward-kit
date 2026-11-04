-- 2. Run after uploading the five CSV files to /Volumes/workspace/steward_kit/raw
USE CATALOG workspace;

CREATE OR REPLACE TABLE vehicle_safety.recalls AS SELECT
    NULLIF(TRIM(`campaign_number`), '') AS campaign_number,
    NULLIF(TRIM(`manufacturer`), '') AS manufacturer,
    NULLIF(TRIM(`make`), '') AS make,
    NULLIF(TRIM(`model`), '') AS model,
    TRY_CAST(NULLIF(TRIM(`model_year`), '') AS INT) AS model_year,
    NULLIF(TRIM(`component`), '') AS component,
    NULLIF(TRIM(`summary`), '') AS summary,
    NULLIF(TRIM(`consequence`), '') AS consequence,
    NULLIF(TRIM(`remedy`), '') AS remedy,
    NULLIF(TRIM(`notes`), '') AS notes,
    TRY_CAST(NULLIF(TRIM(`report_received_date`), '') AS DATE) AS report_received_date,
    TRY_CAST(NULLIF(TRIM(`park_it`), '') AS BOOLEAN) AS park_it,
    TRY_CAST(NULLIF(TRIM(`park_outside`), '') AS BOOLEAN) AS park_outside,
    TRY_CAST(NULLIF(TRIM(`over_the_air_update`), '') AS BOOLEAN) AS over_the_air_update
FROM read_files('/Volumes/workspace/steward_kit/raw/nhtsa_recalls.csv', format => 'csv', header => true, inferSchema => false,
                escape => '"', multiLine => true);

CREATE OR REPLACE TABLE vehicle_safety.complaints AS SELECT
    NULLIF(TRIM(`odi_number`), '') AS odi_number,
    NULLIF(TRIM(`manufacturer`), '') AS manufacturer,
    NULLIF(TRIM(`make`), '') AS make,
    NULLIF(TRIM(`model`), '') AS model,
    TRY_CAST(NULLIF(TRIM(`model_year`), '') AS INT) AS model_year,
    TRY_CAST(NULLIF(TRIM(`crash`), '') AS BOOLEAN) AS crash,
    TRY_CAST(NULLIF(TRIM(`fire`), '') AS BOOLEAN) AS fire,
    TRY_CAST(NULLIF(TRIM(`injuries`), '') AS INT) AS injuries,
    TRY_CAST(NULLIF(TRIM(`deaths`), '') AS INT) AS deaths,
    TRY_CAST(NULLIF(TRIM(`incident_date`), '') AS DATE) AS incident_date,
    TRY_CAST(NULLIF(TRIM(`filed_date`), '') AS DATE) AS filed_date,
    NULLIF(TRIM(`vin_prefix`), '') AS vin_prefix,
    NULLIF(TRIM(`components`), '') AS components,
    NULLIF(TRIM(`summary`), '') AS summary
FROM read_files('/Volumes/workspace/steward_kit/raw/nhtsa_complaints.csv', format => 'csv', header => true, inferSchema => false,
                escape => '"', multiLine => true);

CREATE OR REPLACE TABLE fuel_economy.vehicles AS SELECT
    TRY_CAST(NULLIF(TRIM(`id`), '') AS INT) AS vehicle_id,
    TRY_CAST(NULLIF(TRIM(`year`), '') AS INT) AS model_year,
    NULLIF(TRIM(`make`), '') AS make,
    NULLIF(TRIM(`model`), '') AS model,
    NULLIF(TRIM(`VClass`), '') AS vehicle_class,
    NULLIF(TRIM(`drive`), '') AS drive,
    NULLIF(TRIM(`trany`), '') AS transmission,
    TRY_CAST(NULLIF(TRIM(`cylinders`), '') AS INT) AS cylinders,
    TRY_CAST(NULLIF(TRIM(`displ`), '') AS DOUBLE) AS displacement_l,
    NULLIF(TRIM(`fuelType`), '') AS fuel_type,
    NULLIF(TRIM(`atvType`), '') AS alt_fuel_type,
    TRY_CAST(NULLIF(TRIM(`city08`), '') AS INT) AS city_mpg,
    TRY_CAST(NULLIF(TRIM(`highway08`), '') AS INT) AS highway_mpg,
    TRY_CAST(NULLIF(TRIM(`comb08`), '') AS INT) AS combined_mpg,
    TRY_CAST(NULLIF(TRIM(`co2TailpipeGpm`), '') AS DOUBLE) AS co2_grams_per_mile,
    TRY_CAST(NULLIF(TRIM(`fuelCost08`), '') AS INT) AS annual_fuel_cost_usd,
    TRY_CAST(NULLIF(TRIM(`range`), '') AS INT) AS ev_range_miles
FROM read_files('/Volumes/workspace/steward_kit/raw/epa_vehicles_gm.csv', format => 'csv', header => true, inferSchema => false,
                escape => '"', multiLine => true);

CREATE OR REPLACE TABLE customer_care.owner_contacts AS SELECT
    NULLIF(TRIM(`customer_id`), '') AS customer_id,
    NULLIF(TRIM(`first_name`), '') AS first_name,
    NULLIF(TRIM(`last_name`), '') AS last_name,
    NULLIF(TRIM(`email`), '') AS email,
    NULLIF(TRIM(`phone`), '') AS phone,
    NULLIF(TRIM(`street_address`), '') AS street_address,
    NULLIF(TRIM(`city`), '') AS city,
    NULLIF(TRIM(`state`), '') AS state,
    NULLIF(TRIM(`zip`), '') AS zip,
    NULLIF(TRIM(`vin`), '') AS vin,
    NULLIF(TRIM(`preferred_dealer`), '') AS preferred_dealer,
    TRY_CAST(NULLIF(TRIM(`marketing_opt_in`), '') AS BOOLEAN) AS marketing_opt_in,
    TRY_CAST(NULLIF(TRIM(`created_at`), '') AS DATE) AS created_at
FROM read_files('/Volumes/workspace/steward_kit/raw/owner_contacts.csv', format => 'csv', header => true, inferSchema => false,
                escape => '"', multiLine => true);

CREATE OR REPLACE TABLE dealer_service.service_appointments AS SELECT
    NULLIF(TRIM(`appointment_id`), '') AS appointment_id,
    NULLIF(TRIM(`vin`), '') AS vin,
    NULLIF(TRIM(`dealer_code`), '') AS dealer_code,
    TRY_CAST(NULLIF(TRIM(`appointment_date`), '') AS DATE) AS appointment_date,
    NULLIF(TRIM(`service_type`), '') AS service_type,
    NULLIF(TRIM(`recall_campaign_number`), '') AS recall_campaign_number,
    NULLIF(TRIM(`status`), '') AS status,
    TRY_CAST(NULLIF(TRIM(`completed_at`), '') AS DATE) AS completed_at,
    NULLIF(TRIM(`customer_notes`), '') AS customer_notes
FROM read_files('/Volumes/workspace/steward_kit/raw/service_appointments.csv', format => 'csv', header => true, inferSchema => false,
                escape => '"', multiLine => true);
