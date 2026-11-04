-- 1. Run once. Creates the schemas and the volume you upload the CSV files to.
USE CATALOG workspace;
CREATE SCHEMA IF NOT EXISTS steward_kit COMMENT 'Landing area for the Catalog Steward Kit demo files';
CREATE VOLUME IF NOT EXISTS steward_kit.raw COMMENT 'Raw CSV files from NHTSA, EPA and the synthetic generator';
CREATE SCHEMA IF NOT EXISTS customer_care;
CREATE SCHEMA IF NOT EXISTS dealer_service;
CREATE SCHEMA IF NOT EXISTS fuel_economy;
CREATE SCHEMA IF NOT EXISTS vehicle_safety;
