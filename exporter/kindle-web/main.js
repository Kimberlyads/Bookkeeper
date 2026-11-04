(() => {
  console.log("Bookkeeper: main.js foi carregado");

  const originalFetch = window.fetch;
  
  window.fetch = async function (...args) {
    const response = await originalFetch.apply(this, args);

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
})();