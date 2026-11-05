(() => {
  console.log("Bookkeeper: main.js foi carregado");

  const TARGET_URL = "/hz/mycd/digital-console/ajax";
  const TARGET_OPERATION = "GetContentOwnershipData";

  function isLibraryRequest(body) {
    if (typeof body === "string") {
      return body.includes(TARGET_OPERATION);
    }

    if (body instanceof URLSearchParams) {
      return body.toString().includes(TARGET_OPERATION);
    }

    return false;
  }

  function enviarResposta(data, requestBody = "") {
    if (!data) return;

    let responseText = "";
    try {
      responseText = JSON.stringify(data);
    } catch (_) {
      return;
    }

    // A operação pode aparecer no corpo da requisição ou na resposta.
    if (
      !isLibraryRequest(requestBody) &&
      !responseText.includes(TARGET_OPERATION)
    ) {
      return;
    }

    console.log(
      "Bookkeeper: resposta com GetContentOwnershipData detectada"
    );

    window.postMessage(
      {
        source: "BOOKKEEPER_KINLE",
        type: "KINDLE_LIBRARY_RESPONSE",
        data,
      },
      window.location.origin
    );
  }

  // Observa chamadas feitas com fetch sem consumir a resposta original.
  const originalFetch = window.fetch;

  window.fetch = async function (...args) {
    const response = await originalFetch.apply(this, args);

    const requestUrl =
      typeof args[0] === "string"
        ? args[0]
        : args[0]?.url || "";

    if (requestUrl.includes(TARGET_URL)) {
      const requestBody = args[1]?.body || "";

      console.log("Bookkeeper: fetch Kindle detectado");

      try {
        response
          .clone()
          .json()
          .then((data) => enviarResposta(data, requestBody))
          .catch(() => {});
      } catch (error) {
        console.error(
          "Bookkeeper: erro ao observar resposta fetch",
          error
        );
      }
    }

    return response;
  };

  // Observa chamadas feitas com XMLHttpRequest.
  const originalXhrOpen = XMLHttpRequest.prototype.open;
  const originalXhrSend = XMLHttpRequest.prototype.send;

  XMLHttpRequest.prototype.open = function (method, url, ...rest) {
    this.bookkeeperUrl = String(url);

    if (this.bookkeeperUrl.includes(TARGET_URL)) {
      console.log("Bookkeeper: XHR Kindle detectado");
    }

    return originalXhrOpen.call(this, method, url, ...rest);
  };

  XMLHttpRequest.prototype.send = function (...args) {
    const requestBody = args[0] || "";

    if (this.bookkeeperUrl?.includes(TARGET_URL)) {
      this.addEventListener("load", function () {
        try {
          let data;

          if (this.responseType === "json") {
            data = this.response;
          } else if (
            this.responseType === "" ||
            this.responseType === "text"
          ) {
            if (!this.responseText) return;
            data = JSON.parse(this.responseText);
          } else {
            return;
          }

          enviarResposta(data, requestBody);
        } catch (error) {
          console.error(
            "Bookkeeper: erro ao interpretar resposta XHR",
            error
          );
        }
      });
    }

    return originalXhrSend.apply(this, args);
  };

  console.log("Bookkeeper: observadores fetch e XHR instalados");
})();