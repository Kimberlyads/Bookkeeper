import os

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

from .database import (
    adicionar_livro,
    contar_livros,
    criar_tabela,
    filtrar_livros,
    listar_livros,
    atualizar_status,
)

load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
LIVROS_POR_PAGINA = 20
STATUS_VALIDOS = {"Pendente", "Lendo", "Lido"}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(
        "Oii! Eu sou o Bookkeeper, seu companheiro de leitura. 💙\n"
        "Ainda estou aprendendo, mas logo vou ajudar você a organizar seus livros."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(
        "📚 Comandos disponíveis:\n\n"
        "/biblioteca — consultar seus livros\n"
        "/adicionar Título; Autor; Páginas; Coleção; Status — cadastrar livro\n"
        "/status Título; Status — atualizar o status\n"
        "/estatisticas — ver suas estatísticas\n"
        "/filtrar Status ou Coleção — filtrar a biblioteca\n\n"
        "Status: Pendente, Lendo ou Lido."
    )


async def adicionar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = " ".join(context.args)
    partes = [parte.strip() for parte in texto.split(";")]

    if len(partes) not in (4, 5) or any(not parte for parte in partes[:4]):
        await update.effective_message.reply_text(
            "Use assim:\n"
            "/adicionar Título; Autor; Páginas; Coleção; Status\n\n"
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
    elif colecao.casefold() == "lidos":
        status_livro = "Lido"
    else:
        status_livro = "Pendente"

    if status_livro not in STATUS_VALIDOS:
        await update.effective_message.reply_text(
            "Status inválido. Use Pendente, Lendo ou Lido."
        )
        return

    try:
        adicionar_livro(titulo, autor, paginas, colecao, status_livro)
    except Exception:
        await update.effective_message.reply_text(
            "Não consegui cadastrar esse livro. Talvez ele já esteja registrado."
        )
        return

    await update.effective_message.reply_text(
        f"Livro cadastrado! 📚\n{titulo}\nStatus: {status_livro}"
    )


async def biblioteca(update: Update, context: ContextTypes.DEFAULT_TYPE):
    livros = listar_livros()
    if not livros:
        await update.effective_message.reply_text("Sua biblioteca ainda está vazia!")
        return
    await enviar_pagina(update.effective_message, livros, 0)


def montar_pagina(livros, pagina):
    inicio = pagina * LIVROS_POR_PAGINA
    livros_pagina = livros[inicio : inicio + LIVROS_POR_PAGINA]
    total_paginas = max(
        1, (len(livros) + LIVROS_POR_PAGINA - 1) // LIVROS_POR_PAGINA
    )

    linhas = [f"📚 Sua biblioteca — página {pagina + 1} de {total_paginas}\n"]
    for titulo, autor, paginas, colecao, status_livro in livros_pagina:
        linhas.append(
            f"📖 {titulo}\n"
            f"✍️ Autor: {autor or 'Desconhecido'}\n"
            f"📄 Páginas: {paginas if paginas is not None else 'Não informado'}\n"
            f"🗂 Coleção: {colecao or 'Não informada'}\n"
            f"📌 Status: {status_livro or 'Não informado'}\n"
        )

    botoes = []
    if pagina > 0:
        botoes.append(
            InlineKeyboardButton("⬅️ Anterior", callback_data=f"biblioteca:{pagina - 1}")
        )
    if pagina < total_paginas - 1:
        botoes.append(
            InlineKeyboardButton("Próxima ➡️", callback_data=f"biblioteca:{pagina + 1}")
        )
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

    livros = listar_livros()
    total_paginas = max(
        1, (len(livros) + LIVROS_POR_PAGINA - 1) // LIVROS_POR_PAGINA
    )
    if pagina < 0 or pagina >= total_paginas:
        return

    texto, teclado, _ = montar_pagina(livros, pagina)
    await query.edit_message_text(texto, reply_markup=teclado)


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        await update.effective_message.reply_text(
            "Status inválido. Use Pendente, Lendo ou Lido."
        )
        return

    resultado = atualizar_status(titulo, novo_status)
    if resultado == 0:
        await update.effective_message.reply_text(
            f"Não encontrei o livro '{titulo}' na sua biblioteca."
        )
        return

    await update.effective_message.reply_text(
        f"Status atualizado 📚\n{titulo}\nNovo status: {novo_status}"
    )


async def estatisticas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    contagens = contar_livros()
    quantidades = {"Pendente": 0, "Lendo": 0, "Lido": 0}
    for status_livro, quantidade in contagens:
        if status_livro in quantidades:
            quantidades[status_livro] = quantidade

    total = sum(quantidades.values())
    await update.effective_message.reply_text(
        "📚 Estatísticas da sua biblioteca\n\n"
        f"📖 Total de livros: {total}\n"
        f"⏳ Pendentes: {quantidades['Pendente']}\n"
        f"📕 Lendo: {quantidades['Lendo']}\n"
        f"✅ Lidos: {quantidades['Lido']}"
    )


async def filtrar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    filtro = " ".join(context.args).strip()
    if not filtro:
        await update.effective_message.reply_text(
            "Informe um status ou coleção. Exemplos: /filtrar Lido ou /filtrar Fantasia"
        )
        return

    livros = filtrar_livros(filtro)
    if not livros:
        await update.effective_message.reply_text(
            f"Não encontrei livros com o filtro '{filtro}'."
        )
        return

    linhas = [f"📚 Livros encontrados: {filtro}\n"]
    for titulo, autor, paginas, colecao, status_livro in livros:
        linhas.append(
            f"📖 {titulo}\n"
            f"✍️ Autor: {autor or 'Desconhecido'}\n"
            f"📄 Páginas: {paginas if paginas is not None else 'Não informado'}\n"
            f"🗂 Coleção: {colecao or 'Não informada'}\n"
            f"📌 Status: {status_livro or 'Não informado'}\n"
        )

    await update.effective_message.reply_text("\n".join(linhas))


def main():
    if not TOKEN:
        raise RuntimeError(
            "A variável TELEGRAM_BOT_TOKEN não foi definida. Configure-a no arquivo .env."
        )

    criar_tabela()
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("adicionar", adicionar))
    app.add_handler(CommandHandler("biblioteca", biblioteca))
    app.add_handler(
        CallbackQueryHandler(paginar_biblioteca, pattern=r"^biblioteca:")
    )
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("estatisticas", estatisticas))
    app.add_handler(CommandHandler("filtrar", filtrar))

    print("Bookkeeper está funcionando!")
    app.run_polling()


if __name__ == "__main__":
    main()
