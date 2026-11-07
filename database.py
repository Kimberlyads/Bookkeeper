import sqlite3
import json
from pathlib import Path

CAMINHO_BANCO = Path(__file__).parent / "biblioteca.db"
CAMINHO_JSON = Path(__file__).parent / "kindlogger-export.json"


def conectar():
    return sqlite3.connect(CAMINHO_BANCO)


def criar_tabela():
    with conectar() as conexao:
        conexao.execute("""
            CREATE TABLE IF NOT EXISTS livros (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                titulo TEXT NOT NULL,
                autor TEXT,
                paginas INTEGER,
                colecao TEXT,
                status TEXT,
                asin TEXT
            )
        """)

        # Adiciona a coluna ASIN se o banco já existia
        colunas = conexao.execute(
            "PRAGMA table_info(livros)"
        ).fetchall()

        nomes_colunas = [coluna[1] for coluna in colunas]

        if "asin" not in nomes_colunas:
            conexao.execute("ALTER TABLE livros ADD COLUMN asin TEXT")

        # Evita importar o mesmo livro mais de uma vez
        conexao.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS
            indice_asin_livros
            ON livros(asin)
        """)


def adicionar_livro(
    titulo, autor, paginas, colecao, status="Pendente"
):
    with conectar() as conexao:
        conexao.execute(
            """
            INSERT INTO livros
            (titulo, autor, paginas, colecao, status)
            VALUES (?, ?, ?, ?, ?)
            """,
            (titulo, autor, paginas, colecao, status)
        )


def atualizar_status(titulo, status):
    if status == "Lido":
        colecao = "Lidos"
    else:
        colecao = "Quero ler"

    with conectar() as conexao:
        cursor = conexao.execute(
            """
            UPDATE livros
            SET status = ?, colecao = ?
            WHERE TRIM(LOWER(titulo)) = TRIM(LOWER(?))
            """,
            (status, colecao, titulo)
        )

        return cursor.rowcount


def listar_livros():
    with conectar() as conexao:
        cursor = conexao.execute("""
            SELECT titulo, autor, paginas, colecao, status
            FROM livros
            ORDER BY titulo
        """)

        return cursor.fetchall()


def contar_livros():
    with conectar() as conexao:
        cursor = conexao.execute("""
            SELECT
                CASE
                    WHEN LOWER(TRIM(status)) = 'quero ler'
                    THEN 'Pendente'
                    ELSE status
                END,
                COUNT(*)
            FROM livros
            GROUP BY
                CASE
                    WHEN LOWER(TRIM(status)) = 'quero ler'
                    THEN 'Pendente'
                    ELSE status
                END
        """)

        return cursor.fetchall()


def filtrar_livros(filtro):
    with conectar() as conexao:
        cursor = conexao.execute(
            """
            SELECT titulo, autor, paginas, colecao, status
            FROM livros
            WHERE LOWER(TRIM(status)) = LOWER(TRIM(?))
               OR LOWER(TRIM(colecao)) = LOWER(TRIM(?))
            ORDER BY titulo
            """,
            (filtro, filtro)
        )

        return cursor.fetchall()


def importar_kindlogger():
    if not CAMINHO_JSON.exists():
        print("Não encontrei o arquivo kindlogger-export.json.")
        return

    with open(CAMINHO_JSON, "r", encoding="utf-8") as arquivo:
        dados = json.load(arquivo)

    livros = dados.get("books", [])
    importados = 0

    with conectar() as conexao:
        for livro in livros:
            titulo = livro.get("title")

            if not titulo:
                continue

            autor = livro.get("author", "Autor desconhecido")
            asin = livro.get("asin")
            foi_lido = livro.get("read", False)

            if foi_lido:
                status = "Lido"
                colecao = "Lidos"
            else:
                status = "Pendente"
                colecao = "Quero ler"

            cursor = conexao.execute(
                """
                INSERT OR IGNORE INTO livros
                (titulo, autor, paginas, colecao, status, asin)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (titulo, autor, None, colecao, status, asin)
            )

            if cursor.rowcount > 0:
                importados += 1

    print(f"Importação concluída! {importados} livros adicionados.")


if __name__ == "__main__":
    criar_tabela()
    importar_kindlogger()