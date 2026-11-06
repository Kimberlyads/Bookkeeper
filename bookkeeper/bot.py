import asyncio
import logging
import os

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

from .api import iniciar_api_em_thread
from .database import (
    adicionar_livro, atualizar_status, contar_livros, criar_link_code,
    criar_tabela, filtrar_livros, garantir_usuario, listar_livros,
)

load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
LIVROS_POR_PAGINA = 20
STATUS_VALIDOS = {"Pendente", "Lendo", "Lido"}
AMAZON_LIBRARY_URL = os.getenv(
    "AMAZON_LIBRARY_URL",
    "https://www.amazon.com.br/hz/mycd/digital-console/contentlist/booksAll/dateDsc/",
)
logger = logging.getLogger(__name__)
_application: Application | None = None


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
        "/adicionar Título; Autor; Páginas; Coleção; Status — cadastrar livro\n"
        "/status Título; Status — atualizar o status\n"
        "/estatisticas — ver suas estatísticas\n"
        "/filtrar Status ou Coleção — filtrar a biblioteca\n\n"
        "Status: Pendente, Lendo ou Lido.\n\n"
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
        await update.effective_message.reply_text("Status inválido. Use Pendente, Lendo ou Lido.")
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
    livros = listar_livros(_user_id(update))
    if not livros:
        await update.effective_message.reply_text(
            "Sua biblioteca ainda está vazia!\n"
            "Use /conectar para importar do Kindle ou /adicionar para cadastrar."
        )
        return
    await enviar_pagina(update.effective_message, livros, 0)


def montar_pagina(livros, pagina):
    inicio = pagina * LIVROS_POR_PAGINA
    livros_pagina = livros[inicio:inicio + LIVROS_POR_PAGINA]
    total_paginas = max(1, (len(livros) + LIVROS_POR_PAGINA - 1) // LIVROS_POR_PAGINA)
    linhas = [f"📚 Sua biblioteca — página {pagina + 1} de {total_paginas}\n"]
    for titulo, autor, paginas, colecao, status_livro in livros_pagina:
        linhas.append(
            f"📖 {titulo}\n✍️ Autor: {autor or 'Desconhecido'}\n"
            f"📄 Páginas: {paginas if paginas is not None else 'Não informado'}\n"
            f"🗂 Coleção: {colecao or 'Não informada'}\n"
            f"📌 Status: {status_livro or 'Não informado'}\n"
        )
    botoes = []
    if pagina > 0:
        botoes.append(InlineKeyboardButton("⬅️ Anterior", callback_data=f"biblioteca:{pagina - 1}"))
    if pagina < total_paginas - 1:
        botoes.append(InlineKeyboardButton("Próxima ➡️", callback_data=f"biblioteca:{pagina + 1}"))
    teclado = InlineKeyboardMarkup([botoes]) if botoes else None
    return "\n".join(linhas), teclado, total_paginas


async def enviar_pagina(mensagem, livros, pagina):
    texto, teclado, _ = montar_pagina(livros, pagina)
    await mensagem.reply_text(texto, reply_markup=teclado)


async def paginar_biblioteca(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        pagina = int(query.data.split(":", 1)[1])
    except (ValueError, IndexError):
        return
    livros = listar_livros(query.from_user.id)
    total_paginas = max(1, (len(livros) + LIVROS_POR_PAGINA - 1) // LIVROS_POR_PAGINA)
    if pagina < 0 or pagina >= total_paginas:
        return
    texto, teclado, _ = montar_pagina(livros, pagina)
    await query.edit_message_text(texto, reply_markup=teclado)


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = _user_id(update)
    partes = [parte.strip() for parte in " ".join(context.args).split(";")]
    if len(partes) != 2 or not all(partes):
        await update.effective_message.reply_text(
            "Use assim: /status Título do livro; Status\n"
            "Status disponíveis: Pendente, Lendo ou Lido."
        )
        return
    titulo, novo_status = partes
    novo_status = novo_status.capitalize()
    if novo_status not in STATUS_VALIDOS:
        await update.effective_message.reply_text("Status inválido. Use Pendente, Lendo ou Lido.")
        return
    if atualizar_status(user_id, titulo, novo_status) == 0:
        await update.effective_message.reply_text(f"Não encontrei o livro '{titulo}' na sua biblioteca.")
        return
    await update.effective_message.reply_text(
        f"Status atualizado 📚\n{titulo}\nNovo status: {novo_status}"
    )


async def estatisticas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    contagens = contar_livros(_user_id(update))
    quantidades = {"Pendente": 0, "Lendo": 0, "Lido": 0}
    for status_livro, quantidade in contagens:
        if status_livro in quantidades:
            quantidades[status_livro] = quantidade
    total = sum(quantidades.values())
    await update.effective_message.reply_text(
        "📚 Estatísticas da sua biblioteca\n\n"
        f"📖 Total de livros: {total}\n⏳ Pendentes: {quantidades['Pendente']}\n"
        f"📕 Lendo: {quantidades['Lendo']}\n✅ Lidos: {quantidades['Lido']}"
    )


async def filtrar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    filtro = " ".join(context.args).strip()
    if not filtro:
        await update.effective_message.reply_text(
            "Informe um status ou coleção. Exemplos: /filtrar Lido ou /filtrar Fantasia"
        )
        return
    livros = filtrar_livros(_user_id(update), filtro)
    if not livros:
        await update.effective_message.reply_text(f"Não encontrei livros com o filtro '{filtro}'.")
        return
    linhas = [f"📚 Livros encontrados: {filtro}\n"]
    for titulo, autor, paginas, colecao, status_livro in livros:
        linhas.append(
            f"📖 {titulo}\n✍️ Autor: {autor or 'Desconhecido'}\n"
            f"📄 Páginas: {paginas if paginas is not None else 'Não informado'}\n"
            f"🗂 Coleção: {colecao or 'Não informada'}\n"
            f"📌 Status: {status_livro or 'Não informado'}\n"
        )
    await update.effective_message.reply_text("\n".join(linhas))


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
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.run_coroutine_threadsafe(_send(), loop)
        else:
            loop.run_until_complete(_send())
    except Exception:
        logger.exception("Não foi possível agendar notificação de importação")


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
    app = Application.builder().token(TOKEN).build()
    _application = app
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("conectar", conectar))
    app.add_handler(CommandHandler("adicionar", adicionar))
    app.add_handler(CommandHandler("biblioteca", biblioteca))
    app.add_handler(CallbackQueryHandler(paginar_biblioteca, pattern=r"^biblioteca:"))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("estatisticas", estatisticas))
    app.add_handler(CommandHandler("filtrar", filtrar))
    iniciar_api_em_thread(on_import_complete=_on_import_complete)
    print("Bookkeeper está funcionando!")
    app.run_polling()


if __name__ == "__main__":
    main()
