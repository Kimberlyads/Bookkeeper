/** P0.2 — normalização real + núcleo do coletor com fetch mockado. */
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const N = require("./book-normalize.js");
const Core = require("./collector-core.js");
const __dirname = path.dirname(fileURLToPath(import.meta.url));

function jsonResponse(status, body) {
  return {
    ok: status >= 200 && status < 300,
    status,
    async json() {
      return typeof body === "string" ? JSON.parse(body) : body;
    },
  };
}

function pagePayload(start, count, total) {
  const items = [];
  for (let i = 0; i < count; i++) {
    const n = start + i;
    items.push({
      title: "Livro " + n,
      authors: ["Autor " + n],
      asin: "B" + String(n).padStart(8, "0"),
    });
  }
  return {
    GetContentOwnershipData: {
      items,
      numberOfItems: total,
    },
  };
}

function makeAmazonFetch(plan) {
  // plan: array of { type:'ok', start, count, total } | { type:'error', status|message } | { type:'network' }
  let i = 0;
  const calls = [];
  const fetchFn = async (url, init) => {
    calls.push({ url, init });
    if (String(url).includes("/api/import")) {
      return jsonResponse(200, {
        ok: true,
        adicionados: 0,
        ignorados: 0,
        total_recebidos: 0,
      });
    }
    const step = plan[i++];
    if (!step) throw new Error("fetch sem plano");
    if (step.type === "network") throw new Error("Failed to fetch");
    if (step.type === "error") {
      return jsonResponse(step.status || 500, { error: "x" });
    }
    if (step.type === "badjson") {
      return {
        ok: true,
        status: 200,
        async json() {
          throw new Error("bad");
        },
      };
    }
    return jsonResponse(200, pagePayload(step.start, step.count, step.total));
  };
  fetchFn.calls = calls;
  return fetchFn;
}

// --- normalize fallbacks (real module) ---
assert.equal(N.normalizeBook(null), null);
{
  const b = N.normalizeBook({
    productTitle: "PT",
    contentReference: { asin: "B1", contentIdentifier: "C1" },
    contributors: [{ name: "N" }],
    coverImage: "https://c.jpg",
  });
  assert.equal(b.asin, "B1");
  assert.equal(b.productImage, "https://c.jpg");
}

// --- pagination sizes via real importFullLibrary ---
async function importWithPlan(plan, options) {
  const fetchFn = makeAmazonFetch(plan);
  const c = Core.createCollector({
    fetch: fetchFn,
    sleep: async () => {},
    getOrigin: () => "https://www.amazon.com.br",
    options: Object.assign({ BASE_DELAY_MS: 0, RETRY_DELAY_MS: 0 }, options),
  });
  return { library: await c.importFullLibrary("csrf-test"), fetchFn };
}

{
  const { library } = await importWithPlan([
    { type: "ok", start: 0, count: 0, total: 0 },
  ]);
  assert.equal(library.books.length, 0);
}

{
  const { library, fetchFn } = await importWithPlan([
    { type: "ok", start: 0, count: 1, total: 1 },
  ]);
  assert.equal(library.books.length, 1);
  assert.equal(fetchFn.calls.filter((c) => String(c.url).includes("ajax")).length, 1);
}

{
  const { library, fetchFn } = await importWithPlan([
    { type: "ok", start: 0, count: 25, total: 25 },
  ]);
  assert.equal(library.books.length, 25);
  assert.equal(fetchFn.calls.filter((c) => String(c.url).includes("ajax")).length, 1);
}

{
  const { library, fetchFn } = await importWithPlan([
    { type: "ok", start: 0, count: 25, total: 26 },
    { type: "ok", start: 25, count: 1, total: 26 },
  ]);
  assert.equal(library.books.length, 26);
  assert.equal(fetchFn.calls.filter((c) => String(c.url).includes("ajax")).length, 2);
}

{
  const { library, fetchFn } = await importWithPlan([
    { type: "ok", start: 0, count: 25, total: 50 },
    { type: "ok", start: 25, count: 25, total: 50 },
  ]);
  assert.equal(library.books.length, 50);
  assert.equal(fetchFn.calls.filter((c) => String(c.url).includes("ajax")).length, 2);
}

{
  const plan = [];
  for (let p = 0; p < 3; p++) {
    plan.push({ type: "ok", start: p * 25, count: 25, total: 75 });
  }
  const { library } = await importWithPlan(plan);
  assert.equal(library.books.length, 75);
}

// duplicatas entre páginas
{
  const fetchFn = async (url) => {
    if (String(url).includes("/api/import")) {
      return jsonResponse(200, { ok: true, adicionados: 0, ignorados: 0 });
    }
    // always return same two books
    return jsonResponse(200, {
      GetContentOwnershipData: {
        items: [
          { title: "A", asin: "B00A" },
          { title: "B", asin: "B00B" },
        ],
        numberOfItems: 2,
      },
    });
  };
  const c = Core.createCollector({
    fetch: fetchFn,
    sleep: async () => {},
    getOrigin: () => "https://www.amazon.com",
    options: { BASE_DELAY_MS: 0, RETRY_DELAY_MS: 0 },
  });
  const library = await c.importFullLibrary("csrf");
  assert.equal(library.books.length, 2);
}

