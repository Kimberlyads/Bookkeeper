"use strict";

const importButton = document.getElementById("import-button");
const statusText = document.getElementById("status");

importButton.addEventListener("click", async () => {
  statusText.textContent = "Procurando sua biblioteca Kindle...";

  try {
    const [tab] = await chrome.tabs.query({
      active: true,
      currentWindow: true
    });

    if (!tab || !tab.url || !tab.url.includes("amazon.")) {
      statusText.textContent =
        "Abra sua biblioteca Kindle no navegador primeiro.";
      return;
    }

    statusText.textContent =
      "Conectado à página do Kindle. A leitura dos livros será implementada em seguida.";
  } catch (error) {
    console.error("Erro ao acessar a página:", error);

    statusText.textContent =
      "Não consegui acessar a página. Tente novamente.";
  }
});