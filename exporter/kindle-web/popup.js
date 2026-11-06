"use strict";

const importButton = document.getElementById("import-button");
const exportButton = document.getElementById("export-button");
const statusText = document.getElementById("status");
const progressWrap = document.getElementById("progress-wrap");
const progressBar = document.getElementById("progress-bar");
const linkCodeInput = document.getElementById("link-code");
let lastLibrary = null;

const KINLE_PATH = "/hz/mycd/";
const DEFAULT_API_URL = "http://127.0.0.1:8787/api/import";

function setStatus(msg) { statusText.textContent = msg; }

function setProgress(current, total) {
  if (!total || total <= 0) {
    progressWrap.style.display = "none";
    progressBar.style.width = "0%";
    return;
  }
  progressWrap.style.display = "block";
  progressBar.style.width = `${Math.min(100, Math.round((current / total) * 100))}%`;
}

function isKindleLibraryUrl(url) {
  if (!url) return false;
  try {
    const u = new URL(url);
    return (u.hostname.includes("amazon.") || u.hostname.includes("amazon.com.br")) &&
      u.pathname.includes(KINLE_PATH);
  } catch { return false; }
}

async function getActiveTab() {
  const [tab] = await chrome.tabs.query({active: true, currentWindow: true});
  return tab;
}

async function ensureContentScript(tabId) {
  try {
    await chrome.scripting.executeScript({target: {tabId}, files: ["content.js"]});
  } catch (_) {}
}

async function getApiUrl() {
  try {
    const stored = await chrome.storage.local.get(["apiUrl"]);
    if (stored.apiUrl) return stored.apiUrl;
  } catch (_) {}
  return DEFAULT_API_URL;
}

function listenProgress(tabId) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      chrome.runtime.onMessage.removeListener(onMessage);
      reject(new Error("Tempo esgotado na importação."));
    }, 10 * 60 * 1000);

    function onMessage(message, sender) {
      if (!sender.tab || sender.tab.id !== tabId) return;
      if (!message || message.source !== "BOOKKEEPER") return;
      if (message.type === "IMPORT_PROGRESS") {
        const {fetched, total, page} = message;
        setProgress(fetched, total);
        setStatus(total
          ? `Importando… página ${page}\n${fetched} de ${total} livros`
          : `Importando… página ${page}\n${fetched} livros`);
        return;
      }
      if (message.type === "IMPORT_COMPLETE") {
        clearTimeout(timer);
        chrome.runtime.onMessage.removeListener(onMessage);
        resolve(message.library);
      } else if (message.type === "IMPORT_ERROR") {
        clearTimeout(timer);
        chrome.runtime.onMessage.removeListener(onMessage);
        reject(new Error(message.error || "Erro desconhecido na importação."));
      }
    }
    chrome.runtime.onMessage.addListener(onMessage);
  });
}

async function sendLibraryToBackend(library, code) {
  const response = await fetch(await getApiUrl(), {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({
      code: code.trim().toUpperCase(),
      books: library.books || [],
      exportedAt: library.exportedAt || null,
      totalContentCount: library.totalContentCount || null
    })
  });
  let data = null;
  try { data = await response.json(); } catch (_) {}
  if (!response.ok || !data?.ok) {
    throw new Error(data?.message || data?.error ||
      `Falha ao enviar (HTTP ${response.status})`);
  }
  return data;
}

chrome.storage.local.get(["linkCode"]).then(stored => {
  if (stored.linkCode) linkCodeInput.value = stored.linkCode;
});
linkCodeInput.addEventListener("change", () => {
  const value = linkCodeInput.value.trim().toUpperCase();
  linkCodeInput.value = value;
  chrome.storage.local.set({linkCode: value});
});

importButton.addEventListener("click", async () => {
  importButton.disabled = true;
  exportButton.disabled = true;
  lastLibrary = null;
  setProgress(0, 0);
  const code = (linkCodeInput.value || "").trim();
  if (!code) {
    setStatus("Informe o código gerado no Telegram com /conectar.");
    importButton.disabled = false;
    return;
  }
  setStatus("Procurando sua biblioteca Kindle...");
  try {
    const tab = await getActiveTab();
    if (!tab?.id || !isKindleLibraryUrl(tab.url)) {
      setStatus("Abra a página Conteúdo e dispositivos do Kindle\n(ex.: amazon.com.br/hz/mycd/) e tente de novo.");
      importButton.disabled = false;
      return;
    }
    await ensureContentScript(tab.id);
    const resultPromise = listenProgress(tab.id);
    await chrome.tabs.sendMessage(tab.id, {source: "BOOKKEEPER", type: "START_IMPORT"});
    const library = await resultPromise;
    lastLibrary = library;
    setProgress(library.books.length, library.totalContentCount || library.books.length);
    setStatus(`Biblioteca lida: ${library.books.length} livros.\nEnviando ao Bookkeeper…`);
    const result = await sendLibraryToBackend(library, code);
    setStatus(
      `Concluído!\n${library.books.length} livros lidos\n+${result.adicionados} novos no bot` +
      (result.ignorados ? `\n${result.ignorados} já existiam/ignorados` : "") +
      "\nConfira a confirmação no Telegram."
    );
    exportButton.disabled = false;
    linkCodeInput.value = "";
    chrome.storage.local.remove(["linkCode"]);
  } catch (error) {
    console.error("Bookkeeper popup:", error);
    setStatus(`Falha: ${error.message || "erro desconhecido"}`);
    if (lastLibrary) exportButton.disabled = false;
  } finally {
    importButton.disabled = false;
  }
});

exportButton.addEventListener("click", () => {
  if (!lastLibrary) {
    setStatus("Nenhuma biblioteca para exportar. Importe primeiro.");
    return;
  }
  const blob = new Blob([JSON.stringify(lastLibrary, null, 2)], {type: "application/json"});
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  const stamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-");
  a.href = url;
  a.download = `kindle-library-${stamp}.json`;
  a.click();
  URL.revokeObjectURL(url);
  setStatus(`JSON exportado (${lastLibrary.books.length} livros).`);
});
