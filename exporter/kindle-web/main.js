(() => {
  console.log("Bookkeeper: main.js foi carregado");

  const originalFetch = window.fetch;
  console.log("Bookkeeper: observando chamadas fetch");
  
  window.fetch = async function (...args) {
    const response = await originalFetch.apply(this, args);

    const requestUrl =
      typeof args[0] === "string"
        ? args[0]
        : args[0]?.url || "";
    console.log(
      "Bookkeeper: chamada fetch detectada",
      requestUrl.split("?")[0]
    );

    try {
      const url =
        typeof args[0] === "string"
          ? args[0]
          : args[0]?.url || "";

      if (url.includes("/hz/mycd/digital-console/ajax")) {
        const clone = response.clone();

        clone
          .json()
          .then((data) => {
            const text = JSON.stringify(data);

            if (text.includes("GetContentOwnershipData")) {
              window.postMessage(
                {
                  source: "BOOKKEEPER_KINLE",
                  type: "KINDLE_LIBRARY_RESPONSE",
                  data,
                },
                window.location.origin
              );
            }
          })
          .catch(() => {});
      }
    } catch (error) {
      console.error("Bookkeeper: erro ao observar resposta", error);
    }

    return response;
  };

  const originalXhrOpen = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function (method, url, ...rest) {
    console.log(
      "Bookkeeper: chamada XHR detectada",
      String(url).split("?")[0]
    );
    return originalXhrOpen.call(this, method, url, ...rest);
  };
})();