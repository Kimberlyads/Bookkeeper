"""Camada de banco SQLite multi-usuário do Bookkeeper.

Isola bibliotecas por telegram_user_id.
Não armazena senhas, cookies nem tokens da Amazon.
"""

from __future__ import annotations

import json
import secrets
import sqlite3
import string
from datetime import datetime, timedelta, timezone
from pathlib import Path

CAMINHO_BANCO = Path(__file__).resolve().parent.parent / "biblioteca.db"
CAMINHO_JSON = Path(__file__).resolve().parent.parent / "kindlogger-export.json"

LINK_CODE_TTL_MINUTES = 30
LINK_CODE_LENGTH = 8


def conectar():
    conexao = sqlite3.connect(CAMINHO_BANCO)
    conexao.row_factory = sqlite3.Row
    conexao.execute("PRAGMA foreign_keys = ON")
    return conexao


def criar_tabela():
    """Cria/migra o schema sem destruir dados existentes."""
    with conectar() as conexao:
        conexao.execute(
            """
            CREATE TABLE IF NOT EXISTS usuarios (
                telegram_user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                criado_em TEXT NOT NULL
            )
            """
        )
        conexao.execute(
            """
            CREATE TABLE IF NOT EXISTS livros (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_user_id INTEGER,
                titulo TEXT NOT NULL,
                autor TEXT,
                paginas INTEGER,
                colecao TEXT,
                status TEXT,
                asin TEXT,
                FOREIGN KEY (telegram_user_id)
                    REFERENCES usuarios(telegram_user_id)
            )
            """
        )
        colunas = {
            coluna[1] for coluna in conexao.execute("PRAGMA table_info(livros)")
        }
        if "asin" not in colunas:
            conexao.execute("ALTER TABLE livros ADD COLUMN asin TEXT")
        if "telegram_user_id" not in colunas:
            conexao.execute(
                "ALTER TABLE livros ADD COLUMN telegram_user_id INTEGER"
            )

        # Remove o índice global legado para permitir o mesmo ASIN
        # em bibliotecas de usuários diferentes.
        conexao.execute("DROP INDEX IF EXISTS indice_asin_unico")
        conexao.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS indice_asin_por_usuario
            ON livros(telegram_user_id, asin)
            WHERE asin IS NOT NULL
            """
        )
        conexao.execute(
            """
            CREATE TABLE IF NOT EXISTS link_codes (
                code TEXT PRIMARY KEY,
                telegram_user_id INTEGER NOT NULL,
                criado_em TEXT NOT NULL,
                expira_em TEXT NOT NULL,
                usado_em TEXT,
                FOREIGN KEY (telegram_user_id)
                    REFERENCES usuarios(telegram_user_id)
            )
            """
        )


def garantir_usuario(telegram_user_id: int, username=None, first_name=None):
    agora = datetime.now(timezone.utc).isoformat()
    with conectar() as conexao:
        conexao.execute(
            """
            INSERT INTO usuarios (telegram_user_id, username, first_name, criado_em)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(telegram_user_id) DO UPDATE SET
                username = COALESCE(excluded.username, usuarios.username),
                first_name = COALESCE(excluded.first_name, usuarios.first_name)
            """,
            (telegram_user_id, username, first_name, agora),
        )


def _gerar_codigo() -> str:
    alfabeto = string.ascii_uppercase + string.digits
    alfabeto = alfabeto.replace("0", "").replace("O", "").replace("1", "").replace("I", "")
    return "".join(secrets.choice(alfabeto) for _ in range(LINK_CODE_LENGTH))


def criar_link_code(telegram_user_id: int) -> tuple[str, datetime]:
    """Gera código único de uso único. Invalida códigos anteriores do usuário."""
    garantir_usuario(telegram_user_id)
    agora = datetime.now(timezone.utc)
    expira = agora + timedelta(minutes=LINK_CODE_TTL_MINUTES)
    with conectar() as conexao:
        conexao.execute(
            """
            UPDATE link_codes
            SET usado_em = ?
            WHERE telegram_user_id = ?
              AND usado_em IS NULL
            """,
            (agora.isoformat(), telegram_user_id),
        )
        for _ in range(20):
            code = _gerar_codigo()
            try:
                conexao.execute(
                    """
                    INSERT INTO link_codes
                        (code, telegram_user_id, criado_em, expira_em, usado_em)
                    VALUES (?, ?, ?, ?, NULL)
                    """,
                    (code, telegram_user_id, agora.isoformat(), expira.isoformat()),
                )
                return code, expira
            except sqlite3.IntegrityError:
                continue
    raise RuntimeError("Não foi possível gerar um código de vínculo único.")


def consumir_link_code(code: str) -> int | None:
    """Valida e consome o código. Retorna telegram_user_id ou None."""
    if not code:
        return None
    code = code.strip().upper()
    agora = datetime.now(timezone.utc)
    with conectar() as conexao:
        row = conexao.execute(
            """
            SELECT code, telegram_user_id, expira_em, usado_em
            FROM link_codes
            WHERE code = ?
            """,
            (code,),
        ).fetchone()
        if row is None or row["usado_em"] is not None:
            return None
        try:
            expira = datetime.fromisoformat(row["expira_em"])
        except ValueError:
            return None
        if expira.tzinfo is None:
            expira = expira.replace(tzinfo=timezone.utc)
        if agora > expira:
            return None
        cursor = conexao.execute(
            """
            UPDATE link_codes
            SET usado_em = ?
            WHERE code = ?
              AND usado_em IS NULL
              AND expira_em > ?
            """,
            (agora.isoformat(), code, agora.isoformat()),
        )
        # UPDATE condicional evita consumo duplo em requisições simultâneas.
        if cursor.rowcount != 1:
            return None
        return int(row["telegram_user_id"])


def adicionar_livro(
    telegram_user_id: int, titulo, autor, paginas, colecao,
    status="Pendente", asin=None,
):
    garantir_usuario(telegram_user_id)
    with conectar() as conexao:
        conexao.execute(
            """
            INSERT INTO livros
                (telegram_user_id, titulo, autor, paginas, colecao, status, asin)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (telegram_user_id, titulo, autor, paginas, colecao, status, asin),
        )


