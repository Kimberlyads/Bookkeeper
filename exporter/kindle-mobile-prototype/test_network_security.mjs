/** P0.2 — run() completo com mocks (collector-core real). */
import assert from "node:assert/strict";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const Core = require("./collector-core.js");

function jsonResponse(status, body) {
  return {
    ok: status >= 200 && status < 300,
    status,
    async json() {
      return body;
    },
  };
}

function makeCollector(fetchFn, cfg) {
  return Core.createCollector({
    fetch: fetchFn,
    sleep: async () => {},
    getOrigin: () => "https://www.amazon.com.br",
    getCsrfToken: () => "csrf-ok",
    getConfig: () => cfg || {
      apiUrl: "https://api.example.com/api/import",
      code: "ABCD1234",
    },
    options: { BASE_DELAY_MS: 0, RETRY_DELAY_MS: 0, MAX_RETRIES: 3 },
  });
}

// run sucesso 26 livros
{
  let phase = 0;
  const fetchFn = async (url) => {
    if (String(url).includes("ajax")) {
      phase += 1;
      if (phase === 1) {
        return jsonResponse(200, {
          GetContentOwnershipData: {
            numberOfItems: 26,
            items: Array.from({ length: 25 }, (_, i) => ({
              title: "L" + i,
              asin: "B" + i,
              authors: ["A"],
            })),
          },
        });
      }
      return jsonResponse(200, {
        GetContentOwnershipData: {
          numberOfItems: 26,
          items: [{ title: "L25", asin: "B25", authors: ["A"] }],
        },
      });
    }
    return jsonResponse(200, {
      ok: true,
      adicionados: 26,
      ignorados: 0,
      total_recebidos: 26,
    });
  };
  const c = makeCollector(fetchFn);
  const out = await c.run();
  assert.equal(out.library.books.length, 26);
  assert.equal(out.result.adicionados, 26);
}

// código inválido no run
{
  const fetchFn = async (url) => {
    if (String(url).includes("ajax")) {
      return jsonResponse(200, {
        GetContentOwnershipData: {
          numberOfItems: 1,
          items: [{ title: "T", asin: "B1", authors: [] }],
        },
      });
    }
    return jsonResponse(401, { error: "invalid_or_expired_code" });
  };
  const c = makeCollector(fetchFn);
  await assert.rejects(() => c.run(), /Código inválido/);
}

// HTTP api url bloqueada
{
  const c = makeCollector(async () => jsonResponse(200, {}), {
    apiUrl: "http://127.0.0.1:8787/api/import",
    code: "ABCD1234",
  });
  await assert.rejects(() => c.run(), /HTTPS/);
}

// CSRF missing via run
{
  const c = Core.createCollector({
    fetch: async () => jsonResponse(200, {}),
    sleep: async () => {},
    getOrigin: () => "https://www.amazon.com.br",
    getCsrfToken: () => null,
    getConfig: () => ({
      apiUrl: "https://api.example.com/api/import",
      code: "X",
    }),
    options: { RETRY_DELAY_MS: 0 },
  });
  await assert.rejects(() => c.run(), /CSRF/);
}

console.log("test_network_security P0.2: OK");
