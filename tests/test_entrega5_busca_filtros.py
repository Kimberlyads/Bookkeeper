"""Testes da Entrega 5: busca, detalhes, filtros e comandos (mocks)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import asyncio
import pytest

import bookkeeper.database as db
from bookkeeper.bot import (
    _formatar_detalhe_livro,
    _parse_filtro_args,
    _url_capa_valida,
    buscar,
    filtrar,
    livro,
    paginar_busca_ou_filtro,
)


@pytest.fixture()
def banco_tmp(tmp_path, monkeypatch):
    caminho = tmp_path / "teste.db"
    monkeypatch.setattr(db, "CAMINHO_BANCO", caminho)
    db.criar_tabela()
    return caminho


def _seed(user_id: int):
    db.importar_livros_kindle(
        user_id,
        [
            {
                "title": "O Hobbit",
                "authors": ["J. R. R. Tolkien"],
                "asin": "B00HOBBIT",
                "productImage": "https://example.com/hobbit.jpg",
                "acquiredDate": "2019-01-01",
                "originType": "Purchase",
                "isPurchased": True,
                "read": True,
            },
            {
                "title": "Duna",
                "authors": ["Frank Herbert"],
                "asin": "B00DUNA",
                "read": False,
            },
            {
                "title": "Guia do Mochileiro",
                "authors": ["Douglas Adams"],
                "asin": "B00GUIA",
                "readStatus": "reading",
            },
            {
                "title": "O Tempo e o Vento",
                "authors": ["Érico Veríssimo"],
                "asin": "B00ERICO",
                "read": False,
            },
        ],
    )
    with db.conectar() as c:
        c.execute(
            """
            UPDATE livros SET colecao = 'Clássicos', status = 'Lido'
            WHERE telegram_user_id = ? AND asin = 'B00HOBBIT'
            """,
            (user_id,),
        )
        c.execute(
            """
            UPDATE livros SET colecao = 'Sci-Fi', status = 'Pendente'
            WHERE telegram_user_id = ? AND asin = 'B00DUNA'
            """,
            (user_id,),
        )
        c.execute(
            """
            UPDATE livros SET colecao = 'Sci-Fi', status = 'Lendo'
            WHERE telegram_user_id = ? AND asin = 'B00GUIA'
            """,
            (user_id,),
        )
        c.execute(
            """
            UPDATE livros SET colecao = 'Brasileiros', status = 'Pendente'
            WHERE telegram_user_id = ? AND asin = 'B00ERICO'
            """,
            (user_id,),
        )


def _mock_update(user_id: int = 1, args=None, callback_data=None):
    message = AsyncMock()
    message.reply_text = AsyncMock()
    message.reply_photo = AsyncMock()
    user = SimpleNamespace(id=user_id)
    update = MagicMock()
    update.effective_message = message
    update.effective_user = user
    update.callback_query = None
    if callback_data is not None:
        query = AsyncMock()
        query.data = callback_data
        query.from_user = user
        query.answer = AsyncMock()
        query.edit_message_text = AsyncMock()
        update.callback_query = query
    context = MagicMock()
    context.args = args or []
    context.user_data = {}
    return update, context, message


# --- database / busca ---

def test_buscar_por_titulo(banco_tmp):
    _seed(1)
    r = db.buscar_livros(1, "hobbit")
    assert len(r) == 1
    assert r[0]["titulo"] == "O Hobbit"


def test_buscar_por_autor(banco_tmp):
    _seed(1)
    r = db.buscar_livros(1, "tolkien")
    assert len(r) == 1


def test_buscar_sem_resultados(banco_tmp):
    _seed(1)
    assert db.buscar_livros(1, "xyzinexistente") == []


def test_buscar_ignora_acentos_e_maiusculas(banco_tmp):
    _seed(1)
    for termo in ("ÉRICO", "Érico", "erico", "VERISSIMO", "veríssimo"):
        r = db.buscar_livros(1, termo)
        assert len(r) >= 1, termo
        assert any("Érico" in (row["autor"] or "") or "Veríssimo" in (row["autor"] or "") for row in r)


def test_obter_livro_existente_por_id_e_titulo(banco_tmp):
    _seed(1)
    encontrados = db.buscar_livros(1, "Duna")
    livro_id = encontrados[0]["id"]
    assert db.obter_livro(1, livro_id=livro_id)["titulo"] == "Duna"
    assert db.obter_livro(1, titulo="Duna")["asin"] == "B00DUNA"


def test_obter_livro_inexistente(banco_tmp):
    _seed(1)
    assert db.obter_livro(1, livro_id=999999) is None
    assert db.obter_livro(1, titulo="Não Existe") is None


def test_filtrar_por_status(banco_tmp):
    _seed(1)
    lidos = db.filtrar_livros(1, status="Lido")
    assert len(lidos) == 1
    assert lidos[0]["titulo"] == "O Hobbit"


def test_filtrar_por_colecao(banco_tmp):
    _seed(1)
    assert len(db.filtrar_livros(1, colecao="Sci-Fi")) == 2


def test_filtrar_combinado_status_e_colecao(banco_tmp):
    _seed(1)
    r = db.filtrar_livros(1, status="Lendo", colecao="Sci-Fi")
    assert len(r) == 1
    assert r[0]["titulo"] == "Guia do Mochileiro"


def test_filtrar_legado_string_unica(banco_tmp):
    _seed(1)
    r = db.filtrar_livros(1, "Pendente")
    assert any(row["titulo"] == "Duna" for row in r)


def test_isolamento_busca_entre_usuarios(banco_tmp):
    _seed(10)
    _seed(11)
    with db.conectar() as c:
        c.execute(
            "UPDATE livros SET titulo = 'Só do onze' WHERE telegram_user_id = 11 AND asin = 'B00DUNA'"
        )
    assert db.buscar_livros(10, "Só do onze") == []
    assert len(db.buscar_livros(11, "Só do onze")) == 1


def test_detalhe_sem_metadados_nao_inventa(banco_tmp):
    _seed(1)
    row = db.obter_livro(1, titulo="Duna")
    texto, capa = _formatar_detalhe_livro(row)
    assert "Duna" in texto
    assert capa is None
    assert "Adquirido em" not in texto


def test_detalhe_com_capa(banco_tmp):
    _seed(1)
    row = db.obter_livro(1, titulo="O Hobbit")
    texto, capa = _formatar_detalhe_livro(row)
    assert capa == "https://example.com/hobbit.jpg"
    assert "Adquirido em" in texto
    assert _url_capa_valida(capa)


def test_parse_filtro_args():
    assert _parse_filtro_args([]) == (None, None, None)
    assert _parse_filtro_args(["Lido"]) == (None, None, "Lido")
    assert _parse_filtro_args(["Lendo;", "Sci-Fi"]) == ("Lendo", "Sci-Fi", None)


# --- comandos Telegram (async mocks) ---

def test_comando_buscar_com_resultados(banco_tmp):
    async def _run():
        _seed(1)
        update, context, message = _mock_update(1, args=["hobbit"])
        await buscar(update, context)
        message.reply_text.assert_awaited()
        texto = message.reply_text.await_args.args[0]
        assert "Hobbit" in texto
        assert "Busca:" in texto
    asyncio.run(_run())


def test_comando_buscar_sem_resultados(banco_tmp):
    async def _run():
        _seed(1)
        update, context, message = _mock_update(1, args=["zzzz_sem_livro"])
        await buscar(update, context)
        message.reply_text.assert_awaited()
        assert "Nenhum livro encontrado" in message.reply_text.await_args.args[0]
    asyncio.run(_run())


def test_comando_livro_id_valido_com_capa(banco_tmp):
    async def _run():
        _seed(1)
        row = db.obter_livro(1, titulo="O Hobbit")
        update, context, message = _mock_update(1, args=[str(row["id"])])
        await livro(update, context)
        message.reply_photo.assert_awaited()
        message.reply_text.assert_awaited()
        detalhe = message.reply_text.await_args.args[0]
        assert "O Hobbit" in detalhe
        assert "Adquirido em" in detalhe
        kwargs = message.reply_photo.await_args.kwargs
        assert kwargs.get("caption") in (None, "")
    asyncio.run(_run())


def test_comando_livro_id_invalido(banco_tmp):
    async def _run():
        _seed(1)
        update, context, message = _mock_update(1, args=["999999"])
        await livro(update, context)
        message.reply_text.assert_awaited()
        assert "Não encontrei" in message.reply_text.await_args.args[0]
        message.reply_photo.assert_not_awaited()
    asyncio.run(_run())


def test_comando_livro_capa_falha_envia_texto(banco_tmp):
    async def _run():
        _seed(1)
        row = db.obter_livro(1, titulo="O Hobbit")
        update, context, message = _mock_update(1, args=[str(row["id"])])
        message.reply_photo = AsyncMock(side_effect=RuntimeError("falha de rede"))
        await livro(update, context)
        message.reply_text.assert_awaited()
        texto = message.reply_text.await_args.args[0]
        assert "O Hobbit" in texto
        assert "Capa:" in texto
    asyncio.run(_run())


def test_comando_filtrar_status(banco_tmp):
    async def _run():
        _seed(1)
        update, context, message = _mock_update(1, args=["Lido"])
        await filtrar(update, context)
        message.reply_text.assert_awaited()
        assert "Hobbit" in message.reply_text.await_args.args[0]
    asyncio.run(_run())


def test_comando_filtrar_colecao(banco_tmp):
    async def _run():
        _seed(1)
        update, context, message = _mock_update(1, args=["Sci-Fi"])
        await filtrar(update, context)
        texto = message.reply_text.await_args.args[0]
        assert "Duna" in texto or "Guia" in texto
    asyncio.run(_run())


def test_paginacao_busca_botoes(banco_tmp, monkeypatch):
    async def _run():
        _seed(1)
        import bookkeeper.bot as bot_mod
        monkeypatch.setattr(bot_mod, "LIVROS_POR_PAGINA", 1)
        update, context, message = _mock_update(1, args=["a"])
        await buscar(update, context)
        markup = message.reply_text.await_args.kwargs.get("reply_markup")
        assert markup is not None
        context.user_data["busca_termo"] = "a"
        update2, context2, _ = _mock_update(1, callback_data="busca:1")
        context2.user_data = context.user_data
        await paginar_busca_ou_filtro(update2, context2)
        update2.callback_query.edit_message_text.assert_awaited()
    asyncio.run(_run())


def test_paginacao_isolamento_entre_usuarios(banco_tmp, monkeypatch):
    async def _run():
        import bookkeeper.bot as bot_mod
        monkeypatch.setattr(bot_mod, "LIVROS_POR_PAGINA", 1)
        _seed(20)
        _seed(21)
        with db.conectar() as c:
            c.execute(
                "UPDATE livros SET titulo = 'ExclusivoVinte' WHERE telegram_user_id = 20 AND asin = 'B00DUNA'"
            )
            c.execute(
                "UPDATE livros SET titulo = 'ExclusivoVinteUm' WHERE telegram_user_id = 21 AND asin = 'B00DUNA'"
            )
        u20, c20, m20 = _mock_update(20, args=["ExclusivoVinte"])
        await buscar(u20, c20)
        texto20 = m20.reply_text.await_args.args[0]
        assert "ExclusivoVinte" in texto20
        assert "ExclusivoVinteUm" not in texto20
        u21, c21, _ = _mock_update(21, callback_data="busca:0")
        c21.user_data = {"busca_termo": "ExclusivoVinteUm"}
        await paginar_busca_ou_filtro(u21, c21)
        texto21 = u21.callback_query.edit_message_text.await_args.args[0]
        assert "ExclusivoVinteUm" in texto21
        assert "ExclusivoVinte\n" not in texto21 or "ExclusivoVinteUm" in texto21
    asyncio.run(_run())
