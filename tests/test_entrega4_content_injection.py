"""Testes da Entrega 4: proteção contra injeção duplicada de content.js."""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CONTENT_JS = ROOT / "exporter" / "kindle-web" / "content.js"
POPUP_JS = ROOT / "exporter" / "kindle-web" / "popup.js"
MANIFEST = ROOT / "exporter" / "kindle-web" / "manifest.json"


def test_content_js_tem_guarda_de_inicializacao_unica():
    src = CONTENT_JS.read_text(encoding="utf-8")
    assert "__BOOKKEEPER_CONTENT_READY__" in src
    assert "if (globalThis.__BOOKKEEPER_CONTENT_READY__)" in src
    # Flag é definida antes de registrar listeners
    idx_flag = src.find("globalThis.__BOOKKEEPER_CONTENT_READY__ = true")
    idx_window = src.find('window.addEventListener("message"')
    idx_runtime = src.find("chrome.runtime.onMessage.addListener")
    assert idx_flag > 0
    assert idx_window > idx_flag
    assert idx_runtime > idx_flag


def test_content_js_responde_ping():
    src = CONTENT_JS.read_text(encoding="utf-8")
    assert 'message.type === "PING"' in src
    assert "START_IMPORT" in src


def test_popup_faz_ping_antes_de_reinjetar():
    src = POPUP_JS.read_text(encoding="utf-8")
    assert "isContentScriptReady" in src
    assert 'type: "PING"' in src
    assert "ensureContentScript" in src
    # Ainda mantém contingência via executeScript
    assert "executeScript" in src
    assert 'files: ["content.js"]' in src or "files: ['content.js']" in src


def test_manifest_ainda_declara_content_js():
    import json

    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    scripts = data.get("content_scripts") or []
    arquivos = []
    for entry in scripts:
        arquivos.extend(entry.get("js") or [])
    assert "content.js" in arquivos
    assert "main.js" in arquivos


def test_guarda_simula_dupla_execucao_sem_duplicar_listeners():
    """Simula o padrão do content.js: segunda execução não registra de novo."""
    estado = {"ready": False, "listeners": 0}

    def carregar_script():
        if estado["ready"]:
            return
        estado["ready"] = True
        estado["listeners"] += 1  # equivalente a addEventListener / onMessage

    carregar_script()
    carregar_script()
    carregar_script()
    assert estado["listeners"] == 1
    assert estado["ready"] is True


def test_main_js_nao_foi_alterado_nesta_entrega():
    """Sanidade: main.js ainda contém o exportador Amazon (não reescrito)."""
    main = (ROOT / "exporter" / "kindle-web" / "main.js").read_text(encoding="utf-8")
    assert "requestTemplate" in main
    assert "GetContentOwnershipData" in main
    assert "captureRequest" in main
