"""Testes da Entrega 1: pareamento seguro do código de vínculo."""

from __future__ import annotations

import json
import socket
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

import pytest

import bookkeeper.database as db
from bookkeeper.api import criar_servidor


@pytest.fixture()
def banco_tmp(tmp_path, monkeypatch):
    caminho = tmp_path / "teste.db"
    monkeypatch.setattr(db, "CAMINHO_BANCO", caminho)
    db.criar_tabela()
    return caminho



def _porta_livre(host="127.0.0.1") -> int:
    """Obtém uma porta TCP livre sem fixar números no código de teste."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


def _iniciar_api_temporaria(host="127.0.0.1"):
    """Sobe a API em porta dinâmica e espera ``/health``.

    Não usa portas fixas. Evita ``time.sleep`` arbitrário: faz poll em
    ``/health`` até o servidor responder ou estourar o prazo.

    Nota: ``criar_servidor(..., port=0)`` não serve aqui porque
    ``port or DEFAULT`` trata 0 como falsy e cai em 8787.
    Retorna ``(server, base_url, thread)``.
    """
    port = _porta_livre(host)
    server = criar_servidor(host=host, port=port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host_bound, bound_port = server.server_address
    base_url = f"http://{host_bound}:{bound_port}"
    deadline = time.monotonic() + 3.0
    last_error = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"{base_url}/health", timeout=0.3) as resp:
                if resp.status == 200:
                    return server, base_url, thread
        except Exception as exc:  # noqa: BLE001 — poll de readiness
            last_error = exc
            time.sleep(0.02)
    try:
        server.shutdown()
        server.server_close()
    except Exception:
        pass
    raise RuntimeError(f"API de teste não ficou pronta em tempo: {last_error}")


def test_claim_sucesso_e_reuso_negado(banco_tmp):
    db.garantir_usuario(10, "u", "U")
    code, _ = db.criar_link_code(10)
    claimed = db.claim_link_code(code)
    assert claimed is not None
    uid, token = claimed
    assert uid == 10
    assert token
    assert db.claim_link_code(code) is None


def test_release_com_token_permite_novo_claim(banco_tmp):
    db.garantir_usuario(11, "u", "U")
    code, _ = db.criar_link_code(11)
    uid, token = db.claim_link_code(code)
    assert uid == 11
    assert db.release_link_code(code, token) is True
    claimed = db.claim_link_code(code)
    assert claimed is not None
    assert claimed[0] == 11


def test_release_sem_token_ou_token_errado_falha(banco_tmp):
    db.garantir_usuario(14, "u", "U")
    code, _ = db.criar_link_code(14)
    uid, token = db.claim_link_code(code)
    assert db.release_link_code(code, None) is False
    assert db.release_link_code(code, "token-invalido") is False
    assert db.claim_link_code(code) is None  # ainda reservado
    assert db.release_link_code(code, token) is True


def test_codigo_expirado_nao_claim(banco_tmp):
    db.garantir_usuario(12, "u", "U")
    code, _ = db.criar_link_code(12)
    passado = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    with db.conectar() as c:
        c.execute(
            "UPDATE link_codes SET expira_em = ? WHERE code = ?",
            (passado, code),
        )
    assert db.claim_link_code(code) is None


def test_claim_concorrente_apenas_um_vence(banco_tmp):
    db.garantir_usuario(13, "u", "U")
    code, _ = db.criar_link_code(13)
    resultados = []
    barreira = threading.Barrier(8)

    def trabalhador():
        barreira.wait()
        resultados.append(db.claim_link_code(code))

    threads = [threading.Thread(target=trabalhador) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    sucessos = [r for r in resultados if r is not None]
    falhas = [r for r in resultados if r is None]
    assert len(sucessos) == 1
    assert len(falhas) == 7
    assert sucessos[0][0] == 13
    assert sucessos[0][1]


def test_release_antigo_nao_reativa_apos_novo_codigo(banco_tmp):
    """Cenário do bug:
    1) código A é reservado
    2) usuário gera código B (invalida A)
    3) importação de A falha e tenta release
    4) A não pode voltar a ser utilizável
    """
    db.garantir_usuario(30, "u", "U")
    code_a, _ = db.criar_link_code(30)
    claimed = db.claim_link_code(code_a)
    assert claimed is not None
    _uid, token_a = claimed

    code_b, _ = db.criar_link_code(30)
    assert code_b != code_a

    # Release da reserva antiga não deve reativar A.
    assert db.release_link_code(code_a, token_a) is False
    assert db.claim_link_code(code_a) is None

    # B continua válido para claim.
    claimed_b = db.claim_link_code(code_b)
    assert claimed_b is not None
    assert claimed_b[0] == 30


def test_api_falha_nao_consome_codigo(banco_tmp, monkeypatch):
    db.garantir_usuario(20, "u", "U")
    code, _ = db.criar_link_code(20)

    def falhar(*_a, **_k):
        raise RuntimeError("falha simulada na importação")

    monkeypatch.setattr("bookkeeper.api.importar_livros_kindle", falhar)

    server, base_url, _thread = _iniciar_api_temporaria()
    try:
        payload = json.dumps({"code": code, "books": [{"title": "X"}]}).encode()
        req = urllib.request.Request(
            f"{base_url}/api/import",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(req)
        assert exc.value.code == 500

        # Código deve poder ser claimado de novo após a falha (mesmo código).
        claimed = db.claim_link_code(code)
        assert claimed is not None
        assert claimed[0] == 20
    finally:
        server.shutdown()
        server.server_close()


def test_api_sucesso_consome_codigo(banco_tmp):
    db.garantir_usuario(21, "u", "U")
    code, _ = db.criar_link_code(21)
    server, base_url, _thread = _iniciar_api_temporaria()
    try:
        payload = json.dumps(
            {
                "code": code,
                "books": [
                    {"title": "Livro OK", "authors": ["Autora"], "asin": "B00TEST01"}
                ],
            }
        ).encode()
        req = urllib.request.Request(
            f"{base_url}/api/import",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req) as resp:
            body = json.loads(resp.read().decode())
        assert body["ok"] is True
        assert body["adicionados"] == 1
        assert db.claim_link_code(code) is None
        assert len(db.listar_livros(21)) == 1
    finally:
        server.shutdown()
        server.server_close()


def test_migracao_adiciona_claim_token(tmp_path, monkeypatch):
    """Banco antigo sem claim_token continua utilizável após criar_tabela."""
    caminho = tmp_path / "legado.db"
    monkeypatch.setattr(db, "CAMINHO_BANCO", caminho)
    import sqlite3

    with sqlite3.connect(caminho) as c:
        c.execute(
            """
            CREATE TABLE link_codes (
                code TEXT PRIMARY KEY,
                telegram_user_id INTEGER NOT NULL,
                criado_em TEXT NOT NULL,
                expira_em TEXT NOT NULL,
                usado_em TEXT
            )
            """
        )
        c.execute(
            """
            CREATE TABLE usuarios (
                telegram_user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                criado_em TEXT NOT NULL
            )
            """
        )
        c.execute(
            """
            CREATE TABLE livros (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_user_id INTEGER,
                titulo TEXT NOT NULL,
                autor TEXT,
                paginas INTEGER,
                colecao TEXT,
                status TEXT,
                asin TEXT
            )
            """
        )
    db.criar_tabela()
    with db.conectar() as c:
        cols = {row[1] for row in c.execute("PRAGMA table_info(link_codes)")}
    assert "claim_token" in cols