def atualizar_status(telegram_user_id: int, titulo, status):
    with conectar() as conexao:
        cursor = conexao.execute(
            """
            UPDATE livros SET status = ?
            WHERE telegram_user_id = ?
              AND TRIM(LOWER(titulo)) = TRIM(LOWER(?))
            """,
            (status, telegram_user_id, titulo),
        )
        return cursor.rowcount


def listar_livros(telegram_user_id: int):
    with conectar() as conexao:
        return conexao.execute(
            """
            SELECT titulo, autor, paginas, colecao, status
            FROM livros WHERE telegram_user_id = ?
            ORDER BY titulo COLLATE NOCASE
            """,
            (telegram_user_id,),
        ).fetchall()


def contar_livros(telegram_user_id: int):
    with conectar() as conexao:
        return conexao.execute(
            """
            SELECT
                CASE
                    WHEN LOWER(TRIM(status)) IN ('quero ler', 'pendente') THEN 'Pendente'
                    WHEN LOWER(TRIM(status)) = 'lendo' THEN 'Lendo'
                    WHEN LOWER(TRIM(status)) = 'lido' THEN 'Lido'
                    ELSE 'Pendente'
                END AS status_normalizado,
                COUNT(*)
            FROM livros WHERE telegram_user_id = ?
            GROUP BY status_normalizado
            """,
            (telegram_user_id,),
        ).fetchall()


def filtrar_livros(telegram_user_id: int, filtro):
    with conectar() as conexao:
        return conexao.execute(
            """
            SELECT titulo, autor, paginas, colecao, status
            FROM livros
            WHERE telegram_user_id = ?
              AND (
                    LOWER(TRIM(status)) = LOWER(TRIM(?))
                 OR LOWER(TRIM(colecao)) = LOWER(TRIM(?))
              )
            ORDER BY titulo COLLATE NOCASE
            """,
            (telegram_user_id, filtro, filtro),
        ).fetchall()


def _autor_de_livro_exportado(livro: dict) -> str:
    authors = livro.get("authors") or livro.get("author")
    if isinstance(authors, list):
        nomes = []
        for item in authors:
            if isinstance(item, str):
                nomes.append(item)
            elif isinstance(item, dict):
                nome = item.get("name") or item.get("authorName")
                if nome:
                    nomes.append(str(nome))
        return ", ".join(nomes) if nomes else "Autor desconhecido"
    if isinstance(authors, str) and authors.strip():
        return authors.strip()
    return "Autor desconhecido"


def _status_de_livro_exportado(livro: dict) -> tuple[str, str]:
    read_status = (livro.get("readStatus") or "").strip().lower()
    if read_status in {"read", "lido", "finished"}:
        return "Lido", "Lidos"
    if read_status in {"reading", "lendo"}:
        return "Lendo", "Lendo"
    read_value = livro.get("read")
    if read_value is True:
        return "Lido", "Lidos"
    if read_value is False:
        return "Pendente", "Quero ler"
    return "Pendente", "Importados — revisar status"


def importar_livros_kindle(telegram_user_id: int, books: list) -> dict:
    """Importa lista de livros para o usuário. Idempotente por ASIN."""
    garantir_usuario(telegram_user_id)
    adicionados = 0
    ignorados = 0
    with conectar() as conexao:
        for livro in books or []:
            if not isinstance(livro, dict):
                ignorados += 1
                continue
            titulo = (livro.get("title") or "").strip()
            if not titulo:
                ignorados += 1
                continue
            autor = _autor_de_livro_exportado(livro)
            asin = (livro.get("asin") or "").strip() or None
            paginas = livro.get("pages")
            if not isinstance(paginas, int) or paginas < 0:
                paginas = None
            status_livro, colecao = _status_de_livro_exportado(livro)
            try:
                cursor = conexao.execute(
                    """
                    INSERT INTO livros
                        (telegram_user_id, titulo, autor, paginas, colecao, status, asin)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (telegram_user_id, titulo, autor, paginas, colecao, status_livro, asin),
                )
                if cursor.rowcount > 0:
                    adicionados += 1
                else:
                    ignorados += 1
            except sqlite3.IntegrityError:
                ignorados += 1
    return {
        "telegram_user_id": telegram_user_id,
        "adicionados": adicionados,
        "ignorados": ignorados,
        "total_recebidos": len(books or []),
    }


def importar_kindlogger(telegram_user_id: int | None = None):
    """Importação legada a partir de kindlogger-export.json (arquivo local)."""
    if not CAMINHO_JSON.exists():
        print("Arquivo kindlogger-export.json não encontrado; importação ignorada.")
        return
    if telegram_user_id is None:
        print(
            "importar_kindlogger: informe telegram_user_id para associar os livros "
            "a um usuário. Importação ignorada para não misturar bibliotecas."
        )
        return
    with CAMINHO_JSON.open("r", encoding="utf-8") as arquivo:
        dados = json.load(arquivo)
    resultado = importar_livros_kindle(telegram_user_id, dados.get("books", []))
    print(
        f"Importação concluída: {resultado['adicionados']} livro(s) adicionado(s), "
        f"{resultado['ignorados']} ignorado(s)."
    )


if __name__ == "__main__":
    criar_tabela()
    print(f"Banco pronto em {CAMINHO_BANCO}")
