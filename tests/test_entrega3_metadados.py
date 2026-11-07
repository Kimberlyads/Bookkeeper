"""Testes da Entrega 3: metadados Kindle e preservação de dados."""

from __future__ import annotations

import sqlite3

import bookkeeper.database as db


def banco_tmp(tmp_path, monkeypatch):
    caminho = tmp_path / "teste.db"
    monkeypatch.setattr(db, "CAMINHO_BANCO", caminho)
    db.criar_tabela()
    return caminho


def livro(uid, asin):
    with db.conectar() as c:
        return c.execute(
            "SELECT * FROM livros WHERE telegram_user_id = ? AND asin = ?",
            (uid, asin),
        ).fetchone()


def test_migracao_legada_preserva_registro(tmp_path, monkeypatch):
    caminho = tmp_path / "legado.db"
    monkeypatch.setattr(db, "CAMINHO_BANCO", caminho)
    with sqlite3.connect(caminho) as c:
        c.execute("""CREATE TABLE usuarios (
            telegram_user_id INTEGER PRIMARY KEY, username TEXT,
            first_name TEXT, criado_em TEXT NOT NULL)""")
        c.execute("""CREATE TABLE livros (
            id INTEGER PRIMARY KEY AUTOINCREMENT, telegram_user_id INTEGER,
            titulo TEXT NOT NULL, autor TEXT, paginas INTEGER, colecao TEXT,
            status TEXT, asin TEXT)""")
        c.execute("""INSERT INTO livros
            (telegram_user_id, titulo, autor, status, asin)
            VALUES (1, 'Livro antigo', 'Autora', 'Lendo', 'OLD1')""")
    db.criar_tabela()
    row = livro(1, "OLD1")
    assert row["titulo"] == "Livro antigo" and row["status"] == "Lendo"
    assert all(k in row.keys() for k in (
        "content_identifier", "product_image", "acquired_date",
        "origin_type", "is_purchased"))


def test_insere_todos_os_metadados(tmp_path, monkeypatch):
    banco_tmp(tmp_path, monkeypatch)
    r = db.importar_livros_kindle(2, [{
        "title": "Completo", "authors": ["A"], "asin": "FULL1",
        "contentIdentifier": "CID1", "productImage": "capa.jpg",
        "acquiredDate": "2024-01-01", "originType": "Purchase",
        "isPurchased": True, "read": False,
    }])
    row = livro(2, "FULL1")
    assert r["adicionados"] == 1
    assert (row["content_identifier"], row["product_image"]) == ("CID1", "capa.jpg")
    assert (row["acquired_date"], row["origin_type"], row["is_purchased"]) == (
        "2024-01-01", "Purchase", 1)


def test_metadados_parciais_e_is_purchased_nulo(tmp_path, monkeypatch):
    banco_tmp(tmp_path, monkeypatch)
    db.importar_livros_kindle(3, [{
        "title": "Parcial", "asin": "PART1", "productImage": "capa.jpg",
        "isPurchased": "true",
    }])
    row = livro(3, "PART1")
    assert row["product_image"] == "capa.jpg"
    assert row["is_purchased"] is None
    assert row["content_identifier"] is None


def test_reimportacao_incompleta_nao_apaga_metadados(tmp_path, monkeypatch):
    banco_tmp(tmp_path, monkeypatch)
    db.importar_livros_kindle(4, [{
        "title": "Livro", "asin": "KEEP1", "productImage": "capa.jpg",
        "acquiredDate": "2020-01-01", "originType": "Purchase",
        "contentIdentifier": "CID", "isPurchased": True, "read": False,
    }])
    db.importar_livros_kindle(4, [{"title": "Livro", "asin": "KEEP1", "read": True}])
    row = livro(4, "KEEP1")
    assert (row["product_image"], row["content_identifier"]) == ("capa.jpg", "CID")
    assert row["acquired_date"] == "2020-01-01"
    assert row["origin_type"] == "Purchase" and row["is_purchased"] == 1
    assert row["status"] == "Pendente"


