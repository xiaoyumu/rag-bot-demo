const ingestBtn = document.getElementById("ingestBtn");
const publishBtn = document.getElementById("publishBtn");
const deleteDocBtn = document.getElementById("deleteDocBtn");
const viewDetailBtn = document.getElementById("viewDetailBtn");
const clearAllBtn = document.getElementById("clearAllBtn");
const refreshDocsBtn = document.getElementById("refreshDocsBtn");
const toggleDocsRawBtn = document.getElementById("toggleDocsRawBtn");
const chatBtn = document.getElementById("chatBtn");
const newSessionBtn = document.getElementById("newSessionBtn");
const fileInput = document.getElementById("fileInput");
const documentIdInput = document.getElementById("documentIdInput");
const questionInput = document.getElementById("questionInput");
const rewriteToggle = document.getElementById("rewriteToggle");
const rerankToggle = document.getElementById("rerankToggle");
const kbVersionSelect = document.getElementById("kbVersionSelect");
const deleteVersionSelect = document.getElementById("deleteVersionSelect");
const docsVersionFilter = document.getElementById("docsVersionFilter");
const ingestResult = document.getElementById("ingestResult");
const docsList = document.getElementById("docsList");
const docsResult = document.getElementById("docsResult");
const chatMessages = document.getElementById("chatMessages");
const chatRawBox = document.getElementById("chatRawBox");
const sessionBadge = document.getElementById("sessionBadge");
const toast = document.getElementById("toast");

const SESSION_KEY = "rag_bot_session_id";
let sessionId = initSessionId();
let latestDocumentItems = [];
let toastTimer = null;
let docsRawExpanded = false;

function formatJson(data) {
  return JSON.stringify(data, null, 2);
}

function showToast(message) {
  if (!toast) {
    return;
  }
  if (toastTimer) {
    clearTimeout(toastTimer);
  }
  toast.textContent = String(message || "");
  toast.classList.add("show");
  toastTimer = setTimeout(() => {
    toast.classList.remove("show");
    toastTimer = null;
  }, 2200);
}

function updateDocsRawVisibility() {
  if (!docsResult || !toggleDocsRawBtn) {
    return;
  }
  docsResult.classList.toggle("collapsed", !docsRawExpanded);
  toggleDocsRawBtn.textContent = docsRawExpanded ? "Hide Raw JSON" : "Show Raw JSON";
}

function initSessionId() {
  const saved = localStorage.getItem(SESSION_KEY);
  if (saved) {
    return saved;
  }
  const next = createSessionId();
  localStorage.setItem(SESSION_KEY, next);
  return next;
}

function createSessionId() {
  if (globalThis.crypto && typeof globalThis.crypto.randomUUID === "function") {
    return globalThis.crypto.randomUUID();
  }
  return `session-${Date.now()}-${Math.floor(Math.random() * 1_000_000)}`;
}

function updateSessionBadge() {
  sessionBadge.textContent = `Session: ${sessionId}`;
}

