/**
 * Bookkeeper — normalização de itens Kindle (fonte única).
 * Usado pelo coletor mobile e pelos testes automatizados.
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory();
  } else {
    root.BookkeeperKindleNormalize = factory();
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  function extractItems(payload) {
    if (!payload || typeof payload !== "object") {
      return { items: [], total: null };
    }
    const ownership =
      payload.GetContentOwnershipData ||
      (payload.data && payload.data.GetContentOwnershipData) ||
      null;
    if (!ownership || typeof ownership !== "object") {
      return { items: [], total: null };
    }
    const items = ownership.items || ownership.contentList || [];
    let total = null;
    if (ownership.numberOfItems != null) total = ownership.numberOfItems;
    else if (ownership.totalContentCount != null)
      total = ownership.totalContentCount;
    return {
      items: Array.isArray(items) ? items : [],
      total: total != null ? Number(total) : null,
    };
  }

  function normalizeBook(raw) {
    if (!raw || typeof raw !== "object") return null;

    const asin =
      raw.asin ||
      raw.ASIN ||
      (raw.contentReference && raw.contentReference.asin) ||
      raw.resourceId ||
      null;

    const contentIdentifier =
      raw.contentIdentifier ||
      (raw.contentReference && raw.contentReference.contentIdentifier) ||
      asin ||
      null;

    let authors = raw.authors || raw.authorList || raw.contributors || [];
    if (typeof authors === "string") authors = [authors];
    if (!Array.isArray(authors)) authors = [];
    authors = authors
      .map(function (a) {
        if (typeof a === "string") return a;
        if (a && typeof a === "object") {
          return a.name || a.authorName || null;
        }
        return null;
      })
      .filter(Boolean);

    const title = raw.title || raw.productTitle || null;
    if (!title || !String(title).trim()) return null;

    return {
      title: String(title).trim(),
      authors: authors,
      asin: asin != null && String(asin).trim() ? String(asin).trim() : null,
      contentIdentifier:
        contentIdentifier != null && String(contentIdentifier).trim()
          ? String(contentIdentifier).trim()
          : null,
      productImage:
        raw.productImage || raw.imageUrl || raw.coverImage || null,
      acquiredDate: raw.acquiredDate || raw.purchaseDate || null,
      readStatus: raw.readStatus || raw.readingStatus || null,
      collectionList: Array.isArray(raw.collectionList)
        ? raw.collectionList
        : Array.isArray(raw.collections)
          ? raw.collections
          : [],
      originType: raw.originType || null,
      isPurchased:
        typeof raw.isPurchased === "boolean" ? raw.isPurchased : null,
    };
  }

  function bookKey(book) {
    if (!book || typeof book !== "object") return "";
    if (book.asin) return String(book.asin);
    if (book.contentIdentifier) return String(book.contentIdentifier);
    return (
      String(book.title || "") + "|" + JSON.stringify(book.authors || [])
    );
  }

  function dedupeBooks(books) {
    const seen = Object.create(null);
    const out = [];
    for (let i = 0; i < (books || []).length; i++) {
      const b = books[i];
      if (!b) continue;
      const k = bookKey(b);
      if (!k || seen[k]) continue;
      seen[k] = true;
      out.push(b);
    }
    return out;
  }

  function buildActivityInput(startIndex, batchSize, totalHint) {
    return {
      contentType: "Ebook",
      contentCategoryReference: "booksAll",
      itemStatusList: ["Active"],
      showSharedContent: true,
      fetchCriteria: {
        sortOrder: "DESCENDING",
        sortIndex: "DATE",
        startIndex: Number(startIndex) || 0,
        batchSize: Number(batchSize) || 25,
        totalContentCount:
          totalHint != null && totalHint >= 0 ? Number(totalHint) : -1,
      },
      surfaceType: "Desktop",
    };
  }

  /** Monta o body JSON enviado ao Bookkeeper (somente code + books). */
  function buildImportPayload(code, books) {
    return {
      code: String(code || "").trim().toUpperCase(),
      books: Array.isArray(books) ? books : [],
    };
  }

  function assertSafeImportPayload(payload) {
    if (!payload || typeof payload !== "object") {
      throw new Error("payload inválido");
    }
    const keys = Object.keys(payload).sort();
    const expected = ["books", "code"];
    if (keys.length !== 2 || keys[0] !== "books" || keys[1] !== "code") {
      throw new Error(
        "payload deve conter somente code e books; recebido: " + keys.join(",")
      );
    }
    const forbidden = [
      "cookie",
      "cookies",
      "csrf",
      "csrfToken",
      "password",
      "senha",
      "session",
      "token",
      "authorization",
    ];
    // Checa apenas chaves top-level (títulos de livros podem conter essas palavras).
    for (let i = 0; i < forbidden.length; i++) {
      if (Object.prototype.hasOwnProperty.call(payload, forbidden[i])) {
        throw new Error("campo proibido no payload");
      }
    }
    return true;
  }

  return {
    extractItems: extractItems,
    normalizeBook: normalizeBook,
    bookKey: bookKey,
    dedupeBooks: dedupeBooks,
    buildActivityInput: buildActivityInput,
    buildImportPayload: buildImportPayload,
    assertSafeImportPayload: assertSafeImportPayload,
  };
});
