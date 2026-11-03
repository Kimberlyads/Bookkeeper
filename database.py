import json
import sqlite3
from pathlib import Path

CAMINHO_BANCO = Path(__file__).resolve().parent / "biblioteca.db"
CAMINHO_JSON = Path(__file__).resolve().parent / "kindlogger-export.json"


def conectar():
    return sqlite3.connect(CAMINHO_BANCO)


def criar_tabela():
    with conectar() as conexao:
        conexao.execute(
            """
            CREATE TABLE IF NOT EXISTS livros (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                titulo TEXT NOT NULL,
                autor TEXT,
                paginas INTEGER,
                colecao TEXT,
                status TEXT,
                asin TEXT
            )
            """
        )

        colunas = {
            coluna[1] for coluna in conexao.execute("PRAGMA table_info(livros)")
        }
        if "asin" not in colunas:
            conexao.execute("ALTER TABLE livros ADD COLUMN asin TEXT")

        # SQLite permite múltiplos valores NULL em um índice UNIQUE.
        conexao.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS indice_asin_livros
            ON livros(asin)
            """
        )


def adicionar_livro(titulo, autor, paginas, colecao, status="Pendente", asin=None):
    with conectar() as conexao:
        conexao.execute(
            """
            INSERT INTO livros (titulo, autor, paginas, colecao, status, asin)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (titulo, autor, paginas, colecao, status, asin),
        )


def atualizar_status(titulo, status):
    # O status de leitura não deve sobrescrever a coleção escolhida pela pessoa.
    with conectar() as conexao:
        cursor = conexao.execute(
            """
            UPDATE livros
            SET status = ?
            WHERE TRIM(LOWER(titulo)) = TRIM(LOWER(?))
            """,
            (status, titulo),
        )
        return cursor.rowcount


def listar_livros():
    with conectar() as conexao:
        return conexao.execute(
            """
            SELECT titulo, autor, paginas, colecao, status
            FROM livros
            ORDER BY titulo COLLATE NOCASE
            """
        ).fetchall()


def contar_livros():
    with conectar() as conexao:
        return conexao.execute(
            """
            SELECT
                CASE
                    WHEN LOWER(TRIM(status)) IN ('quero ler', 'pendente')
                    THEN 'Pendente'
                    WHEN LOWER(TRIM(status)) = 'lendo'
                    THEN 'Lendo'
                    WHEN LOWER(TRIM(status)) = 'lido'
                    THEN 'Lido'
                    ELSE 'Pendente'
                END AS status_normalizado,
                COUNT(*)
            FROM livros
            GROUP BY status_normalizado
            """
        ).fetchall()


def filtrar_livros(filtro):
    with conectar() as conexao:
        return conexao.execute(
            """
            SELECT titulo, autor, paginas, colecao, status
            FROM livros
            WHERE LOWER(TRIM(status)) = LOWER(TRIM(?))
               OR LOWER(TRIM(colecao)) = LOWER(TRIM(?))
            ORDER BY titulo COLLATE NOCASE
            """,
            (filtro, filtro),
        ).fetchall()


def importar_kindlogger():
    if not CAMINHO_JSON.exists():
        print("Arquivo kindlogger-export.json não encontrado; importação ignorada.")
        return

    with CAMINHO_JSON.open("r", encoding="utf-8") as arquivo:
        dados = json.load(arquivo)

    importados = 0
    with conectar() as conexao:
        for livro in dados.get("books", []):
            titulo = (livro.get("title") or "").strip()
            if not titulo:
                continue

            autor = livro.get("author") or "Autor desconhecido"
            asin = (livro.get("asin") or "").strip() or None
            paginas = livro.get("pages")
            if not isinstance(paginas, int) or paginas < 0:
                paginas = None

            # Ausência de read não é interpretada como "não lido".
            read_value = livro.get("read")
            if read_value is True:
                status_livro, colecao = "Lido", "Lidos"
            elif read_value is False:
                status_livro, colecao = "Pendente", "Quero ler"
            else:
                status_livro, colecao = "Pendente", "Importados — revisar status"

            cursor = conexao.execute(
                """
                INSERT OR IGNORE INTO livros
                (titulo, autor, paginas, colecao, status, asin)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (titulo, autor, paginas, colecao, status_livro, asin),
            )
            if cursor.rowcount > 0:
                importados += 1

    print(f"Importação concluída: {importados} livro(s) adicionado(s).")


if __name__ == "__main__":
    criar_tabela()
    importar_kindlogger()
