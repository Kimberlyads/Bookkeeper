(() => {
  window.addEventListener("message", (event) => {
    if (event.source !== window) return;

    if (event.data?.source !== "BOOKKEEPER_KINLE") return;

    if (event.data?.type !== "KINDLE_LIBRARY_RESPONSE") return;

    console.log(
      "Bookkeeper: resposta da biblioteca Kindle recebida",
      event.data.data
    );
  });
})();