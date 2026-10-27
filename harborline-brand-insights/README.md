# Harborline Brand Insights

Brand perception and segment responsiveness analytics for Harborline Home & Living (a fictional customer). It combines customer, sales, ad-attribution, and public YouTube data to show, for each customer segment, how the brand is perceived, which segments respond best to marketing spend, and which are mis-targeted. Results are served on a password-protected website over HTTPS.

## How the code maps to the architecture

| Architecture stage | Code | Notes |
|---|---|---|
| Sources and ingestion | `ingestion/files.py`, `ingestion/youtube.py`, `schemas.py` | Salesforce and Shopify arrive through a managed ELT connector into the raw tables defined in `schemas.py`. Xstore and CM360/DV360 arrive as CSV files. YouTube is pulled by `YouTubeClient`. |
| Storage (Raw, Curated, Marts) | `warehouse/` | `raw_*`, `curated_*`, and `mart_*` tables. SQLite for demos, Snowflake for production. |
| Identity and segmentation | `processing/identity.py`, `processing/segmentation.py` | One customer record, one primary segment, versioned by month. |
| Analytics models | `analytics/sentiment.py`, `responsiveness.py`, `mistargeting.py` | Sentiment, Responsiveness Index, and the four-way classification. |
| Orchestration | `pipeline.py`, `cli.py` | `brand-insights run-pipeline`; scheduled by the `pipeline` service in `docker-compose.yml`. |
| Serving | `web/` | FastAPI app with login, CSRF protection, security headers, and server-rendered dashboard. |

```
src/brand_insights/
  config.py  schemas.py  pipeline.py  cli.py
  warehouse/   base.py  sqlite.py  snowflake.py
  ingestion/   files.py  youtube.py  synthetic.py
  processing/  identity.py  segmentation.py
  analytics/   sentiment.py  responsiveness.py  mistargeting.py
  web/         app.py  routes.py  auth.py  security.py  dashboard.py  templates/  static/
tests/         26 tests: schemas, analytics, and web security
deploy/        Caddyfile (automatic HTTPS)
sql/           snowflake_setup.sql (roles and grants)
```

## Quick start (local demo, synthetic data)

```bash
make install
make demo          # loads synthetic data, runs the pipeline, creates a user, starts the server
```
Open http://127.0.0.1:8000 and sign in as `admin`. The password is generated randomly on first run and saved to `data/demo-credentials.txt` (gitignored, owner-only). Delete that file and rerun to rotate it. Plain HTTP is for local use only and must never be used on a real server.

### Sharing the demo from a Codespace

`make demo-up` starts the same demo detached, so it keeps running after the terminal closes, and prints the `https://<codespace>-8000.app.github.dev` URL. `make demo-down` stops it. The repo's `.devcontainer/devcontainer.json` runs `demo-up` on every codespace start or resume, so the URL comes back on its own (this takes effect after a rebuild or in new codespaces). A fixed `BI_SESSION_SECRET` in `.env` keeps sign-ins valid across restarts, and `BI_SECURE_COOKIES=true` is set because the forwarded URL is HTTPS.

The link only works while the codespace is running. To keep it up longer, raise the idle timeout (maximum 4 hours) at https://github.com/settings/codespaces. To share it outside your account, run `gh codespace ports visibility 8000:public -c "$CODESPACE_NAME"`, and share the password through a separate channel from the link. For a link that stays up for days, deploy it as described below.

## Deploy to a secure website

1. Run `sql/snowflake_setup.sql`, create key-pair service users, and place the private keys where the containers can read them (for example Docker secrets).
2. `cp .env.example .env` and fill in `BI_SESSION_SECRET` (48+ random characters), `SITE_DOMAIN`, and the Snowflake settings.
3. Point your DNS record for `SITE_DOMAIN` at the server and open ports 80 and 443.
4. `docker compose up -d --build`. Caddy gets a certificate automatically and redirects HTTP to HTTPS.
5. Create the first user: `docker compose exec -e BI_NEW_USER_PASSWORD='a-long-unique-passphrase' app brand-insights create-user alice`.

Daily data arrives as files named `raw_store_transactions*.csv` and `raw_ad_delivery*.csv` in `BI_LANDING_DIR`. Required columns are listed in `schemas.py` (`RAW_SCHEMAS`); configure the Xstore export and the CM360/DV360 report templates to produce them. Loads are idempotent.

## Security controls in the website

- HTTPS only in production (Caddy), HSTS, secure and HttpOnly session cookies, server-enforced 8-hour session lifetime and 30-minute idle timeout (`BI_SESSION_IDLE_SECONDS`).
- Argon2id password hashing, 12-character minimum, timing-equalized login, lockout after 5 failures for 15 minutes, accounts re-checked on every request so disabling a user takes effect immediately.
- CSRF tokens on login and logout, session reset on login, no redirect parameters (no open redirects).
- Strict Content Security Policy (no scripts at all; the dashboard is server-rendered with SVG charts), frame blocking, no-store caching, trusted host checks.
- API docs and OpenAPI schema disabled. Production refuses to start with a weak session secret or wildcard hosts.
- Containers run as a non-root user with a read-only filesystem and dropped capabilities. The app port is never published; only Caddy is exposed.
- Privacy: email hashes stop at the curated step, YouTube commenters are never identified, and the website needs only read access to Snowflake.

## Configuration

All settings are `BI_*` environment variables (see `config.py` and `.env.example`). Key analytics thresholds: `BI_UNDER_INVESTED_INDEX` (120), `BI_OVER_INVESTED_INDEX` (80), `BI_MIN_SENTIMENT_SAMPLE` (30), `BI_REVENUE_WINDOW_DAYS` (365).

## Testing

```bash
make test    # pytest
make lint    # ruff
```

## Known limitations and next steps

- **Verified here:** the pipeline, analytics, and web app run end to end on synthetic data in SQLite, the tests pass, and a live login and dashboard load were checked over HTTP. **Not verified here:** the Snowflake backend, the YouTube client against the live API, the Docker stack, and certificate issuance. Test these in your environment first.
- Transformations are written in pandas for clarity. For very large volumes, port them to SQL or dbt running inside Snowflake.
- Login lockout is in memory. With more than one app instance, move it to Redis, or replace local accounts with single sign-on (OIDC).
- The Snowflake setup keeps raw, curated, and mart tables in one schema, so the web role can read curated tables too. Split the marts into their own schema for stricter separation.
- YouTube sentiment is a topic-level proxy, not customer data. Validate it against the brand survey in phase 2. The lexicon classifier is a baseline; set `BI_SENTIMENT_CLASSIFIER=llm` to use a language model (output is validated, with fallback to the lexicon).
- Segment rules are a starting point. Review thresholds and rules with Brand Strategy and Marketing.
