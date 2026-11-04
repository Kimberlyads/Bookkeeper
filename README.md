# Bookkeeper 📚

Seu companheiro de leitura. Cada livro, uma nova jornada. 💙

O Bookkeeper ajuda a organizar a biblioteca, acompanhar o progresso de leitura e, futuramente, registrar experiências e reflexões.

## Estrutura do projeto

```text
Bookkeeper/
├── bookkeeper/             # Código Python do bot e acesso ao banco
│   ├── __init__.py
│   ├── bot.py
│   └── database.py
├── exporter/
│   └── kindle-web/         # Extensão Chrome para importar a biblioteca Kindle
│       ├── manifest.json
│       ├── main.js
│       ├── content.js
│       ├── popup.html
│       └── popup.js
├── docs/                   # Documentação de comportamento e funcionalidades
├── tools/                  # Ferramentas auxiliares e notas
├── run_bot.py              # Ponto de entrada do bot
├── requirements.txt
└── roadmap.md
```

## Rodar o bot

1. Instale as dependências: `pip install -r requirements.txt`
2. Crie um arquivo `.env` na raiz com seu token:

   ```env
   TELEGRAM_BOT_TOKEN=seu_token_aqui
   ```

3. Inicie o bot: `python run_bot.py`

O banco SQLite é criado localmente na raiz do projeto. Arquivos locais, tokens e bibliotecas exportadas não devem ser enviados ao GitHub.

## Extensão Kindle

A extensão está em `exporter/kindle-web/`. Para carregar no Chrome, abra `chrome://extensions`, ative o modo do desenvolvedor e selecione **Carregar sem compactação**, apontando para essa pasta.

A importação está em desenvolvimento; a extensão ainda não envia automaticamente os livros para o bot.