def test_enriquece_null_e_string_vazia(tmp_path, monkeypatch):
    banco_tmp(tmp_path, monkeypatch)
    db.importar_livros_kindle(5, [{"title": "Vazio", "asin": "FILL1"}])
    with db.conectar() as c:
        c.execute("UPDATE livros SET content_identifier = '' WHERE asin = 'FILL1'")
    r = db.importar_livros_kindle(5, [{
        "title": "Outro título", "asin": "FILL1",
        "contentIdentifier": "CID-NOVO", "productImage": "nova.jpg",
    }])
    row = livro(5, "FILL1")
    assert r["enriquecidos"] == 1
    assert row["content_identifier"] == "CID-NOVO"
    assert row["product_image"] == "nova.jpg"


def test_nao_substitui_metadado_ja_preenchido(tmp_path, monkeypatch):
    banco_tmp(tmp_path, monkeypatch)
    db.importar_livros_kindle(6, [{
        "title": "Livro", "asin": "KEEP2", "productImage": "capa-original.jpg",
        "originType": "Purchase",
    }])
    db.importar_livros_kindle(6, [{
        "title": "Livro", "asin": "KEEP2", "productImage": "capa-nova.jpg",
        "originType": "KindleUnlimited",
    }])
    row = livro(6, "KEEP2")
    assert row["product_image"] == "capa-original.jpg"
    assert row["origin_type"] == "Purchase"


def test_preserva_status_colecao_titulo_e_autor_manuais(tmp_path, monkeypatch):
    banco_tmp(tmp_path, monkeypatch)
    db.importar_livros_kindle(7, [{
        "title": "Título manual", "authors": ["Autora manual"],
        "asin": "MANUAL1", "read": False,
    }])
    with db.conectar() as c:
        c.execute("""UPDATE livros SET status='Lendo', colecao='Favoritos'
            WHERE telegram_user_id=7 AND asin='MANUAL1'""")
    db.importar_livros_kindle(7, [{
        "title": "Título Amazon", "authors": ["Outro autor"],
        "asin": "MANUAL1", "productImage": "capa.jpg", "read": True,
    }])
    row = livro(7, "MANUAL1")
    assert (row["titulo"], row["autor"]) == ("Título manual", "Autora manual")
    assert (row["status"], row["colecao"]) == ("Lendo", "Favoritos")
    assert row["product_image"] == "capa.jpg"


def test_dedupe_asin_e_sem_asin_permanece(tmp_path, monkeypatch):
    banco_tmp(tmp_path, monkeypatch)
    primeiro = db.importar_livros_kindle(8, [
        {"title": "Com ASIN", "authors": ["A"], "asin": "DUP1"},
        {"title": "Sem ASIN", "authors": ["Autora confiável"]},
    ])
    segundo = db.importar_livros_kindle(8, [
        {"title": "Com ASIN", "authors": ["A"], "asin": "DUP1"},
        {"title": "Sem ASIN", "authors": ["Autora confiável"]},
    ])
    assert primeiro["adicionados"] == 2
    assert segundo["adicionados"] == 0 and segundo["ignorados"] == 2


def test_isolamento_entre_usuarios(tmp_path, monkeypatch):
    banco_tmp(tmp_path, monkeypatch)
    for uid, capa in ((9, "u9.jpg"), (10, "u10.jpg")):
        db.importar_livros_kindle(uid, [{
            "title": "Mesmo livro", "asin": "SHARED1", "productImage": capa,
        }])
    assert livro(9, "SHARED1")["product_image"] == "u9.jpg"
    assert livro(10, "SHARED1")["product_image"] == "u10.jpg"
    assert len(db.listar_livros(9)) == len(db.listar_livros(10)) == 1


def test_content_identifier_nao_e_unico(tmp_path, monkeypatch):
    banco_tmp(tmp_path, monkeypatch)
    for asin in ("CID-DUP-A", "CID-DUP-B"):
        db.importar_livros_kindle(11, [{
            "title": asin, "asin": asin, "contentIdentifier": "MESMO-CID",
        }])
    with db.conectar() as c:
        total = c.execute(
            "SELECT COUNT(*) FROM livros WHERE telegram_user_id=11 AND content_identifier='MESMO-CID'"
        ).fetchone()[0]
        indices = c.execute("PRAGMA index_list(livros)").fetchall()
    assert total == 2
    assert not any(
        row["unique"] and "content_identifier" in row["name"]
        for row in indices
    )
