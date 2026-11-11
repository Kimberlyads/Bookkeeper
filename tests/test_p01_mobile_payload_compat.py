"""Compatibilidade payload coletor mobile ↔ backend real."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

import bookkeeper.database as db


@pytest.fixture()
def banco_tmp(tmp_path, monkeypatch):
    caminho = tmp_path / "teste.db"
    monkeypatch.setattr(db, "CAMINHO_BANCO", caminho)
    db.criar_tabela()
    return caminho


def _books(n=2, prefix="M"):
    return [
        {
            "title": f"{prefix} Book {i}",
            "authors": [f"Author {i}"],
            "asin": f"B00{prefix}{i:04d}",
            "contentIdentifier": f"CID-{prefix}-{i}",
            "productImage": f"https://example.com/{i}.jpg",
            "acquiredDate": "2022-01-01",
            "readStatus": None,
            "collectionList": [],
            "originType": "Purchase",
            "isPurchased": True,
        }
        for i in range(n)
    ]


def test_payload_formato_coletor_mobile_importa(banco_tmp):
    books = _books(2)
    books.append(
        {
            "title": "Sem ASIN",
            "authors": ["Outro"],
            "asin": None,
            "productImage": None,
            "readStatus": None,
        }
    )
    r = db.importar_livros_kindle(42, books)
    assert r["adicionados"] == 3


def test_reimport_mesmo_asin_nao_duplica(banco_tmp):
    books = _books(1, "D")
    assert db.importar_livros_kindle(7, books)["adicionados"] == 1
    assert db.importar_livros_kindle(7, books)["adicionados"] == 0
    assert len(db.listar_livros(7)) == 1


def test_isolamento_usuarios_mobile_payload(banco_tmp):
    books = _books(1, "I")
    db.importar_livros_kindle(100, books)
    db.importar_livros_kindle(200, books)
    assert len(db.listar_livros(100)) == 1
    assert len(db.listar_livros(200)) == 1


def test_preserva_status_manual_na_reimportacao(banco_tmp):
    books = _books(1, "S")
    db.importar_livros_kindle(5, books)
    with db.conectar() as c:
        c.execute(
            "UPDATE livros SET status = 'Lido', colecao = 'Manual' "
            "WHERE telegram_user_id = 5"
        )
    db.importar_livros_kindle(5, books)
    row = db.listar_livros(5)[0]
    assert row["status"] == "Lido"
    assert row["colecao"] == "Manual"


def test_claim_codigo_invalido_e_uso_unico(banco_tmp):
    code, _exp = db.criar_link_code(999)
    assert db.claim_link_code("ZZZZINVALID") is None
    claimed = db.claim_link_code(code)
    assert claimed is not None
    # Segundo claim do mesmo código falha (já consumido na reserva)
    assert db.claim_link_code(code) is None


def test_codigo_expirado(banco_tmp):
    code, _exp = db.criar_link_code(1)
    passado = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    with db.conectar() as c:
        c.execute(
            "UPDATE link_codes SET expira_em = ? WHERE code = ?",
            (passado, code),
        )
    assert db.claim_link_code(code) is None
