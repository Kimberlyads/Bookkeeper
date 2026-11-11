# Protótipo Kindle mobile — P0.2

## P0.1 → P0.2

| Área | P0.1 | P0.2 |
|------|------|------|
| Testes de rede | Helpers reimplementados | Exercitam `collector-core.js` real |
| Paginação | 75 dedupe estático | 0/1/25/26/50/75 + falha intermediária |
| Browser | Coletor monolítico | `normalize` + `core` + adapter |
| Erros | `err.message` bruto | `sanitizeErrorMessage` |
| Flag global | bloqueava reexecução | liberada após run / `__BOOKKEEPER_ALLOW_RERUN__` |
| `surfaceType` | Desktop | Mantido Desktop (sem evidência de quebra; ver abaixo) |

## Arquivos

- `book-normalize.js` — normalização e payload seguro
- `collector-core.js` — lógica testável (injeção de `fetch`)
- `collector.js` — adapter browser (UI, CSRF DOM, prompts)
- `test_collector_logic.mjs` / `test_network_security.mjs`

## surfaceType: Desktop

O valor `Desktop` replica o payload usado pela extensão e por exportadores comunitários. **Não há evidência** neste repositório de que Android exija outro valor. Alterar sem prova pode quebrar a coleta. O teste de campo deve confirmar; se a Amazon recusar no mobile, documentar o status HTTP/corpo e só então experimentar alternativa.

## Chrome Android

| Método | Situação |
|--------|----------|
| Remote debugging + colar 3 scripts | Recomendado para P0.2 |
| Bookmarklet | Frágil |
| Extensão | Indisponível |

Ordem no console: `book-normalize.js` → `collector-core.js` → `collector.js`.

## Túnel HTTPS

```bash
cloudflared tunnel --url http://127.0.0.1:8787
```

## Testes

```bash
node --check exporter/kindle-mobile-prototype/book-normalize.js
node --check exporter/kindle-mobile-prototype/collector-core.js
node --check exporter/kindle-mobile-prototype/collector.js
node exporter/kindle-mobile-prototype/test_collector_logic.mjs
node exporter/kindle-mobile-prototype/test_network_security.mjs
pytest tests/ -v
```

Automatizados ≠ teste real Android (≥50 livros + Telegram).

## Backend

Contrato inalterado: `POST /api/import` com `{ code, books }`. Testes pytest cobrem import, dedupe, isolamento, status manual e códigos inválidos/expirados.
