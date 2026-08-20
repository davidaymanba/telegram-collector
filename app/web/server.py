"""Local web API and static frontend server."""

from __future__ import annotations

import asyncio
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from app.config.settings import Settings
from app.database.session import create_database_engine, create_session_factory, init_db
from app.processing.pipeline import ProcessingPipeline
from app.runtime.locking import LockAlreadyHeldError, file_lock
from app.telegram.collector import TelegramCollector
from app.web.admin import (
    build_overview,
    create_manual_file,
    delete_channel,
    delete_file,
    delete_message,
    delete_run,
    delete_subject,
    list_files,
    list_messages,
    list_runs,
    seed_demo_data,
    update_channel_state,
    update_file,
    upsert_channel,
    upsert_message,
    upsert_subject,
)

STATIC_ROOT = Path(__file__).with_name("static")


def _session_factory(settings: Settings):
    engine = create_database_engine(settings)
    init_db(engine)
    return create_session_factory(engine)


class ApiError(Exception):
    def __init__(self, message: str, status: HTTPStatus = HTTPStatus.BAD_REQUEST) -> None:
        super().__init__(message)
        self.status = status


class DashboardRequestHandler(BaseHTTPRequestHandler):
    settings: Settings

    def do_GET(self) -> None:
        try:
            parsed = urlparse(self.path)
            if parsed.path in {"/", "/index.html"}:
                self._send_static_file(STATIC_ROOT / "index.html", "text/html; charset=utf-8")
                return
            if parsed.path.startswith("/assets/"):
                asset_path = STATIC_ROOT / parsed.path.removeprefix("/assets/")
                self._send_static_file(asset_path, self._content_type(asset_path))
                return
            if parsed.path == "/api/health":
                self._send_json({"healthy": True, "database": self._database_label()})
                return
            if parsed.path == "/api/overview":
                self._send_json(self._overview())
                return
            if parsed.path == "/api/files":
                limit = int(parse_qs(parsed.query).get("limit", ["100"])[0])
                with _session_factory(self.settings)() as session:
                    self._send_json({"files": list_files(session, limit=limit)})
                return
            if parsed.path == "/api/messages":
                limit = int(parse_qs(parsed.query).get("limit", ["100"])[0])
                with _session_factory(self.settings)() as session:
                    self._send_json({"messages": list_messages(session, limit=limit)})
                return
            if parsed.path == "/api/runs":
                limit = int(parse_qs(parsed.query).get("limit", ["30"])[0])
                with _session_factory(self.settings)() as session:
                    self._send_json({"runs": list_runs(session, limit=limit)})
                return
            self._send_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)
        except Exception as exc:
            self._handle_error(exc)

    def do_POST(self) -> None:
        try:
            parsed = urlparse(self.path)
            if parsed.path == "/api/channels":
                channels = upsert_channel(self.settings, self._read_json())
                self._send_json(
                    {"channels": [channel.model_dump() for channel in channels.channels]}
                )
                return
            if parsed.path == "/api/subjects":
                subjects = upsert_subject(self.settings, self._read_json())
                self._send_json(
                    {"subjects": [subject.model_dump() for subject in subjects.subjects]}
                )
                return
            if parsed.path == "/api/channels/state":
                with _session_factory(self.settings)() as session:
                    self._send_json(
                        {
                            "channel": update_channel_state(
                                self.settings,
                                session,
                                self._read_json(),
                            )
                        }
                    )
                return
            if parsed.path == "/api/messages":
                with _session_factory(self.settings)() as session:
                    self._send_json(
                        {"message": upsert_message(self.settings, session, self._read_json())}
                    )
                return
            if parsed.path == "/api/files":
                with _session_factory(self.settings)() as session:
                    self._send_json(
                        {
                            "file": create_manual_file(
                                self.settings,
                                session,
                                self._read_json(),
                            )
                        }
                    )
                return
            if parsed.path == "/api/demo/seed":
                with _session_factory(self.settings)() as session:
                    self._send_json(seed_demo_data(self.settings, session))
                return
            if parsed.path == "/api/actions/process":
                payload = self._read_json(optional=True)
                result = asyncio.run(self._run_process(limit=payload.get("limit")))
                self._send_json({"ok": True, "summary": result.__dict__})
                return
            if parsed.path == "/api/actions/collect":
                payload = self._read_json(optional=True)
                result = asyncio.run(
                    self._run_collect(
                        channel=payload.get("channel") or None,
                        limit=payload.get("limit") or None,
                    )
                )
                self._send_json({"ok": True, "summary": result.__dict__})
                return
            self._send_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)
        except Exception as exc:
            self._handle_error(exc)

    def do_PATCH(self) -> None:
        try:
            parsed = urlparse(self.path)
            if parsed.path.startswith("/api/files/"):
                file_id = int(parsed.path.removeprefix("/api/files/"))
                with _session_factory(self.settings)() as session:
                    self._send_json(
                        {
                            "file": update_file(
                                self.settings,
                                session,
                                file_id,
                                self._read_json(),
                            )
                        }
                    )
                return
            if parsed.path.startswith("/api/messages/"):
                message_id = int(parsed.path.removeprefix("/api/messages/"))
                payload = self._read_json()
                payload["id"] = message_id
                with _session_factory(self.settings)() as session:
                    self._send_json(
                        {"message": upsert_message(self.settings, session, payload)}
                    )
                return
            self._send_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)
        except Exception as exc:
            self._handle_error(exc)

    def do_DELETE(self) -> None:
        try:
            parsed = urlparse(self.path)
            if parsed.path.startswith("/api/channels/"):
                name = unquote(parsed.path.removeprefix("/api/channels/"))
                channels = delete_channel(self.settings, name)
                self._send_json(
                    {"channels": [channel.model_dump() for channel in channels.channels]}
                )
                return
            if parsed.path.startswith("/api/subjects/"):
                code = unquote(parsed.path.removeprefix("/api/subjects/"))
                subjects = delete_subject(self.settings, code)
                self._send_json(
                    {"subjects": [subject.model_dump() for subject in subjects.subjects]}
                )
                return
            if parsed.path.startswith("/api/files/"):
                file_id = int(parsed.path.removeprefix("/api/files/"))
                with _session_factory(self.settings)() as session:
                    self._send_json(delete_file(self.settings, session, file_id))
                return
            if parsed.path.startswith("/api/messages/"):
                message_id = int(parsed.path.removeprefix("/api/messages/"))
                with _session_factory(self.settings)() as session:
                    self._send_json(delete_message(self.settings, session, message_id))
                return
            if parsed.path.startswith("/api/runs/"):
                run_id = int(parsed.path.removeprefix("/api/runs/"))
                with _session_factory(self.settings)() as session:
                    self._send_json(delete_run(session, run_id))
                return
            self._send_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)
        except Exception as exc:
            self._handle_error(exc)

    async def _run_process(self, limit: int | None):
        with file_lock(self.settings.lock_file_path):
            pipeline = ProcessingPipeline(
                settings=self.settings,
                session_factory=_session_factory(self.settings),
            )
            return await pipeline.process_pending(limit=limit)

    async def _run_collect(self, channel: str | None, limit: int | None):
        if self.settings.telegram_api_id is None or self.settings.telegram_api_hash is None:
            raise ApiError(
                "Telegram credentials are not configured. Fill TUC_TELEGRAM_API_ID and "
                "TUC_TELEGRAM_API_HASH, then run telegram-login.",
                HTTPStatus.PRECONDITION_REQUIRED,
            )
        with file_lock(self.settings.lock_file_path):
            collector = TelegramCollector(
                settings=self.settings,
                session_factory=_session_factory(self.settings),
            )
            return await collector.collect(channel_name=channel, limit=limit)

    def _overview(self) -> dict[str, Any]:
        with _session_factory(self.settings)() as session:
            return build_overview(self.settings, session)

    def _read_json(self, *, optional: bool = False) -> dict[str, Any]:
        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length == 0:
            if optional:
                return {}
            raise ApiError("JSON body is required")
        raw = self.rfile.read(content_length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except ValueError as exc:
            raise ApiError("Invalid JSON body") from exc
        if not isinstance(payload, dict):
            raise ApiError("JSON body must be an object")
        return payload

    def _send_static_file(self, path: Path, content_type: str) -> None:
        resolved_root = STATIC_ROOT.resolve()
        resolved_path = path.resolve()
        if resolved_root != resolved_path and resolved_root not in resolved_path.parents:
            self._send_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)
            return
        if not resolved_path.exists() or not resolved_path.is_file():
            self._send_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)
            return
        self._send(resolved_path.read_bytes(), content_type, HTTPStatus.OK)

    def _send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self._send(body, "application/json; charset=utf-8", status)

    def _send(self, body: bytes, content_type: str, status: HTTPStatus) -> None:
        self.send_response(status.value)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _handle_error(self, exc: Exception) -> None:
        if isinstance(exc, LockAlreadyHeldError):
            self._send_json({"error": str(exc)}, status=HTTPStatus.CONFLICT)
            return
        if isinstance(exc, ApiError):
            self._send_json({"error": str(exc)}, status=exc.status)
            return
        self._send_json({"error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def _database_label(self) -> str:
        if self.settings.database_url.startswith("mysql"):
            return "MySQL"
        if self.settings.database_url.startswith("postgresql"):
            return "PostgreSQL"
        if self.settings.database_url.startswith("sqlite"):
            return "SQLite"
        return "Configured"

    @staticmethod
    def _content_type(path: Path) -> str:
        if path.suffix == ".css":
            return "text/css; charset=utf-8"
        if path.suffix == ".js":
            return "application/javascript; charset=utf-8"
        return "application/octet-stream"

    def log_message(self, format: str, *args: object) -> None:
        return


def run_dashboard(settings: Settings, *, host: str, port: int) -> None:
    """Start a blocking local dashboard server."""

    handler = type(
        "ConfiguredDashboardRequestHandler",
        (DashboardRequestHandler,),
        {"settings": settings},
    )
    server = ThreadingHTTPServer((host, port), handler)
    server.serve_forever()
