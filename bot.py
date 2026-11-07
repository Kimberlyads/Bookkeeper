import os 
from dotenv import load_dotenv
from telegram import Update 
from telegram.ext import Application, CommandHandler, ContextTypes 
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackQueryHandler
from database import (
    criar_tabela, 
    adicionar_livro, 
    listar_livros, 
    atualizar_status,
    contar_livros,
    filtrar_livros)

load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

async def start(update: Update, context: 
                ContextTypes.DEFAULT_TYPES):
    await update.message.reply_text(
        "Oii! Eu sou o Bookkeeper, seu assistente de biblioteca!\n"
        "Ainda estou aprendendo, mas logo vou ajudar você a organizar seus livros."
    )

async def help_command(update: Update, context: 
                ContextTypes.DEFAULT_TYPES):
    await update.message.reply_text(
        "📚 O que eu vou poder fazer: \n\n"
        "Consultar sua bibloteca Kindle\n"
        "Contar seus livros\n"
        "Encontrar livros curtinhos\n"
        "Filtrar por coleção\n"
        "Encontrar ofertas gratuitas\n\n"
        "Ainda estou em desenvolvimento"
    )

async def adicionar(update: Update, context: 
                ContextTypes.DEFAULT_TYPES):
    texto = " ".join(context.args)
    partes = [parte.strip() for parte in texto.split(";")]

    if len(partes) not in (4,5):
        await update.message.reply_text(
            "Use assim:\n"
            "/adicionar Titulo; Autor; Páginas; Coleção; Status\n\n"
            "Exemplo:\n"
            "/adicionar A Rainha Vermelha; Victoria Averyard; 424; Lidos\n\n"
            "Status disponiveis: Pendente, Lendo, Lido.\n"
            "Se não informar o status ele será definido automaticamente."
        )
        return
    
    titulo, autor, paginas, colecao=partes[:4]

    try:
        paginas = int(paginas)
    except ValueError:
        await update.message.reply_text(
            "O número de páginas deve ser um número inteiro."
        )
        return

    if len(partes) == 5:
        status = partes[4].capitalize()
    elif colecao.lower() == "lidos":
        status = "Lido"
    else:
        status = "Pendente"

    if status not in ("Pendente", "Lendo", "Lido"):
        await update.message.reply_text(
            "Status inválido! Use Pendente, Lendo ou Lido"
        )
        return

    adicionar_livro(titulo, autor, paginas, colecao, status)

    await update.message.reply_text(
        f"Livro cadastrado!\n"
        f"{titulo}\n"
        f"Status: {status}\n"
    )

async def biblioteca(update: Update, context: ContextTypes.DEFAULT_TYPE):
    livros = listar_livros()

    if not livros:
        await update.message.reply_text(
            "Sua biblioteca ainda está vazia!"
        )
        return

    await mostrar_pagina_biblioteca(
        update.message,
        livros,
        0
    )

async def mostrar_pagina_biblioteca(mensagem, livros, pagina):
    livros_por_pagina = 20

    total_livros = len(livros)
    total_paginas = (total_livros + livros_por_pagina - 1) // livros_por_pagina

    inicio = pagina * livros_por_pagina
    fim = inicio + livros_por_pagina

    livros_pagina = livros[inicio:fim]

    texto = (
        f"📚 Sua biblioteca\n"
        f"Página {pagina + 1} de {total_paginas}\n\n"
    )

    for titulo, autor, paginas, colecao, status in livros_pagina:
        texto += (
            f"📖 {titulo}\n"
            f"✍️ Autor: {autor or 'Desconhecido'}\n"
            f"📄 Páginas: {paginas or 'Não informado'}\n"
            f"🗂 Coleção: {colecao or 'Não informada'}\n"
            f"📌 Status: {status or 'Não informado'}\n\n"
        )

    botoes = []

    if pagina > 0:
        botoes.append(
            InlineKeyboardButton(
                "⬅️ Anterior",
                callback_data=f"biblioteca:{pagina - 1}"
            )
        )

    if pagina < total_paginas - 1:
        botoes.append(
            InlineKeyboardButton(
                "Próxima ➡️",
                callback_data=f"biblioteca:{pagina + 1}"
            )
        )

    teclado = InlineKeyboardMarkup([botoes]) if botoes else None

    await mensagem.reply_text(
        texto,
        reply_markup=teclado
    )

