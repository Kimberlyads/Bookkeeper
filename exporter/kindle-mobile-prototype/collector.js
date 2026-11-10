/**
 * Bookkeeper — coletor experimental (browser) — P0.2
 * Carregar: book-normalize.js → collector-core.js → collector.js
 * Código de pareamento: só memória; limpa resíduos de localStorage.
 */
(function () {
  "use strict";

  var N =
    typeof BookkeeperKindleNormalize !== "undefined"
      ? BookkeeperKindleNormalize
      : null;
  var Core =
    typeof BookkeeperCollectorCore !== "undefined"
      ? BookkeeperCollectorCore
      : null;

  if (!N || !Core) {
    console.error(
      "[Bookkeeper] Carregue book-normalize.js e collector-core.js antes."
    );
    return;
  }

  // Permite reexecução controlada em testes (window.__BOOKKEEPER_ALLOW_RERUN__)
  if (
    window.__BOOKKEEPER_MOBILE_COLLECTOR__ &&
    !window.__BOOKKEEPER_ALLOW_RERUN__
  ) {
    console.warn("[Bookkeeper] Coletor já em execução.");
    return;
  }
  window.__BOOKKEEPER_MOBILE_COLLECTOR__ = true;

  function ui(msg) {
    console.log("[Bookkeeper]", msg);
    try {
      var el = document.getElementById("bookkeeper-mobile-status");
      if (!el) {
        el = document.createElement("div");
        el.id = "bookkeeper-mobile-status";
        el.setAttribute(
          "style",
          "position:fixed;z-index:2147483647;left:8px;right:8px;bottom:8px;" +
            "max-height:40vh;overflow:auto;background:#111;color:#eee;" +
            "font:13px/1.4 system-ui,sans-serif;padding:12px;border-radius:8px;" +
            "box-shadow:0 4px 24px rgba(0,0,0,.4);"
        );
        (document.body || document.documentElement).appendChild(el);
      }
      el.textContent = String(msg);
    } catch (_) {}
  }

  function findCsrfToken() {
    if (typeof window.csrfToken === "string" && window.csrfToken.trim()) {
      return window.csrfToken.trim();
    }
    var input = document.querySelector(
      'input[name="csrfToken"], input[name="csrf-token"], meta[name="csrf-token"]'
    );
    if (input) {
      var v = input.getAttribute("content") || input.value;
      if (v && String(v).trim()) return String(v).trim();
    }
    var html =
      document.documentElement && document.documentElement.innerHTML;
    if (html) {
      var m = html.match(/csrfToken["']\s*[:=]\s*["']([^"']+)["']/);
      if (m) return m[1];
    }
    return null;
  }

  function clearStalePairingCode() {
    try {
      if (typeof localStorage !== "undefined") {
        localStorage.removeItem("BOOKKEEPER_LINK_CODE");
      }
      if (typeof sessionStorage !== "undefined") {
        sessionStorage.removeItem("BOOKKEEPER_LINK_CODE");
      }
    } catch (_) {}
  }

  function resolveConfig() {
    clearStalePairingCode();
    var apiUrl = window.BOOKKEEPER_API_URL || "";
    try {
      if (!apiUrl && typeof localStorage !== "undefined") {
        apiUrl = localStorage.getItem("BOOKKEEPER_API_URL") || "";
      }
    } catch (_) {}
    var code = window.BOOKKEEPER_LINK_CODE || "";
    if (!apiUrl) {
      apiUrl = window.prompt(
        "URL HTTPS do POST /api/import do Bookkeeper\n" +
          "(ex.: https://xxxx.trycloudflare.com/api/import)"
      );
    }
    if (!code) {
      code = window.prompt(
        "Código temporário do Telegram (/conectar).\n" +
          "O código não será salvo neste aparelho."
      );
    }
    try {
      delete window.BOOKKEEPER_LINK_CODE;
    } catch (_) {
      window.BOOKKEEPER_LINK_CODE = "";
    }
    clearStalePairingCode();
    return {
      apiUrl: String(apiUrl || "").trim().replace(/\/$/, ""),
      code: String(code || "").trim(),
    };
  }

  var collector = Core.createCollector({
    fetch: window.fetch.bind(window),
    getOrigin: function () {
      return window.location.origin;
    },
    getCsrfToken: findCsrfToken,
    getConfig: resolveConfig,
    onStatus: ui,
    onProgress: function (p) {
      var total = p.total != null ? p.total : "?";
      ui(
        "Progresso: " + p.fetched + "/" + total + " livros (página " + p.page + ")"
      );
    },
  });

  window.BookkeeperMobileCollector = collector;

  if (window.__BOOKKEEPER_SKIP_AUTORUN__) {
    return;
  }

  collector
    .run()
    .then(function () {
      window.__BOOKKEEPER_MOBILE_COLLECTOR__ = false;
    })
    .catch(function (err) {
      window.__BOOKKEEPER_MOBILE_COLLECTOR__ = false;
      ui(
        "Erro: " +
          (collector.sanitizeErrorMessage
            ? collector.sanitizeErrorMessage(err)
            : "falha")
      );
      console.error(err);
    });
})();
