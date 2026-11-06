(() => {
  "use strict";

  /**
   * content.js — mundo isolado (Chrome extension).
   * Orquestra a paginação e fala com o popup via chrome.runtime.
   * As requisições HTTP reais ficam em main.js (MAIN world).
   * Não altera o fluxo de interceptação/CSRF da Amazon.
   */
  const BATCH_SIZE = 25;
  const MAX_RETRIES = 3;
  const BASE_DELAY_MS = 400;
  const RETRY_DELAY_MS = 1200;

  window.addEventListener("message", (event) => {
    if (event.source !== window) return;
    if (event.data?.source !== "BOOKKEEPER_KINLE") return;
    if (event.data.type === "KINDLE_BATCH_RESPONSE") {
      const pending = window.__bookkeeperPending;
      if (pending && pending.requestId === event.data.requestId) pending.resolve(event.data);
      return;
    }
    if (event.data.type === "KINDLE_BATCH_ERROR") {
      const pending = window.__bookkeeperPending;
      if (pending && pending.requestId === event.data.requestId) {
        pending.reject(new Error(event.data.error || "Falha na requisição Kindle"));
      }
    }
  });

  function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  function requestBatch(startIndex, batchSize, totalHint) {
    const requestId = `bk_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`;
    return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        if (window.__bookkeeperPending?.requestId === requestId) {
          window.__bookkeeperPending = null;
          reject(new Error("Timeout aguardando resposta da Amazon"));
        }
      }, 45000);
      window.__bookkeeperPending = {
        requestId,
        resolve: (data) => {
          clearTimeout(timeout);
          window.__bookkeeperPending = null;
          resolve(data);
        },
        reject: (error) => {
          clearTimeout(timeout);
          window.__bookkeeperPending = null;
          reject(error);
        }
      };
      window.postMessage({
        source: "BOOKKEEPER_CONTENT",
        type: "FETCH_KINDLE_BATCH",
        requestId,
        startIndex,
        batchSize,
        totalContentCount: totalHint ?? null
      }, window.location.origin);
    });
  }

  function extractItems(payload) {
    const data = payload?.data ?? payload;
    const ownership = data?.GetContentOwnershipData ??
      data?.contentOwnershipData ?? data?.OwnershipData ?? data;
    const items = ownership?.items ?? ownership?.contentItems ??
      ownership?.OwnershipData?.items ?? data?.items ?? [];
    const total = ownership?.totalContentCount ??
      ownership?.numberOfItems ?? data?.totalContentCount ?? null;
    return {items: Array.isArray(items) ? items : [], total};
  }

  function normalizeBook(raw) {
    const asin = raw.asin || raw.ASIN || raw.contentReference?.asin || raw.resourceId || null;
    const contentIdentifier = raw.contentIdentifier ||
      raw.contentReference?.contentIdentifier || asin;
    let authors = raw.authors || raw.authorList || raw.contributors || [];
    if (typeof authors === "string") authors = [authors];
    if (!Array.isArray(authors)) authors = [];
    return {
      title: raw.title || raw.productTitle || null,
      authors,
      asin,
      contentIdentifier,
      productImage: raw.productImage || raw.imageUrl || raw.coverImage || null,
      acquiredDate: raw.acquiredDate || raw.purchaseDate || null,
      readStatus: raw.readStatus || raw.readingStatus || null,
      collectionList: raw.collectionList || raw.collections || [],
      originType: raw.originType || null,
      isPurchased: typeof raw.isPurchased === "boolean" ? raw.isPurchased : null
    };
  }

  function bookKey(book) {
    return book.asin || book.contentIdentifier ||
      `${book.title}|${JSON.stringify(book.authors)}`;
  }

  async function fetchBatchWithRetry(startIndex, batchSize, totalHint) {
    let lastError;
    for (let attempt = 1; attempt <= MAX_RETRIES; attempt++) {
      try {
        const response = await requestBatch(startIndex, batchSize, totalHint);
        if (response.error) throw new Error(response.error);
        return response.data;
      } catch (error) {
        lastError = error;
        if (attempt < MAX_RETRIES) await sleep(RETRY_DELAY_MS * attempt);
      }
    }
    throw lastError || new Error("Falha após retentativas");
  }

  async function importFullLibrary() {
    const seen = new Set();
    const books = [];
    let startIndex = 0;
    let totalContentCount = null;
    let page = 0;
    while (true) {
      page += 1;
      const payload = await fetchBatchWithRetry(startIndex, BATCH_SIZE, totalContentCount);
      const {items, total} = extractItems(payload);
      if (total != null && totalContentCount == null) totalContentCount = Number(total);
      for (const raw of items) {
        const book = normalizeBook(raw);
        const key = bookKey(book);
        if (!key || seen.has(key)) continue;
        seen.add(key);
        books.push(book);
      }
      try {
        chrome.runtime.sendMessage({
          source: "BOOKKEEPER",
          type: "IMPORT_PROGRESS",
          fetched: books.length,
          total: totalContentCount,
          page
        });
      } catch (_) {}
      if (!items.length) break;
      if (totalContentCount != null && startIndex + items.length >= totalContentCount) break;
      if (items.length < BATCH_SIZE && totalContentCount == null) break;
      startIndex += BATCH_SIZE;
      await sleep(BASE_DELAY_MS);
    }
    return {
      exportedAt: new Date().toISOString(),
      source: "kindle-web",
      totalContentCount,
      books
    };
  }

  chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (message?.source !== "BOOKKEEPER" || message.type !== "START_IMPORT") return;
    (async () => {
      try {
        const library = await importFullLibrary();
        chrome.runtime.sendMessage({source: "BOOKKEEPER", type: "IMPORT_COMPLETE", library});
        sendResponse({ok: true});
      } catch (error) {
        chrome.runtime.sendMessage({
          source: "BOOKKEEPER",
          type: "IMPORT_ERROR",
          error: error.message || String(error)
        });
        sendResponse({ok: false, error: error.message});
      }
    })();
    return true;
  });
})();