function appendMessage(role, content, options = {}) {
  const sources = Array.isArray(options.sources) ? options.sources : [];
  const rewrittenQuery = typeof options.rewrittenQuery === "string" ? options.rewrittenQuery.trim() : "";
  const wrapper = document.createElement("div");
  wrapper.className = `message ${role}`;

  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.textContent = content || "(empty)";
  wrapper.appendChild(bubble);

  if (role === "assistant" && rewrittenQuery) {
    const rewrittenNode = document.createElement("div");
    rewrittenNode.className = "rewrite-meta";
    rewrittenNode.textContent = `改写问题: ${rewrittenQuery}`;
    wrapper.appendChild(rewrittenNode);
  }

  if (role === "assistant" && sources.length > 0) {
    wrapper.appendChild(renderSources(sources));
  }

  chatMessages.appendChild(wrapper);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

function renderSources(sources) {
  const container = document.createElement("div");
  container.className = "citations";

  sources.forEach((source, idx) => {
    const item = document.createElement("details");
    item.className = "citation-item";

    const index = typeof source.chunk_index === "number" ? source.chunk_index : -1;
    const total = Number(source.total_chunks || 0);
    const location = index >= 0 && total > 0 ? `chunk ${index + 1}/${total}` : "chunk n/a";
    const score = typeof source.score === "number" ? source.score.toFixed(4) : "n/a";
    const sourcePath = String(source.source || "unknown");
    const sourceName = sourcePath.split(/[\\/]/).pop() || sourcePath;
    const snippet = String(source.text || "").trim();

    const meta = document.createElement("summary");
    meta.className = "citation-meta";
    meta.textContent = `[${idx + 1}] ${sourceName} | ${location} | score=${score}`;
    item.appendChild(meta);

    const detailBody = document.createElement("div");
    detailBody.className = "citation-detail";
    const sourceLine = document.createElement("div");
    sourceLine.textContent = `source: ${sourcePath}`;
    detailBody.appendChild(sourceLine);
    if (source.document_id) {
      const docLine = document.createElement("div");
      docLine.textContent = `document_id: ${source.document_id}`;
      detailBody.appendChild(docLine);
    }
    if (snippet) {
      const snippetNode = document.createElement("div");
      snippetNode.className = "citation-snippet";
      snippetNode.textContent = snippet;
      detailBody.appendChild(snippetNode);
    }
    item.appendChild(detailBody);

    container.appendChild(item);
  });

  return container;
}

async function ingestFiles() {
  const files = fileInput.files;
  if (!files || files.length === 0) {
    ingestResult.textContent = "Please select at least one file.";
    return;
  }

  ingestBtn.disabled = true;
  ingestResult.textContent = "Uploading...";
  try {
    const formData = new FormData();
    const documentId = documentIdInput.value.trim();
    if (documentId) {
      formData.append("document_id", documentId);
    }
    for (const file of files) {
      formData.append("files", file);
    }

    const response = await fetch("/api/ingest/files", {
      method: "POST",
      body: formData,
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || "Ingest request failed.");
    }
    ingestResult.textContent = formatJson(payload);
    showToast("Upload to draft success.");
  } catch (error) {
    ingestResult.textContent = String(error);
    showToast(error);
  } finally {
    ingestBtn.disabled = false;
  }
  await refreshDocuments();
}

async function publishDocumentById(documentId) {
  if (!documentId) {
    ingestResult.textContent = "Please input document_id first.";
    return;
  }
  publishBtn.disabled = true;
  ingestResult.textContent = "Publishing...";
  try {
    const response = await fetch(`/api/ingest/documents/${encodeURIComponent(documentId)}/publish`, {
      method: "POST",
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || "Publish request failed.");
    }
    ingestResult.textContent = formatJson(payload);
    showToast(`Published: ${documentId}`);
  } catch (error) {
    ingestResult.textContent = String(error);
    showToast(error);
  } finally {
    publishBtn.disabled = false;
  }
  await refreshDocuments();
}

async function publishDocument() {
  const documentId = documentIdInput.value.trim();
  await publishDocumentById(documentId);
}

async function refreshDocuments() {
  refreshDocsBtn.disabled = true;
  docsResult.textContent = "Loading documents...";
  docsList.innerHTML = "";
  try {
    const version = docsVersionFilter.value;
    const query = version ? `?kb_version=${encodeURIComponent(version)}` : "";
    const response = await fetch(`/api/ingest/documents${query}`, {
      method: "GET",
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || "List documents failed.");
    }
    latestDocumentItems = Array.isArray(payload.items) ? payload.items : [];
    renderDocumentList(latestDocumentItems);
    docsResult.textContent = formatJson(payload);
  } catch (error) {
    latestDocumentItems = [];
    docsResult.textContent = String(error);
    showToast(error);
  } finally {
    refreshDocsBtn.disabled = false;
  }
}

function renderDocumentList(items) {
  docsList.innerHTML = "";
  if (!items || items.length === 0) {
    const empty = document.createElement("div");
    empty.className = "doc-item-meta";
    empty.textContent = "No documents found.";
    docsList.appendChild(empty);
    return;
  }

  items.forEach((item) => {
    const card = document.createElement("div");
    card.className = "doc-item";

    const title = document.createElement("div");
    title.className = "doc-item-title";
    title.textContent = item.document_id || "(missing document_id)";
    card.appendChild(title);

    const meta = document.createElement("div");
    meta.className = "doc-item-meta";
    meta.textContent = `${item.kb_version || "n/a"} | chunks=${item.chunks || 0} | ${item.source || "unknown"}`;
    card.appendChild(meta);

    const actions = document.createElement("div");
    actions.className = "doc-actions";

    const useBtn = document.createElement("button");
    useBtn.type = "button";
    useBtn.textContent = "Use";
    useBtn.addEventListener("click", () => {
      documentIdInput.value = item.document_id || "";
      kbVersionSelect.value = item.kb_version || "publish";
      deleteVersionSelect.value = item.kb_version || "all";
      ingestResult.textContent = `Selected document: ${item.document_id} (${item.kb_version})`;
      showToast(`Selected: ${item.document_id}`);
    });
    actions.appendChild(useBtn);

    const detailBtn = document.createElement("button");
    detailBtn.type = "button";
    detailBtn.textContent = "Detail";
    detailBtn.addEventListener("click", async () => {
      documentIdInput.value = item.document_id || "";
      kbVersionSelect.value = item.kb_version || "publish";
      await viewDocumentDetail();
    });
    actions.appendChild(detailBtn);

    const publishInlineBtn = document.createElement("button");
    publishInlineBtn.type = "button";
    publishInlineBtn.textContent = "Publish";
    publishInlineBtn.addEventListener("click", async () => {
      documentIdInput.value = item.document_id || "";
      await publishDocumentById(item.document_id || "");
    });
    actions.appendChild(publishInlineBtn);

    const deleteInlineBtn = document.createElement("button");
    deleteInlineBtn.type = "button";
    deleteInlineBtn.textContent = "Delete";
    deleteInlineBtn.addEventListener("click", async () => {
      documentIdInput.value = item.document_id || "";
      const deleteVersion = item.kb_version || "all";
      deleteVersionSelect.value = deleteVersion;
      await deleteDocumentById(item.document_id || "", deleteVersion);
    });
    actions.appendChild(deleteInlineBtn);

    const copyIdBtn = document.createElement("button");
    copyIdBtn.type = "button";
    copyIdBtn.textContent = "Copy ID";
    copyIdBtn.addEventListener("click", async () => {
      const id = item.document_id || "";
      if (!id) {
        showToast("No document_id to copy.");
        return;
      }
      try {
        await globalThis.navigator.clipboard.writeText(id);
        showToast(`Copied: ${id}`);
      } catch (_error) {
        documentIdInput.value = id;
        showToast("Clipboard unavailable, filled into input.");
      }
    });
    actions.appendChild(copyIdBtn);

    card.appendChild(actions);
    docsList.appendChild(card);
  });
}

async function deleteDocumentById(documentId, deleteVersion) {
  if (!documentId) {
    ingestResult.textContent = "Please input document_id first.";
    return;
  }
  const confirmed = globalThis.confirm(`Delete document ${documentId} (${deleteVersion})?`);
  if (!confirmed) {
    return;
  }
  deleteDocBtn.disabled = true;
  ingestResult.textContent = "Deleting...";
  try {
    const response = await fetch(
      `/api/ingest/documents/${encodeURIComponent(documentId)}?kb_version=${encodeURIComponent(deleteVersion)}`,
      { method: "DELETE" }
    );
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || "Delete document failed.");
    }
    ingestResult.textContent = formatJson(payload);
    showToast(`Deleted: ${documentId} (${deleteVersion})`);
  } catch (error) {
    ingestResult.textContent = String(error);
    showToast(error);
  } finally {
    deleteDocBtn.disabled = false;
  }
  await refreshDocuments();
}

