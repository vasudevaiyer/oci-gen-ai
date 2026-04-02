const SESSION_STORAGE_KEY = "rag_workspace_chat_history_v1";

const DEFAULT_EVIDENCE_SUMMARY_ITEMS = [
  "Primary evidence will appear here after the first answer.",
  "Only the most relevant supporting sources stay visible.",
  "Relevant image matches are called out when they improve grounding.",
];

const state = {
  recentQueries: [],
  chatHistory: [],
};

const elements = {
  documentsCount: document.getElementById("documentsCount"),
  chunksCount: document.getElementById("chunksCount"),
  imagesCount: document.getElementById("imagesCount"),
  embeddingModel: document.getElementById("embeddingModel"),
  chatModel: document.getElementById("chatModel"),
  visionModel: document.getElementById("visionModel"),
  indexStatusPill: document.getElementById("indexStatusPill"),
  indexedCountPill: document.getElementById("indexedCountPill"),
  evidenceSummaryList: document.getElementById("evidenceSummaryList"),
  recentQueries: document.getElementById("recentQueries"),
  assistantOutput: document.getElementById("assistantOutput"),
  toast: document.getElementById("toast"),
  imageModal: document.getElementById("imageModal"),
  modalImage: document.getElementById("modalImage"),
  modalCaption: document.getElementById("modalCaption"),
  chatForm: document.getElementById("chatForm"),
  clearChatButton: document.getElementById("clearChat"),
};

function showToast(message, isError = false) {
  if (!elements.toast) {
    return;
  }
  elements.toast.textContent = message;
  elements.toast.classList.remove("hidden");
  elements.toast.style.borderColor = isError ? "rgba(184, 77, 25, 0.42)" : "rgba(20, 119, 137, 0.3)";
  window.clearTimeout(showToast._timer);
  showToast._timer = window.setTimeout(() => elements.toast.classList.add("hidden"), 3200);
}

