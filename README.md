# Bookkeeper 📚

Seu companheiro de leitura. Cada livro, uma nova jornada. 💙

O Bookkeeper organiza a biblioteca, acompanha o progresso de leitura e importa livros do Kindle **sem pedir senha da Amazon**.

## Estrutura

```
Bookkeeper/
├── bookkeeper/             # Bot Telegram + banco + API de importação
│   ├── bot.py
│   ├── database.py
│   └── api.py
├── exporter/
│   └── kindle-web/         # Extensão Chrome (Manifest V3)
│       ├── main.js         # Intercepta Amazon + paginação (MAIN world)
│       ├── content.js      # Orquestra importação (isolated world)
│       ├── popup.html / popup.js
│       └── manifest.json
├── docs/                   # Documentação de comportamento
├── tools/                  # Utilitários auxiliares
├── run_bot.py
├── requirements.txt
└── roadmap.md
```

## Configuração do bot

1. Instale as dependências:

```bash
pip install -r requirements.txt
```

2. Crie um arquivo `.env` na raiz (nunca envie ao GitHub):

```env
TELEGRAM_BOT_TOKEN=seu_token_aqui
BOOKKEEPER_API_HOST=127.0.0.1
BOOKKEEPER_API_PORT=8787
```

3. Inicie:

```bash
python run_bot.py
```

O SQLite (`biblioteca.db`) é criado localmente. A API HTTP sobe em `http://127.0.0.1:8787` para receber a biblioteca da extensão.

> **Limitação desta primeira versão:** a API escuta apenas em `127.0.0.1`. Portanto, o bot e o navegador com a extensão precisam estar no mesmo computador. Para atender usuários em computadores diferentes, será necessário hospedar a API em um servidor HTTPS público e configurar a extensão para usar esse endereço. Não exponha a API local diretamente à internet.

## Extensão Kindle

1. Abra `chrome://extensions` e ative o modo do desenvolvedor.
2. Clique em **Carregar sem compactação** e selecione `exporter/kindle-web/`.
3. No Telegram, use `/conectar` e copie o código.
4. Abra a página **Conteúdo e dispositivos** da Amazon (já autenticado).
5. No popup da extensão, cole o código e clique em **Buscar e enviar livros**.

A extensão usa a sessão já autenticada no navegador, captura o modelo legítimo de requisição da Amazon, preserva o CSRF dinâmico, pagina a biblioteca em lotes e envia os livros ao backend com o código de uso único. Também permite exportar um JSON local.

**Nunca** digite a senha da Amazon no bot ou na extensão.

## Comandos do bot

| Comando | Função |
|---------|--------|
| `/start` | Apresentação |
| `/help` | Ajuda |
| `/conectar` | Gera código temporário para a extensão |
| `/biblioteca` | Lista seus livros (paginado) |
| `/adicionar` | Cadastro manual |
| `/status` | Atualiza status de um livro |
| `/estatisticas` | Contagens por status |
| `/filtrar` | Filtra por status ou coleção |

Cada usuário Telegram vê apenas a própria biblioteca.

## Segurança

- Código de vínculo único, de uso único e válido por 30 minutos.
- Backend não armazena cookies, senhas ou tokens da Amazon.
- Bibliotecas isoladas por `telegram_user_id`.
- Arquivos locais (`.env`, bancos e exports JSON) ficam fora do Git.

## Observações

- O exportador Kindle foi mantido com sua interceptação e paginação.
- A sincronização automática de novas compras ainda não está implementada.
- Se a API local não estiver acessível pela extensão, use **Exportar JSON local**.
