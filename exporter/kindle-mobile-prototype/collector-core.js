/**
 * Núcleo do coletor mobile (P0.2) — testável via injeção de dependências.
 * Não acessa DOM. O collector.js do browser adapta fetch/UI/prompts.
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory(
      typeof require === "function" ? require("./book-normalize.js") : null
    );
  } else {
    root.BookkeeperCollectorCore = factory(root.BookkeeperKindleNormalize);
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function (N) {
  "use strict";

  if (!N) {
    throw new Error("BookkeeperKindleNormalize é obrigatório");
  }

  var DEFAULTS = {
    BATCH_SIZE: 25,
    MAX_RETRIES: 3,
    BASE_DELAY_MS: 400,
    RETRY_DELAY_MS: 800,
    TARGET_PATH: "/hz/mycd/digital-console/ajax",
  };

  /**
   * @param {object} deps
   * @param {typeof fetch} deps.fetch
   * @param {(ms:number)=>Promise<void>} [deps.sleep]
   * @param {()=>string} [deps.getOrigin] retorna origin Amazon, ex. https://www.amazon.com.br
   * @param {()=>string|null} [deps.getCsrfToken]
   * @param {()=>{apiUrl:string, code:string}} [deps.getConfig]
   * @param {(msg:string)=>void} [deps.onStatus]
   * @param {(info:object)=>void} [deps.onProgress]
   * @param {object} [deps.options] overrides BATCH_SIZE etc.
   */
  function createCollector(deps) {
    deps = deps || {};
    if (typeof deps.fetch !== "function") {
      throw new Error("deps.fetch é obrigatório");
    }
    var fetchFn = deps.fetch;
    var sleep =
      deps.sleep ||
      function (ms) {
        return new Promise(function (r) {
          setTimeout(r, ms);
        });
      };
    var opts = Object.assign({}, DEFAULTS, deps.options || {});
    var onStatus = deps.onStatus || function () {};
    var onProgress = deps.onProgress || function () {};

    function ajaxUrl() {
      var origin = deps.getOrigin ? deps.getOrigin() : "";
      if (!origin) throw new Error("Origem Amazon indisponível");
      return String(origin).replace(/\/$/, "") + opts.TARGET_PATH;
    }

    function sanitizeErrorMessage(err) {
      var msg = err && err.message ? String(err.message) : "erro desconhecido";
      // Não ecoar possíveis códigos/tokens longos
      msg = msg.replace(/\b[A-Z0-9]{6,12}\b/g, "[redacted]");
      if (msg.length > 180) msg = msg.slice(0, 180) + "…";
      return msg;
    }

    async function requestBatch(csrf, startIndex, batchSize, totalHint) {
      if (!csrf) {
        var e = new Error("CSRF ausente na página Amazon");
        e.code = "CSRF_MISSING";
        throw e;
      }
      var body = new URLSearchParams();
      body.set("activity", "GetContentOwnershipData");
      body.set(
        "activityInput",
        JSON.stringify(N.buildActivityInput(startIndex, batchSize, totalHint))
      );
      body.set("clientId", "MYCD_WebService");
      body.set("csrfToken", csrf);

      var response = await fetchFn(ajaxUrl(), {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
          Accept: "application/json, text/plain, */*",
        },
        body: body.toString(),
      });
      if (!response.ok) {
        var httpErr = new Error("Falha HTTP ao consultar a biblioteca");
        httpErr.status = response.status;
        httpErr.code = "AMAZON_HTTP";
        throw httpErr;
      }
      var data;
      try {
        data = await response.json();
      } catch (_) {
        var parseErr = new Error("Resposta inválida da biblioteca");
        parseErr.code = "AMAZON_BAD_JSON";
        throw parseErr;
      }
      if (data && (data.error || data.errors)) {
        var apiErr = new Error("A biblioteca retornou erro");
        apiErr.code = "AMAZON_API_ERROR";
        throw apiErr;
      }
      return data;
    }

    async function fetchBatchWithRetry(csrf, startIndex, batchSize, totalHint) {
      var lastError;
      for (var attempt = 1; attempt <= opts.MAX_RETRIES; attempt++) {
        try {
          return await requestBatch(csrf, startIndex, batchSize, totalHint);
        } catch (err) {
          lastError = err;
          if (err && err.code === "CSRF_MISSING") throw err;
          if (attempt < opts.MAX_RETRIES) {
            await sleep(opts.RETRY_DELAY_MS * attempt);
          }
        }
      }
      throw lastError || new Error("Falha após retentativas");
    }

    async function importFullLibrary(csrf) {
      var seen = Object.create(null);
      var books = [];
      var startIndex = 0;
      var totalContentCount = null;
      var page = 0;

      while (true) {
        page += 1;
        var payload = await fetchBatchWithRetry(
          csrf,
          startIndex,
          opts.BATCH_SIZE,
          totalContentCount
        );
        var extracted = N.extractItems(payload);
        var items = extracted.items;
        var total = extracted.total;
        if (total != null && totalContentCount == null) {
          totalContentCount = Number(total);
        }
        for (var i = 0; i < items.length; i++) {
          var book = N.normalizeBook(items[i]);
          if (!book) continue;
          var key = N.bookKey(book);
          if (!key || seen[key]) continue;
          seen[key] = true;
          books.push(book);
        }
        onProgress({
          fetched: books.length,
          total: totalContentCount,
          page: page,
        });
        if (!items.length) break;
        if (
          totalContentCount != null &&
          startIndex + items.length >= totalContentCount
        ) {
          break;
        }
        if (items.length < opts.BATCH_SIZE && totalContentCount == null) break;
        startIndex += opts.BATCH_SIZE;
        await sleep(opts.BASE_DELAY_MS);
      }

      return {
        exportedAt: new Date().toISOString(),
        source: "kindle-mobile-prototype",
        totalContentCount: totalContentCount,
        books: books,
      };
    }

    async function sendToBookkeeper(apiUrl, code, library) {
      requireHttps(apiUrl);
      var payload = N.buildImportPayload(code, library.books);
      N.assertSafeImportPayload(payload);

      var response = await fetchFn(apiUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      var body = null;
      try {
        body = await response.json();
      } catch (_) {}
      if (!response.ok) {
        var err = new Error(
          response.status === 401
            ? "Código inválido ou expirado"
            : "Falha ao enviar biblioteca"
        );
        err.status = response.status;
        err.body = body;
        err.code =
          response.status === 401 ? "INVALID_CODE" : "IMPORT_HTTP_ERROR";
        throw err;
      }
      return body;
    }

    function requireHttps(url) {
      if (!/^https:\/\//i.test(String(url || ""))) {
        var e = new Error("A URL da API deve ser HTTPS");
        e.code = "HTTPS_REQUIRED";
        throw e;
      }
    }

    /**
     * Config: código somente memória (passado por getConfig).
     * Não lê/grava código em storage — responsabilidade do adapter.
     */
    async function run() {
      onStatus("Iniciando…");
      var csrf = deps.getCsrfToken ? deps.getCsrfToken() : null;
      if (!csrf) {
        onStatus("CSRF ausente. Abra a lista de livros e tente de novo.");
        var e = new Error("CSRF ausente");
        e.code = "CSRF_MISSING";
        throw e;
      }
      var cfg = deps.getConfig ? deps.getConfig() : { apiUrl: "", code: "" };
      var apiUrl = String((cfg && cfg.apiUrl) || "").trim().replace(/\/$/, "");
      var code = String((cfg && cfg.code) || "").trim();
      if (!apiUrl || !code) {
        onStatus("API URL ou código ausente.");
        var e2 = new Error("Config incompleta");
        e2.code = "CONFIG_MISSING";
        throw e2;
      }
      if (!/\/api\/import$/i.test(apiUrl)) {
        apiUrl = apiUrl + "/api/import";
      }
      requireHttps(apiUrl);

      onStatus("Consultando biblioteca…");
      var library = await importFullLibrary(csrf);
      if (!library.books.length) {
        onStatus("Nenhum livro encontrado.");
        return { library: library, result: null };
      }
      onStatus("Enviando " + library.books.length + " livros…");

      var lastErr = null;
      for (var attempt = 1; attempt <= opts.MAX_RETRIES; attempt++) {
        try {
          var result = await sendToBookkeeper(apiUrl, code, library);
          onStatus(
            "Concluído. Adicionados: " +
              (result && result.adicionados) +
              " | Ignorados: " +
              (result && result.ignorados)
          );
          return { library: library, result: result };
        } catch (err) {
          lastErr = err;
          onStatus(
            "Falha no envio (tentativa " +
              attempt +
              "): " +
              sanitizeErrorMessage(err)
          );
          if (err && err.code === "INVALID_CODE") throw err;
          if (attempt < opts.MAX_RETRIES) {
            await sleep(opts.RETRY_DELAY_MS * attempt);
          }
        }
      }
      throw lastErr || new Error("Falha no envio");
    }

    return {
      requestBatch: requestBatch,
      fetchBatchWithRetry: fetchBatchWithRetry,
      importFullLibrary: importFullLibrary,
      sendToBookkeeper: sendToBookkeeper,
      requireHttps: requireHttps,
      sanitizeErrorMessage: sanitizeErrorMessage,
      run: run,
      options: opts,
    };
  }

  return {
    createCollector: createCollector,
    DEFAULTS: DEFAULTS,
  };
});
