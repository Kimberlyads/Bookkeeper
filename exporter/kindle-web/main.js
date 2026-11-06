(() => {
  "use strict";

  const TARGET_URL = "/hz/mycd/digital-console/ajax";
  const TARGET_OPERATION = "GetContentOwnershipData";
  console.log("Bookkeeper: main.js carregado (MAIN world)");
  let requestTemplate = null;

  function toParams(body) {
    if (typeof body === "string") return new URLSearchParams(body);
    if (body instanceof URLSearchParams) return new URLSearchParams(body.toString());
    return null;
  }

  function captureRequest(body) {
    const params = toParams(body);
    if (!params || params.get("activity") !== TARGET_OPERATION) return;
    const activityInput = params.get("activityInput");
    if (!activityInput) return;
    try {
      JSON.parse(activityInput);
      requestTemplate = params;
      console.log("Bookkeeper: modelo de requisição Kindle capturado.");
    } catch {
      console.warn("Bookkeeper: activityInput inválido.");
    }
  }

  function isLibraryRequest(body) {
    return toParams(body)?.get("activity") === TARGET_OPERATION;
  }

  function notifyPassive(data, requestBody = "") {
    if (!data) return;
    if (!isLibraryRequest(requestBody) &&
        !JSON.stringify(data).includes(TARGET_OPERATION)) return;
    window.postMessage({
      source: "BOOKKEEPER_KINLE",
      type: "KINDLE_LIBRARY_RESPONSE",
      data
    }, window.location.origin);
  }

  const originalFetch = window.fetch;
  window.fetch = async function (...args) {
    const requestUrl = typeof args[0] === "string" ? args[0] : args[0]?.url || "";
    const requestBody = args[1]?.body || "";
    if (requestUrl.includes(TARGET_URL)) captureRequest(requestBody);
    const response = await originalFetch.apply(this, args);
    if (requestUrl.includes(TARGET_URL)) {
      try {
        response.clone().json()
          .then(data => notifyPassive(data, requestBody))
          .catch(() => {});
      } catch (_) {}
    }
    return response;
  };

  const originalXhrOpen = XMLHttpRequest.prototype.open;
  const originalXhrSend = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function (method, url, ...rest) {
    this.bookkeeperUrl = String(url);
    return originalXhrOpen.call(this, method, url, ...rest);
  };
  XMLHttpRequest.prototype.send = function (...args) {
    const requestBody = args[0] || "";
    if (this.bookkeeperUrl?.includes(TARGET_URL)) {
      captureRequest(requestBody);
      this.addEventListener("load", function () {
        try {
          let data;
          if (this.responseType === "json") data = this.response;
          else if (this.responseType === "" || this.responseType === "text") {
            if (!this.responseText) return;
            data = JSON.parse(this.responseText);
          } else return;
          notifyPassive(data, requestBody);
        } catch (_) {}
      });
    }
    return originalXhrSend.apply(this, args);
  };

  function buildPayload(startIndex, batchSize, totalContentCount) {
    if (!requestTemplate) {
      throw new Error("A Amazon ainda não realizou uma requisição da biblioteca. Atualize a página Kindle e tente novamente.");
    }
    const params = new URLSearchParams(requestTemplate.toString());
    const activityInput = JSON.parse(params.get("activityInput"));
    if (!activityInput.fetchCriteria) {
      throw new Error("Não foi possível localizar os critérios de paginação da Amazon.");
    }
    activityInput.fetchCriteria.startIndex = Number(startIndex) || 0;
    activityInput.fetchCriteria.batchSize = Number(batchSize) || 25;
    activityInput.fetchCriteria.totalContentCount =
      totalContentCount != null ? Number(totalContentCount) : -1;
    params.set("activityInput", JSON.stringify(activityInput));
    return params.toString();
  }

  async function fetchOwnershipBatch({startIndex, batchSize, totalContentCount}) {
    const body = buildPayload(startIndex, batchSize, totalContentCount);
    const response = await originalFetch(TARGET_URL, {
      method: "POST",
      credentials: "include",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
        Accept: "application/json, text/plain, */*"
      },
      body
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    if (data?.errors || data?.error) {
      throw new Error("A Amazon retornou um erro ao buscar esta página.");
    }
    return data;
  }

  window.addEventListener("message", async event => {
    if (event.source !== window) return;
    if (event.data?.source !== "BOOKKEEPER_CONTENT") return;
    if (event.data.type !== "FETCH_KINDLE_BATCH") return;
    const {requestId, startIndex, batchSize, totalContentCount} = event.data;
    try {
      const data = await fetchOwnershipBatch({startIndex, batchSize, totalContentCount});
      window.postMessage({
        source: "BOOKKEEPER_KINLE",
        type: "KINDLE_BATCH_RESPONSE",
        requestId,
        data
      }, window.location.origin);
    } catch (error) {
      window.postMessage({
        source: "BOOKKEEPER_KINLE",
        type: "KINDLE_BATCH_ERROR",
        requestId,
        error: error.message || String(error)
      }, window.location.origin);
    }
  });
  console.log("Bookkeeper: interceptores e bridge de batch prontos");
})();
