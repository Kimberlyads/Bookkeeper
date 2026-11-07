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

# Status de leitura reconhecidos pelo sistema.
STATUS_PENDENTE = "Pendente"
STATUS_LENDO = "Lendo"
STATUS_LIDO = "Lido"
STATUS_DESCONHECIDO = "Desconhecido"
STATUS_VALIDOS = {
    STATUS_PENDENTE,
    STATUS_LENDO,
    STATUS_LIDO,
    STATUS_DESCONHECIDO,
}
AUTOR_DESCONHECIDO = "Autor desconhecido"


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
                claim_token TEXT,
                FOREIGN KEY (telegram_user_id)
                    REFERENCES usuarios(telegram_user_id)
            )
            """
        )
        # Migração não destrutiva: bancos antigos sem claim_token.
        colunas_link = {
            coluna[1] for coluna in conexao.execute("PRAGMA table_info(link_codes)")
        }
        if "claim_token" not in colunas_link:
            conexao.execute(
                "ALTER TABLE link_codes ADD COLUMN claim_token TEXT"
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
    """Gera código único de uso único.

    Invalida todos os códigos anteriores do usuário (livres ou apenas
    reservados), limpando claim_token para que um release antigo não
    consiga reativá-los.
    """
    garantir_usuario(telegram_user_id)
    agora = datetime.now(timezone.utc)
    expira = agora + timedelta(minutes=LINK_CODE_TTL_MINUTES)
    with conectar() as conexao:
        # Revoga códigos anteriores — inclusive já claimados em import em andamento.
        conexao.execute(
            """
            UPDATE link_codes
            SET usado_em = COALESCE(usado_em, ?),
                claim_token = NULL
            WHERE telegram_user_id = ?
            """,
            (agora.isoformat(), telegram_user_id),
        )
        for _ in range(20):
            code = _gerar_codigo()
            try:
                conexao.execute(
                    """
                    INSERT INTO link_codes
                        (code, telegram_user_id, criado_em, expira_em, usado_em, claim_token)
                    VALUES (?, ?, ?, ?, NULL, NULL)
                    """,
                    (code, telegram_user_id, agora.isoformat(), expira.isoformat()),
                )
                return code, expira
            except sqlite3.IntegrityError:
                continue
    raise RuntimeError("Não foi possível gerar um código de vínculo único.")


def _normalizar_codigo(code: str | None) -> str | None:
    if not code:
        return None
    normalizado = code.strip().upper()
    return normalizado or None


def claim_link_code(code: str) -> tuple[int, str] | None:
    """Reserva atomicamente o código de vínculo.

    Retorna ``(telegram_user_id, claim_token)`` ou ``None``.
    O ``claim_token`` deve ser apresentado em ``release_link_code``;
    só a reserva que gerou o token consegue liberar o código.
    """
    code = _normalizar_codigo(code)
    if not code:
        return None
    agora = datetime.now(timezone.utc)
    token = secrets.token_urlsafe(16)
    with conectar() as conexao:
        conexao.execute("BEGIN IMMEDIATE")
        try:
            row = conexao.execute(
                """
                SELECT code, telegram_user_id, expira_em, usado_em, claim_token
                FROM link_codes
                WHERE code = ?
                """,
                (code,),
            ).fetchone()
            if row is None or row["usado_em"] is not None:
                conexao.rollback()
                return None
            try:
                expira = datetime.fromisoformat(row["expira_em"])
            except ValueError:
                conexao.rollback()
                return None
            if expira.tzinfo is None:
                expira = expira.replace(tzinfo=timezone.utc)
            if agora > expira:
                conexao.rollback()
                return None
            cursor = conexao.execute(
                """
                UPDATE link_codes
                SET usado_em = ?,
                    claim_token = ?
                WHERE code = ?
                  AND usado_em IS NULL
                  AND claim_token IS NULL
                """,
                (agora.isoformat(), token, code),
            )
            if cursor.rowcount != 1:
                conexao.rollback()
                return None
            conexao.commit()
            return int(row["telegram_user_id"]), token
        except Exception:
            conexao.rollback()
            raise


def release_link_code(code: str, claim_token: str | None) -> bool:
    """Libera um código reservado somente se o claim_token coincidir.

    Se o código foi revogado por ``criar_link_code`` (claim_token limpo)
    ou se o token for de outra reserva, a liberação falha e o código
    permanece inutilizável.
    """
    code = _normalizar_codigo(code)
    if not code or not claim_token:
        return False
    with conectar() as conexao:
        cursor = conexao.execute(
            """
            UPDATE link_codes
            SET usado_em = NULL,
                claim_token = NULL
            WHERE code = ?
              AND claim_token = ?
              AND usado_em IS NOT NULL
            """,
            (code, claim_token),
        )
        return cursor.rowcount == 1


def consumir_link_code(code: str) -> int | None:
    """Compatibilidade: reserva o código e descarta o claim_token.

    Preferir ``claim_link_code`` + ``release_link_code`` no fluxo de API.
    """
    resultado = claim_link_code(code)
    if resultado is None:
        return None
    return resultado[0]


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
                    WHEN LOWER(TRIM(status)) = 'desconhecido' THEN 'Desconhecido'
                    ELSE 'Desconhecido'
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
        return ", ".join(nomes) if nomes else AUTOR_DESCONHECIDO
    if isinstance(authors, str) and authors.strip():
        return authors.strip()
    return AUTOR_DESCONHECIDO


def _status_de_livro_exportado(livro: dict) -> tuple[str, str]:
    """Infere status a partir do export Kindle.

    Sem evidência de leitura, retorna Desconhecido — não assume Pendente.
    """
    read_status = (livro.get("readStatus") or "").strip().lower()
    if read_status in {"read", "lido", "finished"}:
        return STATUS_LIDO, "Lidos"
    if read_status in {"reading", "lendo"}:
        return STATUS_LENDO, "Lendo"
    if read_status in {"unread", "not_read", "pendente", "want_to_read"}:
        return STATUS_PENDENTE, "Quero ler"
    read_value = livro.get("read")
    if read_value is True:
        return STATUS_LIDO, "Lidos"
    if read_value is False:
        return STATUS_PENDENTE, "Quero ler"
    return STATUS_DESCONHECIDO, "Importados — revisar status"


def _autor_e_confiavel(autor: str | None) -> bool:
    """Autor genérico não serve para deduplicação conservadora."""
    if not autor:
        return False
    normalizado = autor.strip().casefold()
    if not normalizado:
        return False
    if normalizado == AUTOR_DESCONHECIDO.casefold():
        return False
    if normalizado in {"unknown", "desconhecido", "n/a", "na"}:
        return False
    return True


def _existe_livro_por_asin(conexao, telegram_user_id: int, asin: str) -> bool:
    row = conexao.execute(
        """
        SELECT 1 FROM livros
        WHERE telegram_user_id = ?
          AND asin = ?
        LIMIT 1
        """,
        (telegram_user_id, asin),
    ).fetchone()
    return row is not None


def _existe_candidato_sem_asin(
    conexao, telegram_user_id: int, titulo: str, autor: str
) -> bool:
    """Heurística conservadora: só evita insert se título e autor forem
    idênticos (case-insensitive) e o autor for confiável.

    Não trata título+autor como identidade absoluta — apenas reduz
    duplicatas óbvias sem apagar nem alterar registros existentes.
    """
    if not _autor_e_confiavel(autor):
        return False
    row = conexao.execute(
        """
        SELECT 1 FROM livros
        WHERE telegram_user_id = ?
          AND asin IS NULL
          AND LOWER(TRIM(titulo)) = LOWER(TRIM(?))
          AND LOWER(TRIM(autor)) = LOWER(TRIM(?))
        LIMIT 1
        """,
        (telegram_user_id, titulo, autor),
    ).fetchone()
    return row is not None


def importar_livros_kindle(telegram_user_id: int, books: list) -> dict:
    """Importa livros do export Kindle para o usuário.

    - Com ASIN: não duplica; não altera status/coleção/manuais existentes.
    - Sem ASIN: só evita insert quando título e autor confiável já existem
      com match exato normalizado; caso contrário, insere (evita falso positivo).
    - Status ausente no export vira Desconhecido, não Pendente.
    """
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

            # Já existe por ASIN: preservar registro manual, não sobrescrever.
            if asin and _existe_livro_por_asin(conexao, telegram_user_id, asin):
                ignorados += 1
                continue

            # Sem ASIN: dedupe conservadora (não é prova absoluta de identidade).
            if not asin and _existe_candidato_sem_asin(
                conexao, telegram_user_id, titulo, autor
            ):
                ignorados += 1
                continue

            try:
                cursor = conexao.execute(
                    """
                    INSERT INTO livros
                        (telegram_user_id, titulo, autor, paginas, colecao, status, asin)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        telegram_user_id,
                        titulo,
                        autor,
                        paginas,
                        colecao,
                        status_livro,
                        asin,
                    ),
                )
                if cursor.rowcount > 0:
                    adicionados += 1
                else:
                    ignorados += 1
            except sqlite3.IntegrityError:
                # Corrida com índice único de ASIN: preservar existente.
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
