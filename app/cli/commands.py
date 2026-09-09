"""CLI command definitions for the collector."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from collections.abc import Sequence

from app.config.loaders import load_channels_config, load_subjects_config
from app.config.settings import Settings
from app.database.models import ProcessingRun
from app.database.repositories.processing import ProcessingRunRepository
from app.database.session import create_database_engine, create_session_factory, init_db
from app.logging.setup import configure_logging
from app.processing.pipeline import ProcessingPipeline
from app.reports.reporter import Reporter
from app.runtime.locking import LockAlreadyHeldError, file_lock
from app.telegram.authentication import interactive_login
from app.telegram.collector import TelegramCollector, TelegramSessionNotAuthorizedError

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.cli",
        description="Telegram University Content Collector",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("health-check", help="Validate settings and configuration files.")
    subparsers.add_parser("init-db", help="Create database tables for local smoke checks.")
    subparsers.add_parser("telegram-login", help="Run one-time Telegram login.")

    collect_parser = subparsers.add_parser(
        "collect",
        help="Collect configured Telegram channel content.",
    )
    collect_parser.add_argument("--channel", help="Collect one configured channel by name.")
    collect_parser.add_argument("--limit", type=int, help="Limit messages per selected channel.")

    process_parser = subparsers.add_parser("process", help="Process pending downloaded files.")
    process_parser.add_argument("--limit", type=int, help="Limit number of files to process.")

    subparsers.add_parser("report", help="Generate a database report.")
    subparsers.add_parser("seed-demo", help="Insert demo records for the web dashboard.")

    serve_parser = subparsers.add_parser("serve", help="Run local web dashboard.")
    serve_parser.add_argument("--host", default="127.0.0.1", help="Dashboard host.")
    serve_parser.add_argument("--port", default=8000, type=int, help="Dashboard port.")
    return parser


def _session_factory(settings: Settings):
    engine = create_database_engine(settings)
    if settings.database_url.startswith("sqlite"):
        init_db(engine)
    return create_session_factory(engine)


def run_health_check(settings: Settings) -> int:
    channels = load_channels_config(settings.channels_config_path)
    subjects = load_subjects_config(settings.subjects_config_path)

    logger.info(
        "Health check completed",
        extra={
            "enabled_channels": len(channels.enabled_channels),
            "subjects": len(subjects.subjects),
            "database_url_configured": bool(settings.database_url),
            "ai_provider": settings.ai_provider,
        },
    )
    return 0


def run_init_db(settings: Settings) -> int:
    engine = create_database_engine(settings)
    init_db(engine)
    logger.info("Database tables are ready")
    return 0


async def run_collect(settings: Settings, *, channel: str | None, limit: int | None) -> int:
    with file_lock(settings.lock_file_path):
        session_factory = _session_factory(settings)
        with session_factory() as session:
            run = ProcessingRunRepository(session).start(
                {"command": "collect", "channel": channel, "limit": limit}
            )
            run_id = run.id
            session.commit()

        collector = TelegramCollector(settings=settings, session_factory=session_factory)
        summary = await collector.collect(channel_name=channel, limit=limit)

        with session_factory() as session:
            run = session.get(ProcessingRun, run_id)
            if run is not None:
                ProcessingRunRepository(session).finish(
                    run,
                    new_count=summary.new_messages,
                    duplicate_count=summary.duplicate_files,
                    failed_count=summary.failed_messages,
                    unsupported_count=summary.unsupported_files,
                )
                session.commit()
    logger.info("Collection completed", extra=summary.__dict__)
    return 0


async def run_process(settings: Settings, *, limit: int | None) -> int:
    with file_lock(settings.lock_file_path):
        session_factory = _session_factory(settings)
        with session_factory() as session:
            run = ProcessingRunRepository(session).start({"command": "process", "limit": limit})
            run_id = run.id
            session.commit()

        pipeline = ProcessingPipeline(settings=settings, session_factory=session_factory)
        summary = await pipeline.process_pending(limit=limit)

        with session_factory() as session:
            run = session.get(ProcessingRun, run_id)
            if run is not None:
                ProcessingRunRepository(session).finish(
                    run,
                    new_count=summary.processed,
                    classified_count=summary.classified,
                    unclassified_count=summary.unclassified,
                    failed_count=summary.failed,
                    unsupported_count=summary.unsupported,
                )
                session.commit()
    logger.info("Processing completed", extra=summary.__dict__)
    return 0


def run_report(settings: Settings) -> int:
    subjects = load_subjects_config(settings.subjects_config_path)
    session_factory = _session_factory(settings)
    with session_factory() as session:
        report = Reporter(session, subjects).generate()
        print(report.to_text(), file=sys.stdout)
    return 0


def run_seed_demo(settings: Settings) -> int:
    from app.web.admin import seed_demo_data

    session_factory = _session_factory(settings)
    with session_factory() as session:
        result = seed_demo_data(settings, session)
    logger.info("Demo data is ready", extra=result)
    return 0


def run_serve(settings: Settings, *, host: str, port: int) -> int:
    from app.web.server import run_dashboard

    logger.info("Starting dashboard", extra={"host": host, "port": port})
    run_dashboard(settings, host=host, port=port)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    settings = Settings()
    configure_logging(settings)

    if args.command == "health-check":
        return run_health_check(settings)
    if args.command == "init-db":
        return run_init_db(settings)
    if args.command == "telegram-login":
        return asyncio.run(interactive_login(settings))
    if args.command == "collect":
        try:
            return asyncio.run(run_collect(settings, channel=args.channel, limit=args.limit))
        except LockAlreadyHeldError as exc:
            logger.warning(
                "Another run is already active",
                extra={"lock_path": str(settings.lock_file_path)},
            )
            print(str(exc), file=sys.stderr)
            return 75
        except TelegramSessionNotAuthorizedError as exc:
            logger.error("Telegram session is not authorized")
            print(str(exc), file=sys.stderr)
            return 1
    if args.command == "process":
        try:
            return asyncio.run(run_process(settings, limit=args.limit))
        except LockAlreadyHeldError as exc:
            logger.warning(
                "Another run is already active",
                extra={"lock_path": str(settings.lock_file_path)},
            )
            print(str(exc), file=sys.stderr)
            return 75
    if args.command == "report":
        return run_report(settings)
    if args.command == "seed-demo":
        return run_seed_demo(settings)
    if args.command == "serve":
        return run_serve(settings, host=args.host, port=args.port)

    logger.error("Unknown command", extra={"command": args.command})
    return 2
