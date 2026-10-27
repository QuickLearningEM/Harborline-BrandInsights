"""Command line entry point: brand-insights <command>."""

import argparse
import getpass
import logging
import os
import sys

from .config import get_settings
from .logging_setup import configure_logging
from .warehouse import get_warehouse

log = logging.getLogger("brand_insights.cli")


def _demo_data(_args) -> int:
    from .ingestion.files import upsert_table
    from .ingestion.synthetic import generate

    wh = get_warehouse(get_settings())
    for table, df in generate().items():
        upsert_table(wh, table, df)
        log.info("Wrote %d synthetic rows to %s", len(df), table)
    return 0


def _ingest_files(_args) -> int:
    from .ingestion.files import load_landing_files

    settings = get_settings()
    counts = load_landing_files(settings.landing_dir, get_warehouse(settings))
    log.info("Loaded: %s", counts or "nothing")
    return 0


def _ingest_youtube(_args) -> int:
    from .ingestion.files import upsert_table
    from .ingestion.youtube import YouTubeClient

    settings = get_settings()
    client = YouTubeClient(settings.youtube_api_key, settings.youtube_max_quota_units)
    terms = [t.strip() for t in settings.youtube_search_terms.split(",") if t.strip()]
    df = client.collect(terms)
    if df.empty:
        log.warning("No comments collected")
        return 0
    upsert_table(get_warehouse(settings), "raw_youtube_comments", df)
    return 0


def _run_pipeline(_args) -> int:
    from .pipeline import run_pipeline

    settings = get_settings()
    status = run_pipeline(get_warehouse(settings), settings)
    log.info("Status: %s", status)
    return 0


def _create_user(args) -> int:
    from .web.auth import UserStore

    settings = get_settings()
    password = os.environ.get("BI_NEW_USER_PASSWORD") or getpass.getpass("Password (12+ chars): ")
    UserStore(settings.auth_db_path).create_user(args.username, password, args.role)
    log.info("Created user %s (%s)", args.username, args.role)
    return 0


def _serve(args) -> int:
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "brand_insights.web.app:create_app", factory=True, host=args.host, port=args.port,
        proxy_headers=True, forwarded_allow_ips=settings.forwarded_allow_ips,
        server_header=False,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    configure_logging(get_settings().log_level)
    parser = argparse.ArgumentParser(prog="brand-insights")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo-data", help="Load synthetic data for every source").set_defaults(func=_demo_data)
    sub.add_parser("ingest-files", help="Load Xstore and CM360/DV360 files").set_defaults(func=_ingest_files)
    sub.add_parser("ingest-youtube", help="Pull public YouTube comments").set_defaults(func=_ingest_youtube)
    sub.add_parser("run-pipeline", help="Rebuild curated tables and marts").set_defaults(func=_run_pipeline)
    cu = sub.add_parser("create-user", help="Add a dashboard user")
    cu.add_argument("username")
    cu.add_argument("--role", default="viewer", choices=["viewer", "admin"])
    cu.set_defaults(func=_create_user)
    sv = sub.add_parser("serve", help="Run the dashboard web server")
    sv.add_argument("--host", default="127.0.0.1")
    sv.add_argument("--port", type=int, default=8000)
    sv.set_defaults(func=_serve)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