async function api(url, options = {}) {
  const response = await fetch(url, options);
  const contentType = response.headers.get("content-type") || "";
  const data = contentType.includes("application/json") ? await response.json() : await response.text();
  if (!response.ok) {
    const detail = typeof data === "object" && data?.detail ? data.detail : response.statusText;
    throw new Error(detail || "Request failed");
  }
  return data;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function escapeHtmlAttr(value) {
  return escapeHtml(value).replaceAll("\n", " ");
}

function renderStatus(status) {
  if (elements.documentsCount) elements.documentsCount.textContent = status.documents;
  if (elements.chunksCount) elements.chunksCount.textContent = status.chunks;
  if (elements.imagesCount) elements.imagesCount.textContent = status.images;
  if (elements.embeddingModel) elements.embeddingModel.textContent = status.models?.embedding || "n/a";
  if (elements.chatModel) elements.chatModel.textContent = status.models?.chat || "n/a";
  if (elements.visionModel) elements.visionModel.textContent = status.models?.vision || "n/a";
  if (elements.indexStatusPill) {
    const ready = Number(status.chunks) > 0;
    elements.indexStatusPill.textContent = ready ? "Indexed" : "No index";
    elements.indexStatusPill.classList.toggle("ready", ready);
    elements.indexStatusPill.classList.toggle("empty", !ready);
  }
  if (elements.indexedCountPill) {
    const indexedDocuments = Number(status.indexed_documents || 0);
    elements.indexedCountPill.textContent = `${indexedDocuments} indexed doc${indexedDocuments === 1 ? "" : "s"}`;
  }
}

function loadSessionState() {
  try {
    const raw = window.sessionStorage.getItem(SESSION_STORAGE_KEY);
    if (!raw) {
      return;
    }
    const parsed = JSON.parse(raw);
    state.recentQueries = Array.isArray(parsed.recentQueries) ? parsed.recentQueries : [];
    state.chatHistory = Array.isArray(parsed.chatHistory) ? parsed.chatHistory : [];
  } catch (error) {
    console.warn("Failed to restore chat history", error);
  }
}

function persistSessionState() {
  try {
    window.sessionStorage.setItem(
      SESSION_STORAGE_KEY,
      JSON.stringify({
        recentQueries: state.recentQueries,
        chatHistory: state.chatHistory,
      }),
    );
  } catch (error) {
    console.warn("Failed to persist chat history", error);
  }
}

function renderRecentQueries() {
  if (!elements.recentQueries) {
    return;
  }
  if (!state.recentQueries.length) {
    elements.recentQueries.innerHTML = '<div class="empty-state">No questions yet in this session.</div>';
    return;
  }
  elements.recentQueries.innerHTML = state.recentQueries
    .map(
      (item) => `
        <button class="pipeline-recent-item" type="button" data-history-id="${escapeHtmlAttr(item.id)}">
          <strong>${escapeHtml(item.question)}</strong>
          <span>${escapeHtml(item.summary)}</span>
        </button>
      `,
    )
    .join("");
}

function renderEvidenceSummary(payload) {
  if (!elements.evidenceSummaryList) {
    return;
  }
  const items = [];
  if (payload.sources?.length) {
    const primary = payload.sources[0];
    items.push(`Primary source: ${primary.title} (${primary.source_path.split("/").pop()})`);
    items.push(`${payload.sources.length} supporting source(s) returned for grounding.`);
  } else {
    items.push("No supporting text sources were returned for this answer.");
  }
  if (payload.matched_images?.length) {
    items.push(`${payload.matched_images.length} relevant image match(es) were included.`);
  } else {
    items.push("No relevant image evidence was needed for this answer.");
  }
  elements.evidenceSummaryList.innerHTML = items.map((item) => `<li>${escapeHtml(item)}</li>`).join("");
}

function renderDefaultEvidenceSummary() {
  if (!elements.evidenceSummaryList) {
    return;
  }
  elements.evidenceSummaryList.innerHTML = DEFAULT_EVIDENCE_SUMMARY_ITEMS.map((item) => `<li>${escapeHtml(item)}</li>`).join("");
}

function syncClearChatButton() {
  if (!elements.clearChatButton) {
    return;
  }
  elements.clearChatButton.disabled = !state.chatHistory.length && !state.recentQueries.length;
}

function recordRecentQuery(entry) {
  const sourceCount = entry.payload.sources?.length || 0;
  const imageCount = entry.payload.matched_images?.length || 0;
  const summary = imageCount ? `${sourceCount} src · ${imageCount} img` : `${sourceCount} src`;
  state.recentQueries = [
    { id: entry.id, question: entry.question, summary },
    ...state.recentQueries.filter((item) => item.question !== entry.question),
  ].slice(0, 8);
  renderRecentQueries();
  syncClearChatButton();
}

function renderMatchedImages(images) {
  if (!images.length) {
    return "";
  }
  return `
    <div class="vision-grid">
      ${images
        .map((image) => {
          const modalCaption = [image.caption_text || "Image match", image.section_path, image.source_path]
            .filter(Boolean)
            .join(" · ");
          return `
            <article class="vision-card">
              <button type="button" class="vision-card-trigger" data-image-url="${image.image_url}" data-caption="${escapeHtmlAttr(modalCaption)}">
                <img src="${image.image_url}" alt="Matched image" />
              </button>
              <div>
                <strong>${escapeHtml(image.section_path || "Matched image")}</strong>
                <p>${escapeHtml(image.caption_text || "Relevant visual context")}</p>
                <small>${escapeHtml(image.source_path || "")}</small>
              </div>
            </article>
          `;
        })
        .join("")}
    </div>
  `;
}

function renderSupportingSources(sources) {
  if (!sources.length) {
    return '<div class="empty-state">No supporting text sources returned.</div>';
  }
  return `
    <div class="source-grid">
      ${sources
        .map(
          (source, index) => `
            <article class="source-card">
              <div class="message-meta">
                <span>Evidence ${index + 1}</span>
                <small>${escapeHtml(source.chunk_type.replaceAll("_", " "))} · ${source.score.toFixed(3)}</small>
              </div>
              <strong>${escapeHtml(source.title)}</strong>
              <span>${escapeHtml(source.section_path)}</span>
              <small>${escapeHtml(source.source_path)}</small>
              <p class="plain-message">${escapeHtml(source.excerpt)}</p>
              ${
                source.image_urls?.length
                  ? `
                    <div class="thumb-row">
                      ${source.image_urls
                        .slice(0, 3)
                        .map(
                          (imageUrl) => `
                            <button type="button" class="thumb-button" data-image-url="${imageUrl}" data-caption="${escapeHtmlAttr(source.title)}">
                              <img src="${imageUrl}" alt="" />
                            </button>
                          `,
                        )
                        .join("")}
                    </div>
                  `
                  : ""
              }
            </article>
          `,
        )
        .join("")}
    </div>
  `;
}

function renderSupportingSourcesSection(sources) {
  const label = sources.length ? `Supporting Sources (${sources.length})` : "Supporting Sources";
  return `
    <details class="assistant-disclosure">
      <summary class="assistant-disclosure-summary">
        <span>${label}</span>
        <span class="assistant-disclosure-hint">Expand</span>
      </summary>
      <div class="assistant-disclosure-body">
        ${renderSupportingSources(sources)}
      </div>
    </details>
  `;
}

function renderEmptyHistory() {
  return `
    <article class="message assistant intro-message">
      <div class="message-meta">
        <span>Oracle RAG</span>
        <small>Ready</small>
      </div>
      <p class="plain-message">Start with a question. Grounded answers, supporting sources, and relevant image context will appear here.</p>
    </article>
  `;
}

function renderThread(entry) {
  return `
    <article class="message user" id="history-${escapeHtmlAttr(entry.id)}">
      <div class="message-meta">
        <span>You</span>
        <small>Question</small>
      </div>
      <p class="plain-message">${escapeHtml(entry.question)}</p>
    </article>

    <article class="message assistant">
      <div class="message-meta">
        <span>Oracle RAG</span>
        <small>${escapeHtml(entry.payload.model || "Grounded answer")}</small>
      </div>
      <div class="answer-text plain-message">${escapeHtml(entry.payload.answer)}</div>
      ${renderSupportingSourcesSection(entry.payload.sources || [])}
      ${
        (entry.payload.matched_images || []).length
          ? `
            <div class="message-section">
              <p class="eyebrow">Visual support</p>
              <h3 class="message-section-title">Matched Images</h3>
              ${renderMatchedImages(entry.payload.matched_images || [])}
            </div>
          `
          : ""
      }
    </article>
  `;
}

function renderHistory() {
  if (!elements.assistantOutput) {
    return;
  }
  if (!state.chatHistory.length) {
    elements.assistantOutput.innerHTML = renderEmptyHistory();
    syncClearChatButton();
    return;
  }
  elements.assistantOutput.innerHTML = state.chatHistory.map((entry) => renderThread(entry)).join("");
  syncClearChatButton();
}

function appendChatResult(payload, question) {
  const entry = {
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    question,
    payload,
  };
  state.chatHistory.push(entry);
  renderHistory();
  renderEvidenceSummary(payload);
  recordRecentQuery(entry);
  persistSessionState();
  const anchor = document.getElementById(`history-${entry.id}`);
  if (anchor) {
    anchor.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

function clearChatHistory() {
  if (!state.chatHistory.length && !state.recentQueries.length) {
    showToast("Chat is already clear.");
    return;
  }
  state.chatHistory = [];
  state.recentQueries = [];
  try {
    window.sessionStorage.removeItem(SESSION_STORAGE_KEY);
  } catch (error) {
    console.warn("Failed to clear chat history", error);
  }
  removePendingState();
  renderHistory();
  renderRecentQueries();
  renderDefaultEvidenceSummary();
  closeImageModal();
  showToast("Chat cleared.");
}

async function refreshWorkspace() {
  renderStatus(await api("/api/status"));
}

function openImageModal(url, caption) {
  if (!elements.imageModal) {
    return;
  }
  elements.modalImage.src = url;
  elements.modalCaption.textContent = caption || "Image preview";
  elements.imageModal.classList.remove("hidden");
}

function closeImageModal() {
  if (!elements.imageModal) {
    return;
  }
  elements.imageModal.classList.add("hidden");
  elements.modalImage.src = "";
}

function scrollToHistoryItem(id) {
  const anchor = document.getElementById(`history-${id}`);
  if (anchor) {
    anchor.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

function renderPendingState() {
  if (!elements.assistantOutput) {
    return;
  }
  removePendingState();
  elements.assistantOutput.insertAdjacentHTML(
    "beforeend",
    `
      <article class="message user pending-user-message" id="pendingQuestion">
        <div class="message-meta">
          <span>You</span>
          <small>Question</small>
        </div>
        <p class="plain-message">${escapeHtml(renderPendingState._question || "")}</p>
      </article>
      <article class="message assistant pending-message" id="pendingAnswer">
        <div class="message-meta">
          <span>Oracle RAG</span>
          <small>Working</small>
        </div>
        <p class="plain-message">Generating grounded answer...</p>
      </article>
    `,
  );
}

function removePendingState() {
  document.getElementById("pendingQuestion")?.remove();
  document.getElementById("pendingAnswer")?.remove();
}

function submitStarterQuestion(question) {
  const questionField = document.getElementById("chatQuestion");
  if (!questionField || !elements.chatForm || !question) {
    return;
  }
  questionField.value = question;
  elements.chatForm.requestSubmit();
}

const refreshButton = document.getElementById("refreshAll");
if (refreshButton) {
  refreshButton.addEventListener("click", () => refreshWorkspace().catch(handleError));
}

if (elements.clearChatButton) {
  elements.clearChatButton.addEventListener("click", clearChatHistory);
}

if (elements.chatForm) {
  elements.chatForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const questionField = document.getElementById("chatQuestion");
    const question = questionField.value.trim();
    if (!question) {
      showToast("Enter a question for chat.", true);
      return;
    }
    questionField.value = "";
    renderPendingState._question = question;
    renderPendingState();
    try {
      const result = await api("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question,
          top_k: Number(document.getElementById("chatTopK").value || 4),
          include_images: document.getElementById("chatIncludeImages").checked,
        }),
      });
      removePendingState();
      appendChatResult(result, question);
    } catch (error) {
      removePendingState();
      handleError(error);
      elements.assistantOutput.insertAdjacentHTML("beforeend", '<div class="empty-state">Chat failed.</div>');
    }
  });
}