async function deleteDocument() {
  const documentId = documentIdInput.value.trim();
  const deleteVersion = deleteVersionSelect.value;
  await deleteDocumentById(documentId, deleteVersion);
}

async function clearAllKnowledgeBase() {
  const confirmed = globalThis.confirm("This will permanently delete ALL knowledge base chunks in Weaviate and MongoDB. Continue?");
  if (!confirmed) {
    return;
  }
  const phrase = globalThis.prompt('Type "CLEAR ALL" to confirm clearing all knowledge base data:', "");
  if (phrase !== "CLEAR ALL") {
    showToast('Cancelled. You must type "CLEAR ALL".');
    return;
  }
  clearAllBtn.disabled = true;
  ingestResult.textContent = "Clearing all knowledge base data...";
  try {
    const response = await fetch("/api/ingest/documents?confirm_text=CLEAR%20ALL", { method: "DELETE" });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || "Clear knowledge base failed.");
    }
    ingestResult.textContent = formatJson(payload);
    showToast("Cleared all knowledge base data.");
  } catch (error) {
    ingestResult.textContent = String(error);
    showToast(error);
  } finally {
    clearAllBtn.disabled = false;
  }
  await refreshDocuments();
}

async function viewDocumentDetail() {
  const documentId = documentIdInput.value.trim();
  if (!documentId) {
    ingestResult.textContent = "Please input document_id first.";
    return;
  }
  const version = kbVersionSelect.value;
  viewDetailBtn.disabled = true;
  ingestResult.textContent = "Loading detail...";
  try {
    const response = await fetch(
      `/api/ingest/documents/${encodeURIComponent(documentId)}?kb_version=${encodeURIComponent(version)}`
    );
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || "Get document detail failed.");
    }
    ingestResult.textContent = formatJson(payload);
    showToast(`Loaded detail: ${documentId} (${version})`);
  } catch (error) {
    ingestResult.textContent = String(error);
    showToast(error);
  } finally {
    viewDetailBtn.disabled = false;
  }
}

