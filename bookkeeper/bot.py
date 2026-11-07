import asyncio
import logging
import os

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

from .api import iniciar_api_em_thread
from .database import (
    adicionar_livro,
    atualizar_status,
    buscar_livros,
    contar_livros,
    criar_link_code,
    criar_tabela,
    filtrar_livros,
    garantir_usuario,
    listar_livros,
    listar_livros_com_id,
    obter_livro,
)

load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
LIVROS_POR_PAGINA = 20
STATUS_VALIDOS = {"Pendente", "Lendo", "Lido", "Desconhecido"}
AMAZON_LIBRARY_URL = os.getenv(
    "AMAZON_LIBRARY_URL",
    "https://www.amazon.com.br/hz/mycd/digital-console/contentlist/booksAll/dateDsc/",
)
logger = logging.getLogger(__name__)
_application: Application | None = None
_bot_loop: asyncio.AbstractEventLoop | None = None


def _user_id(update: Update) -> int:
    return update.effective_user.id


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    garantir_usuario(user.id, user.username, user.first_name)
    await update.effective_message.reply_text(
        "Oii! Eu sou o Bookkeeper, seu companheiro de leitura. 💙\n\n"
        "Use /conectar para vincular sua biblioteca Kindle.\n"
        "Use /help para ver os comandos."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(
        "📚 Comandos disponíveis:\n\n"
        "/conectar — gerar código para importar a biblioteca Kindle\n"
        "/biblioteca — consultar seus livros\n"
        "/buscar trecho — pesquisar por título ou autor\n"
        "/livro id ou título — ver detalhes de um livro\n"
        "/adicionar Título; Autor; Páginas; Coleção; Status — cadastrar livro\n"
        "/status Título; Status — atualizar o status\n"
        "/estatisticas — ver suas estatísticas\n"
        "/filtrar Status — filtrar por status\n"
        "/filtrar Coleção — filtrar por coleção\n"
        "/filtrar Status; Coleção — combinar os dois\n\n"
        "Status: Pendente, Lendo, Lido ou Desconhecido.\n\n"
        "A senha da Amazon nunca é pedida. O login fica só no site oficial."
    )

async def conectar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    garantir_usuario(user.id, user.username, user.first_name)
    code, _expira = criar_link_code(user.id)
    teclado = InlineKeyboardMarkup([[
        InlineKeyboardButton("Abrir biblioteca Kindle", url=AMAZON_LIBRARY_URL)
    ]])
    await update.effective_message.reply_text(
        "🔗 Vínculo seguro com o Kindle\n\n"
        f"Seu código: `{code}`\n"
        "Validade: 30 minutos (uso único)\n\n"
        "1. Abra a página oficial da Amazon e faça login se precisar.\n"
        "2. Com a extensão Bookkeeper instalada, cole o código no popup.\n"
        "3. Clique em buscar/importar. A extensão usa a sessão já autenticada.\n"
        "4. Eu confirmo aqui no Telegram quando a biblioteca chegar.\n\n"
        "Não compartilhe este código. Ele não contém senha nem cookies.",
        reply_markup=teclado,
        parse_mode="Markdown",
    )


async def adicionar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    garantir_usuario(user_id, user.username, user.first_name)
    partes = [parte.strip() for parte in " ".join(context.args).split(";")]
    if len(partes) not in (4, 5) or any(not parte for parte in partes[:4]):
        await update.effective_message.reply_text(
            "Use assim:\n/adicionar Título; Autor; Páginas; Coleção; Status\n\n"
            "O status é opcional. Exemplo:\n"
            "/adicionar A Rainha Vermelha; Victoria Aveyard; 424; Quero ler; Pendente"
        )
        return
    titulo, autor, paginas_texto, colecao = partes[:4]
    try:
        paginas = int(paginas_texto)
        if paginas < 0:
            raise ValueError
    except ValueError:
        await update.effective_message.reply_text(
            "O número de páginas precisa ser um inteiro igual ou maior que zero."
        )
        return
    if len(partes) == 5:
        status_livro = partes[4].strip().capitalize()
    else:
        status_livro = "Lido" if colecao.casefold() == "lidos" else "Pendente"
    if status_livro not in STATUS_VALIDOS:
        await update.effective_message.reply_text("Status inválido. Use Pendente, Lendo, Lido ou Desconhecido.")
        return
    try:
        adicionar_livro(user_id, titulo, autor, paginas, colecao, status_livro)
    except Exception:
        await update.effective_message.reply_text(
            "Não consegui cadastrar esse livro. Talvez ele já esteja registrado."
        )
        return
    await update.effective_message.reply_text(
        f"Livro cadastrado! 📚\n{titulo}\nStatus: {status_livro}"
    )


async def biblioteca(update: Update, context: ContextTypes.DEFAULT_TYPE):
    livros = listar_livros_com_id(_user_id(update))
    if not livros:
        await update.effective_message.reply_text(
            "Sua biblioteca ainda está vazia!\n"
            "Use /conectar para importar do Kindle ou /adicionar para cadastrar."
        )
        return
    context.user_data["lista_atual"] = "biblioteca"
    await enviar_pagina(update.effective_message, livros, 0, titulo_lista="Sua biblioteca")

def _extrair_campos_lista(row):
    """Normaliza linha de listagem com ou sem id."""
    if hasattr(row, "keys"):
        keys = set(row.keys())
        return {
            "id": row["id"] if "id" in keys else None,
            "titulo": row["titulo"],
            "autor": row["autor"],
            "paginas": row["paginas"],
            "colecao": row["colecao"],
            "status": row["status"],
        }
    if len(row) >= 6:
        return {
            "id": row[0],
            "titulo": row[1],
            "autor": row[2],
            "paginas": row[3],
            "colecao": row[4],
            "status": row[5],
        }
    return {
        "id": None,
        "titulo": row[0],
        "autor": row[1],
        "paginas": row[2],
        "colecao": row[3],
        "status": row[4],
    }


def montar_pagina(livros, pagina, titulo_lista="Sua biblioteca", callback_prefix="biblioteca"):
    inicio = pagina * LIVROS_POR_PAGINA
    livros_pagina = livros[inicio:inicio + LIVROS_POR_PAGINA]
    total_paginas = max(1, (len(livros) + LIVROS_POR_PAGINA - 1) // LIVROS_POR_PAGINA)
    linhas = [f"📚 {titulo_lista} — página {pagina + 1} de {total_paginas}\n"]
    for row in livros_pagina:
        item = _extrair_campos_lista(row)
        id_txt = f"#{item['id']} · " if item["id"] is not None else ""
        linhas.append(
            f"📖 {id_txt}{item['titulo']}\n"
            f"✍️ Autor: {item['autor'] or 'Desconhecido'}\n"
            f"📄 Páginas: {item['paginas'] if item['paginas'] is not None else 'Não informado'}\n"
            f"🗂 Coleção: {item['colecao'] or 'Não informada'}\n"
            f"📌 Status: {item['status'] or 'Não informado'}\n"
        )
    botoes = []
    if pagina > 0:
        botoes.append(
            InlineKeyboardButton("⬅️ Anterior", callback_data=f"{callback_prefix}:{pagina - 1}")
        )
    if pagina + 1 < total_paginas:
        botoes.append(
            InlineKeyboardButton("Próxima ➡️", callback_data=f"{callback_prefix}:{pagina + 1}")
        )
    teclado = InlineKeyboardMarkup([botoes]) if botoes else None
    return "\n".join(linhas), teclado, total_paginas

async def enviar_pagina(mensagem, livros, pagina, titulo_lista="Sua biblioteca", callback_prefix="biblioteca"):
    texto, teclado, _ = montar_pagina(
        livros, pagina, titulo_lista=titulo_lista, callback_prefix=callback_prefix
    )
    await mensagem.reply_text(texto, reply_markup=teclado)

async def paginar_biblioteca(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        pagina = int(query.data.split(":")[1])
    except (IndexError, ValueError):
        return
    livros = listar_livros_com_id(query.from_user.id)
    total_paginas = max(1, (len(livros) + LIVROS_POR_PAGINA - 1) // LIVROS_POR_PAGINA)
    pagina = max(0, min(pagina, total_paginas - 1))
    texto, teclado, _ = montar_pagina(livros, pagina, titulo_lista="Sua biblioteca")
    await query.edit_message_text(texto, reply_markup=teclado)

async def paginar_busca_ou_filtro(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Paginação de /buscar e /filtrar usando context.user_data por usuário."""
    query = update.callback_query
    await query.answer()
    try:
        prefixo, pagina_s = query.data.split(":", 1)
        pagina = int(pagina_s)
    except (ValueError, IndexError):
        return
    user_data = context.user_data
    if prefixo == "busca":
        termo = user_data.get("busca_termo")
        if not termo:
            await query.edit_message_text("A busca expirou. Use /buscar de novo.")
            return
        livros = buscar_livros(query.from_user.id, termo)
        titulo = f'Busca: "{termo}"'
    elif prefixo == "filtro":
        status_filtro = user_data.get("filtro_status")
        colecao = user_data.get("filtro_colecao")
        filtro_unico = user_data.get("filtro_unico")
        if status_filtro or colecao:
            livros = filtrar_livros(query.from_user.id, status=status_filtro, colecao=colecao)
            partes = []
            if status_filtro:
                partes.append(f"status={status_filtro}")
            if colecao:
                partes.append(f"coleção={colecao}")
            titulo = "Filtro: " + ", ".join(partes)
        elif filtro_unico:
            livros = filtrar_livros(query.from_user.id, filtro_unico)
            titulo = f'Filtro: "{filtro_unico}"'
        else:
            await query.edit_message_text("O filtro expirou. Use /filtrar de novo.")
            return
    else:
        return
    if not livros:
        await query.edit_message_text("Nenhum livro nesta lista.")
        return
    total_paginas = max(1, (len(livros) + LIVROS_POR_PAGINA - 1) // LIVROS_POR_PAGINA)
    pagina = max(0, min(pagina, total_paginas - 1))
    texto, teclado, _ = montar_pagina(livros, pagina, titulo_lista=titulo, callback_prefix=prefixo)
    await query.edit_message_text(texto, reply_markup=teclado)


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = _user_id(update)
    partes = [parte.strip() for parte in " ".join(context.args).split(";")]
    if len(partes) != 2 or not all(partes):
        await update.effective_message.reply_text(
            "Use assim: /status Título do livro; Status\n"
            "Status disponíveis: Pendente, Lendo, Lido ou Desconhecido."
        )
        return
    titulo, novo_status = partes
    novo_status = novo_status.capitalize()
    if novo_status not in STATUS_VALIDOS:
        await update.effective_message.reply_text(
            "Status inválido. Use Pendente, Lendo, Lido ou Desconhecido."
        )
        return
    if atualizar_status(user_id, titulo, novo_status) == 0:
        await update.effective_message.reply_text(
            f"Não encontrei o livro '{titulo}' na sua biblioteca."
        )
        return
    await update.effective_message.reply_text(
        f"Status atualizado 📚\n{titulo}\nNovo status: {novo_status}"
    )


async def estatisticas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    contagens = contar_livros(_user_id(update))
    quantidades = {"Pendente": 0, "Lendo": 0, "Lido": 0, "Desconhecido": 0}
    for status_livro, quantidade in contagens:
        if status_livro in quantidades:
            quantidades[status_livro] = quantidade
    total = sum(quantidades.values())
    await update.effective_message.reply_text(
        "📚 Estatísticas da sua biblioteca\n\n"
        f"📖 Total de livros: {total}\n"
        f"⏳ Pendentes: {quantidades['Pendente']}\n"
        f"📕 Lendo: {quantidades['Lendo']}\n"
        f"✅ Lidos: {quantidades['Lido']}\n"
        f"❔ Desconhecidos: {quantidades['Desconhecido']}"
    )


def _parse_filtro_args(args: list[str]) -> tuple[str | None, str | None, str | None]:
    """Retorna (status, coleção, filtro_unico) para formatos antigos e combinados."""
    bruto = " ".join(args).strip()
    if not bruto:
        return None, None, None
    if ";" in bruto:
        partes = [p.strip() for p in bruto.split(";", 1)]
        status = partes[0] or None
        colecao = partes[1] if len(partes) > 1 and partes[1] else None
        return status, colecao, None
    return None, None, bruto


async def filtrar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status_filtro, colecao, filtro_unico = _parse_filtro_args(context.args)
    if not status_filtro and not colecao and not filtro_unico:
        await update.effective_message.reply_text(
            "Informe um status e/ou coleção.\n"
            "Exemplos:\n/filtrar Lido\n/filtrar Fantasia\n/filtrar Lendo; Clube do Livro"
        )
        return
    user_id = _user_id(update)
    if status_filtro or colecao:
        livros = filtrar_livros(user_id, status=status_filtro, colecao=colecao)
        partes = []
        if status_filtro:
            partes.append(f"status={status_filtro}")
        if colecao:
            partes.append(f"coleção={colecao}")
        rotulo = ", ".join(partes)
        context.user_data["filtro_status"] = status_filtro
        context.user_data["filtro_colecao"] = colecao
        context.user_data.pop("filtro_unico", None)
    else:
        livros = filtrar_livros(user_id, filtro_unico)
        rotulo = filtro_unico
        context.user_data["filtro_unico"] = filtro_unico
        context.user_data.pop("filtro_status", None)
        context.user_data.pop("filtro_colecao", None)
    if not livros:
        await update.effective_message.reply_text(f"Não encontrei livros com o filtro '{rotulo}'.")
        return
    await enviar_pagina(
        update.effective_message, livros, 0,
        titulo_lista=f"Filtro: {rotulo}", callback_prefix="filtro"
    )

async def buscar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    termo = " ".join(context.args).strip()
    if not termo:
        await update.effective_message.reply_text(
            "Use assim: /buscar trecho do título ou autor\nExemplo: /buscar Tolkien"
        )
        return
    livros = buscar_livros(_user_id(update), termo)
    if not livros:
        await update.effective_message.reply_text(f'Nenhum livro encontrado para "{termo}".')
        return
    context.user_data["busca_termo"] = termo
    await enviar_pagina(
        update.effective_message, livros, 0,
        titulo_lista=f'Busca: "{termo}"', callback_prefix="busca"
    )


def _url_capa_valida(url) -> bool:
    if not url or not isinstance(url, str):
        return False
    u = url.strip().lower()
    return u.startswith("https://") or u.startswith("http://")


def _formatar_detalhe_livro(row) -> tuple[str, str | None]:
    """Retorna texto completo e URL de capa, sem inventar dados ausentes."""
    def val(chave, rotulo_ausente="Não informado"):
        try:
            v = row[chave]
        except (KeyError, IndexError, TypeError):
            return rotulo_ausente
        if v is None or (isinstance(v, str) and not v.strip()):
            return rotulo_ausente
        return v
    linhas = [
        f"📖 {val('titulo')}",
        f"✍️ Autor: {val('autor', 'Desconhecido')}",
        f"📌 Status: {val('status')}",
        f"🗂 Coleção: {val('colecao', 'Não informada')}",
    ]
    if row["paginas"] is not None:
        linhas.append(f"📄 Páginas: {row['paginas']}")
    if row["asin"]:
        linhas.append(f"🔖 ASIN: {row['asin']}")
    if row["content_identifier"]:
        linhas.append(f"🆔 Identificador: {row['content_identifier']}")
    if row["acquired_date"]:
        linhas.append(f"📅 Adquirido em: {row['acquired_date']}")
    if row["origin_type"]:
        linhas.append(f"📦 Origem: {row['origin_type']}")
    if row["is_purchased"] is not None:
        linhas.append("🛒 Comprado: sim" if int(row["is_purchased"]) == 1 else "🛒 Comprado: não")
    linhas.append(f"🔢 ID interno: {row['id']}")
    capa = row["product_image"] if _url_capa_valida(row["product_image"]) else None
    return "\n".join(linhas), capa


async def livro(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.effective_message.reply_text(
            "Use assim:\n/livro 12\nou\n/livro Título completo do livro\n\n"
            "Dica: /buscar mostra o #ID de cada resultado."
        )
        return
    user_id = _user_id(update)
    args_txt = " ".join(context.args).strip()
    row = obter_livro(user_id, livro_id=int(args_txt)) if args_txt.isdigit() else None
    if row is None:
        row = obter_livro(user_id, titulo=args_txt)
    if row is None:
        await update.effective_message.reply_text(f'Não encontrei o livro "{args_txt}" na sua biblioteca.')
        return
    texto, capa = _formatar_detalhe_livro(row)
    if capa:
        try:
            await update.effective_message.reply_photo(photo=capa)
        except Exception:
            await update.effective_message.reply_text(texto + f"\n🖼 Capa: {capa}")
            return
        await update.effective_message.reply_text(texto)
        return
    await update.effective_message.reply_text(texto)


def _on_import_complete(telegram_user_id: int, resultado: dict):
    global _application
    if _application is None:
        return
    texto = (
        "✅ Importação Kindle concluída!\n\n"
        f"📚 Recebidos: {resultado.get('total_recebidos', 0)}\n"
        f"➕ Novos: {resultado.get('adicionados', 0)}\n"
        f"↩️ Já existentes/ignorados: {resultado.get('ignorados', 0)}\n\n"
        "Use /biblioteca ou /estatisticas para conferir."
    )
    async def _send():
        try:
            await _application.bot.send_message(chat_id=telegram_user_id, text=texto)
        except Exception:
            logger.exception("Falha ao notificar usuário %s", telegram_user_id)
    try:
        if _bot_loop is None or not _bot_loop.is_running():
            logger.error("Loop do Telegram indisponível para notificação de importação")
            return
        asyncio.run_coroutine_threadsafe(_send(), _bot_loop)
    except Exception:
        logger.exception("Não foi possível agendar notificação de importação")


async def _registrar_loop_do_bot(app: Application):
    global _bot_loop
    _bot_loop = asyncio.get_running_loop()


def main():
    global _application
    if not TOKEN:
        raise RuntimeError(
            "A variável TELEGRAM_BOT_TOKEN não foi definida. Configure-a no arquivo .env."
        )
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        level=logging.INFO,
    )
    criar_tabela()
    app = Application.builder().token(TOKEN).post_init(_registrar_loop_do_bot).build()
    _application = app
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("conectar", conectar))
    app.add_handler(CommandHandler("adicionar", adicionar))
    app.add_handler(CommandHandler("biblioteca", biblioteca))
    app.add_handler(CallbackQueryHandler(paginar_biblioteca, pattern=r"^biblioteca:"))
    app.add_handler(CallbackQueryHandler(paginar_busca_ou_filtro, pattern=r"^(busca|filtro):"))
    app.add_handler(CommandHandler("buscar", buscar))
    app.add_handler(CommandHandler("livro", livro))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("estatisticas", estatisticas))
    app.add_handler(CommandHandler("filtrar", filtrar))
    iniciar_api_em_thread(on_import_complete=_on_import_complete)
    print("Bookkeeper está funcionando!")
    app.run_polling()


if __name__ == "__main__":
    main()