// página intermediária com erro + retry ok
{
  let ajax = 0;
  const fetchFn = async (url) => {
    if (String(url).includes("ajax")) {
      ajax += 1;
      if (ajax === 2) throw new Error("Failed to fetch");
      const start = ajax === 1 ? 0 : 25;
      // after retry ajax becomes 3 for second page
      const s = ajax <= 2 ? 0 : 25;
      const count = s === 0 ? 25 : 25;
      const startIdx = ajax === 1 ? 0 : ajax === 2 ? 0 : 25;
      // simpler: page1 ok, page2 fail once then ok
      if (ajax === 1) {
        return jsonResponse(200, pagePayload(0, 25, 50));
      }
      if (ajax === 2) throw new Error("Failed to fetch");
      return jsonResponse(200, pagePayload(25, 25, 50));
    }
    return jsonResponse(200, { ok: true });
  };
  const c = Core.createCollector({
    fetch: fetchFn,
    sleep: async () => {},
    getOrigin: () => "https://www.amazon.com.br",
    options: { BASE_DELAY_MS: 0, RETRY_DELAY_MS: 0, MAX_RETRIES: 3 },
  });
  const library = await c.importFullLibrary("csrf");
  assert.equal(library.books.length, 50);
}

// falha permanente na paginação — não engolir
{
  const fetchFn = async (url) => {
    if (String(url).includes("ajax")) throw new Error("Failed to fetch");
    return jsonResponse(200, {});
  };
  const c = Core.createCollector({
    fetch: fetchFn,
    sleep: async () => {},
    getOrigin: () => "https://www.amazon.com.br",
    options: { RETRY_DELAY_MS: 0, MAX_RETRIES: 3 },
  });
  await assert.rejects(() => c.importFullLibrary("csrf"), /Failed to fetch/);
}

// HTTP 500 Amazon
{
  const fetchFn = async () => jsonResponse(500, { error: true });
  const c = Core.createCollector({
    fetch: fetchFn,
    sleep: async () => {},
    getOrigin: () => "https://www.amazon.com.br",
    options: { RETRY_DELAY_MS: 0, MAX_RETRIES: 2 },
  });
  await assert.rejects(() => c.importFullLibrary("csrf"), /Falha HTTP|biblioteca/);
}

// CSRF ausente
{
  const c = Core.createCollector({
    fetch: async () => jsonResponse(200, {}),
    sleep: async () => {},
    getOrigin: () => "https://www.amazon.com.br",
  });
  await assert.rejects(() => c.importFullLibrary(null), /CSRF/);
}

// send 401
{
  const c = Core.createCollector({
    fetch: async () => jsonResponse(401, { error: "invalid_or_expired_code" }),
    sleep: async () => {},
    getOrigin: () => "https://www.amazon.com.br",
  });
  await assert.rejects(
    () =>
      c.sendToBookkeeper("https://api.example/api/import", "DEADCODE", {
        books: [{ title: "T", authors: [], asin: "B1" }],
      }),
    /Código inválido/
  );
}

// HTTPS required
{
  const c = Core.createCollector({
    fetch: async () => jsonResponse(200, {}),
    sleep: async () => {},
    getOrigin: () => "https://www.amazon.com.br",
  });
  assert.throws(() => c.requireHttps("http://127.0.0.1:8787/api/import"));
}

// payload only code+books
{
  const p = N.buildImportPayload("abc", [{ title: "T", authors: [] }]);
  N.assertSafeImportPayload(p);
  assert.throws(() =>
    N.assertSafeImportPayload({ code: "X", books: [], cookie: "a" })
  );
}

// sanitize não ecoa código longo
{
  const c = Core.createCollector({
    fetch: async () => jsonResponse(200, {}),
    sleep: async () => {},
    getOrigin: () => "https://www.amazon.com.br",
  });
  const s = c.sanitizeErrorMessage(new Error("falha CODE99XY token"));
  assert.ok(!s.includes("CODE99XY"));
}

// collector.js não persiste código
{
  const src = fs.readFileSync(path.join(__dirname, "collector.js"), "utf8");
  assert.doesNotMatch(src, /localStorage\.setItem\(\s*["']BOOKKEEPER_LINK_CODE/);
  assert.match(src, /removeItem\("BOOKKEEPER_LINK_CODE"\)/);
  assert.match(src, /delete window\.BOOKKEEPER_LINK_CODE/);
}

// surfaceType documentado como Desktop (igual extensão/comunidade)
{
  const input = N.buildActivityInput(0, 25, -1);
  assert.equal(input.surfaceType, "Desktop");
}

console.log("test_collector_logic P0.2: OK");