async function askQuestion() {
  const question = questionInput.value.trim();
  if (!question) {
    return;
  }

  appendMessage("user", question);
  questionInput.value = "";
  chatBtn.disabled = true;
  const pendingText = "Thinking...";
  appendMessage("assistant", pendingText);
  chatRawBox.textContent = "Loading raw response...";

  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question,
        session_id: sessionId,
        enable_rewrite: rewriteToggle.checked,
        enable_rerank: rerankToggle.checked,
        kb_version: kbVersionSelect.value,
      }),
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || "Chat request failed.");
    }

    if (payload.session_id && payload.session_id !== sessionId) {
      sessionId = payload.session_id;
      localStorage.setItem(SESSION_KEY, sessionId);
      updateSessionBadge();
    }

    chatMessages.removeChild(chatMessages.lastElementChild);
    appendMessage("assistant", payload.answer || "(empty answer)", {
      sources: payload.sources || [],
      rewrittenQuery: payload.rewritten_query || "",
    });
    chatRawBox.textContent = formatJson(payload);
  } catch (error) {
    chatMessages.removeChild(chatMessages.lastElementChild);
    appendMessage("assistant", String(error));
    chatRawBox.textContent = "{}";
  } finally {
    chatBtn.disabled = false;
  }
}

function resetSession() {
  sessionId = createSessionId();
  localStorage.setItem(SESSION_KEY, sessionId);
  updateSessionBadge();
  chatMessages.innerHTML = "";
  appendMessage("assistant", "已创建新会话，请继续提问。");
  chatRawBox.textContent = "No response yet.";
}

ingestBtn.addEventListener("click", ingestFiles);
publishBtn.addEventListener("click", publishDocument);
deleteDocBtn.addEventListener("click", deleteDocument);
viewDetailBtn.addEventListener("click", viewDocumentDetail);
clearAllBtn.addEventListener("click", clearAllKnowledgeBase);
refreshDocsBtn.addEventListener("click", refreshDocuments);
docsVersionFilter.addEventListener("change", refreshDocuments);
toggleDocsRawBtn.addEventListener("click", () => {
  docsRawExpanded = !docsRawExpanded;
  updateDocsRawVisibility();
});
chatBtn.addEventListener("click", askQuestion);
newSessionBtn.addEventListener("click", resetSession);
questionInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    askQuestion();
  }
});
updateSessionBadge();
updateDocsRawVisibility();
refreshDocuments();