document.body.addEventListener("click", (event) => {
  const trigger = event.target.closest("button[data-image-url]");
  if (trigger) {
    openImageModal(trigger.dataset.imageUrl, trigger.dataset.caption || "Image preview");
    return;
  }

  const historyButton = event.target.closest("button[data-history-id]");
  if (historyButton) {
    scrollToHistoryItem(historyButton.dataset.historyId);
    return;
  }

  const starterButton = event.target.closest("button[data-starter-question]");
  if (starterButton) {
    submitStarterQuestion(starterButton.dataset.starterQuestion || "");
  }
});

const closeImageModalButton = document.getElementById("closeImageModal");
if (closeImageModalButton) {
  closeImageModalButton.addEventListener("click", closeImageModal);
}

if (elements.imageModal) {
  elements.imageModal.addEventListener("click", (event) => {
    if (event.target === elements.imageModal) {
      closeImageModal();
    }
  });
}

function handleError(error) {
  console.error(error);
  showToast(error.message || "Something went wrong.", true);
}

loadSessionState();
renderRecentQueries();
renderHistory();
if (state.chatHistory.length) {
  renderEvidenceSummary(state.chatHistory[state.chatHistory.length - 1].payload);
} else {
  renderDefaultEvidenceSummary();
}
refreshWorkspace().catch(handleError);
