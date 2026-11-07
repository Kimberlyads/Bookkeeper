"""API HTTP mínima para receber a biblioteca exportada pela extensão.

Não armazena credenciais da Amazon.
O código de vínculo é de uso único e com validade limitada.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable
from urllib.parse import urlparse

from .database import (
    claim_link_code,
    criar_tabela,
    importar_livros_kindle,
    release_link_code,
)

logger = logging.getLogger(__name__)
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8787


class BookkeeperAPIHandler(BaseHTTPRequestHandler):
    on_import_complete: Callable | None = None

    def log_message(self, format, *args):
        logger.info("%s - %s", self.address_string(), format % args)

    def _send_json(self, status: int, payload: dict):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/health"):
            self._send_json(200, {"ok": True, "service": "bookkeeper-api"})
            return
        self._send_json(404, {"ok": False, "error": "not_found"})

    def do_POST(self):
        path = urlparse(self.path).path
        if path != "/api/import":
            self._send_json(404, {"ok": False, "error": "not_found"})
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length <= 0 or length > 50_000_000:
            self._send_json(400, {"ok": False, "error": "invalid_body"})
            return
        try:
            raw = self.rfile.read(length)
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send_json(400, {"ok": False, "error": "invalid_json"})
            return
        if not isinstance(payload, dict):
            self._send_json(400, {"ok": False, "error": "invalid_payload"})
            return
        code = (payload.get("code") or "").strip()
        books = payload.get("books")
        if not code:
            self._send_json(400, {"ok": False, "error": "missing_code"})
            return
        if not isinstance(books, list):
            self._send_json(400, {"ok": False, "error": "missing_books"})
            return
        # Reserva atômica com claim_token: impede uso simultâneo e evita
        # que um release antigo reative código já revogado por /conectar.
        claimed = claim_link_code(code)
        if claimed is None:
            self._send_json(
                401,
                {
                    "ok": False,
                    "error": "invalid_or_expired_code",
                    "message": (
                        "Código inválido, expirado ou já utilizado. "
                        "Gere um novo com /conectar no Telegram."
                    ),
                },
            )
            return
        telegram_user_id, claim_token = claimed
        try:
            resultado = importar_livros_kindle(telegram_user_id, books)
        except Exception:
            logger.exception("Falha ao importar biblioteca")
            # Só libera se o token ainda for o desta reserva.
            try:
                release_link_code(code, claim_token)
            except Exception:
                logger.exception("Falha ao liberar código após erro de importação")
            self._send_json(500, {"ok": False, "error": "import_failed"})
            return
        callback = type(self).on_import_complete
        if callback:
            try:
                callback(telegram_user_id, resultado)
            except Exception:
                logger.exception("Falha no callback de importação")
        self._send_json(
            200,
            {
                "ok": True,
                "adicionados": resultado["adicionados"],
                "ignorados": resultado["ignorados"],
                "enriquecidos": resultado.get("enriquecidos", 0),
                "total_recebidos": resultado["total_recebidos"],
            },
        )


def criar_servidor(
    host: str | None = None,
    port: int | None = None,
    on_import_complete: Callable | None = None,
) -> ThreadingHTTPServer:
    criar_tabela()
    host = host or os.getenv("BOOKKEEPER_API_HOST", DEFAULT_HOST)
    port = int(port or os.getenv("BOOKKEEPER_API_PORT", DEFAULT_PORT))
    BookkeeperAPIHandler.on_import_complete = on_import_complete
    return ThreadingHTTPServer((host, port), BookkeeperAPIHandler)


def iniciar_api_em_thread(
    host: str | None = None,
    port: int | None = None,
    on_import_complete: Callable | None = None,
) -> ThreadingHTTPServer:
    server = criar_servidor(host, port, on_import_complete)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info(
        "API Bookkeeper ouvindo em http://%s:%s",
        server.server_address[0],
        server.server_address[1],
    )
    return server