async def paginar_biblioteca(update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    await query.answer()

    pagina = int(query.data.split(":")[1])
    livros = listar_livros()

    livros_por_pagina = 20
    total_paginas = (len(livros) + livros_por_pagina - 1) // livros_por_pagina

    if pagina < 0 or pagina >= total_paginas:
        return

    inicio = pagina * livros_por_pagina
    fim = inicio + livros_por_pagina

    livros_pagina = livros[inicio:fim]

    texto = (
        f"📚 Sua biblioteca\n"
        f"Página {pagina + 1} de {total_paginas}\n\n"
    )

    for titulo, autor, paginas, colecao, status in livros_pagina:
        texto += (
            f"📖 {titulo}\n"
            f"✍️ Autor: {autor or 'Desconhecido'}\n"
            f"📄 Páginas: {paginas or 'Não informado'}\n"
            f"🗂 Coleção: {colecao or 'Não informada'}\n"
            f"📌 Status: {status or 'Não informado'}\n\n"
        )

    botoes = []

    if pagina > 0:
        botoes.append(
            InlineKeyboardButton(
                "⬅️ Anterior",
                callback_data=f"biblioteca:{pagina - 1}"
            )
        )

    if pagina < total_paginas - 1:
        botoes.append(
            InlineKeyboardButton(
                "Próxima ➡️",
                callback_data=f"biblioteca:{pagina + 1}"
            )
        )

    teclado = InlineKeyboardMarkup([botoes]) if botoes else None

    await query.edit_message_text(
        texto,
        reply_markup=teclado
    )


async def status(update: Update, context: ContextTypes.DEFAULT_TYPES):
    texto = " ".join(context.args)
    partes = [parte.strip() for parte in texto.split(";")]

    if len(partes)!= 2:
        await update.message.reply_text(
            "Use assim:\n"
            "/status Título do livro; Status\n\n"
            "Status disponiveis: Pendente, Lendo ou Lixo.\n" 
            "Exemplo: /status O prinipe Cruel; Lendo"
        )
        return
   
    titulo, novo_status = partes
    novo_status = novo_status.capitalize()

    if novo_status not in ("Pendente", "Lendo", "Lido"):
        await update.message.reply_text(
            "Status inválido! Use Pendente, Lendo ou Lido"
        )
        return

    resultado = atualizar_status(titulo, novo_status)

    if resultado == 0:
        await update.message.reply_text(
            f"Não encontrei o livro '{titulo}' na sua biblioteca. "
        )
        return

    await update.message.reply_text(
        f"Status atualizado\n"
        f"{titulo}\n"
        f"Novo Status: {novo_status}\n"
    )


async def estatisticas(update: Update, context: ContextTypes.DEFAULT_TYPES):
    contagens = contar_livros()

    quantidades = {
        "Pendente": 0,
        "Lendo": 0,
        "Lido": 0
    }

    for status, quantidade in contagens:
        if status in quantidades:
            quantidades[status] = quantidade

    total = sum(quantidades.values())

    mensagem = (
        "📚 **Estatísticas da sua biblioteca**\n\n"
        f"📖 Total de livros: {sum(quantidades.values())}\n"
        f"⏳ Pendentes: {quantidades['Pendente']}\n"
        f"📕 Lendo: {quantidades['Lendo']}\n"
        f"✅ Lidos: {quantidades['Lido']}"
    )


    await update.message.reply_text(
        mensagem, 
        parse_mode="Markdown"
    )


async def filtrar(update: Update, context: ContextTypes.DEFAULT_TYPES):
    filtro = update.message.text.partition(" ")[2].strip()

    if not filtro:
        await update.message.reply_text(
            "Use assim:\n" 
            "/filtrar Lido\n" 
            "/filtrar Lendo\n" 
            "/filtrar Pendente\n" 
            "/filtrar Quero ler"
        )
        return

    livros = filtrar_livros(filtro)

    if not livros:
        await update.message.reply_text(
            f"Não encontrei livros com o filtro {filtro}."
        )
        return

    mensagem = f"📚 **Livros encontrados: {filtro}**\n\n"

    for titulo, autor, paginas, colecao, status in livros:
        mensage += (
             f"📖 {titulo}\n"
            f"✍️ Autor: {autor}\n"
            f"📄 Páginas: {paginas}\n"
            f"🗂 Coleção: {colecao}\n"
            f"📌 Status: {status}\n\n"
        )

    await update.message.reply_text(
        mensagem, 
        parse_mode="Markdown"
    )


def main():
    criar_tabela()
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("adicionar", adicionar))
    app.add_handler(CommandHandler("biblioteca", biblioteca))
    app.add_handler(CallbackQueryHandler(paginar_biblioteca, pattern="^biblioteca:"))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("estatisticas", estatisticas))
    app.add_handler(CommandHandler("filtrar", filtrar))

    print("Bookkepper está funcionando!")
    app.run_polling()

if __name__ == "__main__":
    main()