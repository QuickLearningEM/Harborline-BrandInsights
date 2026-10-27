-- One-time Snowflake setup. Run as ACCOUNTADMIN or a role that can create roles and databases.
CREATE DATABASE IF NOT EXISTS BRAND_INSIGHTS;
CREATE WAREHOUSE IF NOT EXISTS BI_WH WAREHOUSE_SIZE = XSMALL AUTO_SUSPEND = 60 AUTO_RESUME = TRUE;

CREATE ROLE IF NOT EXISTS BI_PIPELINE;    -- loads raw data, builds curated tables and marts
CREATE ROLE IF NOT EXISTS BI_WEB_READER;  -- used by the website: read-only

GRANT USAGE ON WAREHOUSE BI_WH TO ROLE BI_PIPELINE;
GRANT USAGE ON WAREHOUSE BI_WH TO ROLE BI_WEB_READER;
GRANT USAGE ON DATABASE BRAND_INSIGHTS TO ROLE BI_PIPELINE;
GRANT USAGE ON DATABASE BRAND_INSIGHTS TO ROLE BI_WEB_READER;
GRANT USAGE ON SCHEMA BRAND_INSIGHTS.PUBLIC TO ROLE BI_PIPELINE;
GRANT USAGE ON SCHEMA BRAND_INSIGHTS.PUBLIC TO ROLE BI_WEB_READER;
GRANT CREATE TABLE ON SCHEMA BRAND_INSIGHTS.PUBLIC TO ROLE BI_PIPELINE;

-- The pipeline owns the tables it creates. Give the website read access to future tables.
-- NOTE: this layout keeps raw, curated, and mart tables in one schema, so the reader can also
-- see curated tables. For stricter separation, move the mart_* tables to their own schema
-- and grant the reader access to that schema only.
GRANT SELECT ON FUTURE TABLES IN SCHEMA BRAND_INSIGHTS.PUBLIC TO ROLE BI_WEB_READER;

-- Service users use key-pair authentication (no passwords):
-- CREATE USER bi_pipeline_svc DEFAULT_ROLE = BI_PIPELINE RSA_PUBLIC_KEY = '<public key>';
-- CREATE USER bi_web_svc DEFAULT_ROLE = BI_WEB_READER RSA_PUBLIC_KEY = '<public key>';
-- GRANT ROLE BI_PIPELINE TO USER bi_pipeline_svc;
-- GRANT ROLE BI_WEB_READER TO USER bi_web_svc;
