"""Testes da Entrega 2: status Desconhecido e deduplicação conservadora."""

from __future__ import annotations

import pytest

import bookkeeper.database as db


@pytest.fixture()
def banco_tmp(tmp_path, monkeypatch):
    caminho = tmp_path / "teste2.db"
    monkeypatch.setattr(db, "CAMINHO_BANCO", caminho)
    db.criar_tabela()
    return caminho


def test_export_sem_leitura_vira_desconhecido(banco_tmp):
    db.garantir_usuario(1)
    r = db.importar_livros_kindle(
        1,
        [{"title": "Sem status", "authors": ["A"], "asin": "B001"}],
    )
    assert r["adicionados"] == 1
    livros = db.listar_livros(1)
    assert livros[0][4] == db.STATUS_DESCONHECIDO


def test_export_read_false_vira_pendente(banco_tmp):
    db.garantir_usuario(2)
    db.importar_livros_kindle(
        2, [{"title": "Nao lido", "authors": ["A"], "asin": "B002", "read": False}]
    )
    assert db.listar_livros(2)[0][4] == db.STATUS_PENDENTE


def test_export_read_true_vira_lido(banco_tmp):
    db.garantir_usuario(3)
    db.importar_livros_kindle(
        3, [{"title": "Lido", "authors": ["A"], "asin": "B003", "read": True}]
    )
    assert db.listar_livros(3)[0][4] == db.STATUS_LIDO


def test_contar_nao_mistura_desconhecido_com_pendente(banco_tmp):
    db.garantir_usuario(4)
    db.adicionar_livro(4, "A", "X", None, "C", db.STATUS_PENDENTE, "P1")
    db.adicionar_livro(4, "B", "Y", None, "C", db.STATUS_DESCONHECIDO, "D1")
    contagens = dict(db.contar_livros(4))
    assert contagens.get("Pendente") == 1
    assert contagens.get("Desconhecido") == 1


def test_reimport_com_asin_preserva_status_manual(banco_tmp):
    db.garantir_usuario(5)
    db.adicionar_livro(5, "Manual", "Autora", 10, "Minha coleção", "Lendo", "ASIN5")
    r = db.importar_livros_kindle(
        5,
        [
            {
                "title": "Outro titulo Amazon",
                "authors": ["Outro"],
                "asin": "ASIN5",
                "read": True,
            }
        ],
    )
    assert r["adicionados"] == 0
    assert r["ignorados"] == 1
    livro = db.listar_livros(5)[0]
    assert livro[0] == "Manual"
    assert livro[3] == "Minha coleção"
    assert livro[4] == "Lendo"


def test_sem_asin_match_exato_confiavel_nao_duplica(banco_tmp):
    db.garantir_usuario(6)
    db.importar_livros_kindle(
        6, [{"title": "Mesmo", "authors": ["Fulano de Tal"]}]
    )
    r = db.importar_livros_kindle(
        6, [{"title": "mesmo", "authors": ["fulano de tal"]}]
    )
    assert r["adicionados"] == 0
    assert r["ignorados"] == 1
    assert len(db.listar_livros(6)) == 1


def test_sem_asin_autor_desconhecido_nao_bloqueia_insert(banco_tmp):
    """Autor genérico não é prova de identidade — permite novo registro."""
    db.garantir_usuario(7)
    db.importar_livros_kindle(
        7, [{"title": "Obra", "authors": []}]
    )
    r = db.importar_livros_kindle(
        7, [{"title": "Obra", "authors": []}]
    )
    # Conservador: sem autor confiável, não deduplica → segundo insert ocorre.
    assert r["adicionados"] == 1
    assert len(db.listar_livros(7)) == 2


def test_sem_asin_titulos_diferentes_nao_colidem(banco_tmp):
    db.garantir_usuario(8)
    db.importar_livros_kindle(
        8, [{"title": "Livro Um", "authors": ["Autora"]}]
    )
    r = db.importar_livros_kindle(
        8, [{"title": "Livro Dois", "authors": ["Autora"]}]
    )
    assert r["adicionados"] == 1
    assert len(db.listar_livros(8)) == 2


def test_mesmo_asin_usuarios_diferentes_ok(banco_tmp):
    db.garantir_usuario(9)
    db.garantir_usuario(10)
    db.importar_livros_kindle(
        9, [{"title": "Shared", "authors": ["A"], "asin": "SHARED1"}]
    )
    r = db.importar_livros_kindle(
        10, [{"title": "Shared", "authors": ["A"], "asin": "SHARED1"}]
    )
    assert r["adicionados"] == 1
    assert len(db.listar_livros(9)) == 1
    assert len(db.listar_livros(10)) == 1
