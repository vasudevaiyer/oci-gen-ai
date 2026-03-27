const SESSION_STORAGE_KEY = "rag_workspace_chat_history_v1";

const state = {
  recentQueries: [],
  chatHistory: [],
};

const DEFAULT_EVIDENCE_SUMMARY_ITEMS = [
  'Primary evidence will appear here after the first answer.',
  'Only the most relevant supporting sources stay visible.',
  'The right rail stays lightweight and avoids document-browsing clutter.',
];

const elements = {
  documentsCount: document.getElementById('documentsCount'),
  chunksCount: document.getElementById('chunksCount'),
  imagesCount: document.getElementById('imagesCount'),
  evidenceSummaryList: document.getElementById('evidenceSummaryList'),
  recentQueries: document.getElementById('recentQueries'),
  assistantOutput: document.getElementById('assistantOutput'),
  toast: document.getElementById('toast'),
  imageModal: document.getElementById('imageModal'),
  modalImage: document.getElementById('modalImage'),
  modalCaption: document.getElementById('modalCaption'),
  chatForm: document.getElementById('chatForm'),
  clearChatButton: document.getElementById('clearChat'),
};

function showToast(message, isError = false) {
  if (!elements.toast) {
    return;
  }
  elements.toast.textContent = message;
  elements.toast.classList.remove('hidden');
  elements.toast.style.borderColor = isError ? 'rgba(239, 109, 103, 0.45)' : 'rgba(89, 209, 197, 0.35)';
  window.clearTimeout(showToast._timer);
  showToast._timer = window.setTimeout(() => elements.toast.classList.add('hidden'), 3200);
}

async function api(url, options = {}) {
  const response = await fetch(url, options);
  const contentType = response.headers.get('content-type') || '';
  const data = contentType.includes('application/json') ? await response.json() : await response.text();
  if (!response.ok) {
    const detail = typeof data === 'object' && data?.detail ? data.detail : response.statusText;
    throw new Error(detail || 'Request failed');
  }
  return data;
}

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function escapeHtmlAttr(value) {
  return escapeHtml(value).replaceAll('\n', ' ');
}

function renderStatus(status) {
  if (elements.documentsCount) elements.documentsCount.textContent = status.documents;
  if (elements.chunksCount) elements.chunksCount.textContent = status.chunks;
  if (elements.imagesCount) elements.imagesCount.textContent = status.images;
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
    console.warn('Failed to restore chat history', error);
  }
}

function persistSessionState() {
  try {
    window.sessionStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify({
      recentQueries: state.recentQueries,
      chatHistory: state.chatHistory,
    }));
  } catch (error) {
    console.warn('Failed to persist chat history', error);
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
  elements.recentQueries.innerHTML = state.recentQueries.map((item) => `
    <button class="mockup-history-row mockup-history-button" type="button" data-history-id="${escapeHtmlAttr(item.id)}">
      <p>${escapeHtml(item.question)}</p>
      <span>${escapeHtml(item.summary)}</span>
    </button>
  `).join('');
}

function renderEvidenceSummary(payload) {
  if (!elements.evidenceSummaryList) {
    return;
  }
  const items = [];
  if (payload.sources?.length) {
    const primary = payload.sources[0];
    items.push(`Primary source: ${primary.title} (${primary.source_path.split('/').pop()})`);
    items.push(`${payload.sources.length} supporting source(s) returned for grounding.`);
  } else {
    items.push('No supporting text sources were returned for this answer.');
  }
  if (payload.matched_images?.length) {
    items.push(`${payload.matched_images.length} relevant image match(es) were included.`);
  } else {
    items.push('No relevant image evidence was needed for this answer.');
  }
  elements.evidenceSummaryList.innerHTML = items.map((item) => `<li>${escapeHtml(item)}</li>`).join('');
}

function renderDefaultEvidenceSummary() {
  if (!elements.evidenceSummaryList) {
    return;
  }
  elements.evidenceSummaryList.innerHTML = DEFAULT_EVIDENCE_SUMMARY_ITEMS
    .map((item) => `<li>${escapeHtml(item)}</li>`)
    .join('');
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
  state.recentQueries = [{ id: entry.id, question: entry.question, summary }, ...state.recentQueries.filter((item) => item.question !== entry.question)].slice(0, 8);
  renderRecentQueries();
  syncClearChatButton();
}

function renderMatchedImages(images) {
  if (!images.length) {
    return '';
  }
  return `
    <section class="assistant-subsection">
      <div class="section-heading"><div><p class="eyebrow">Visual Support</p><h3>Matched Images</h3></div></div>
      <div class="image-result-grid">
        ${images.map((image) => {
          const modalCaption = [image.caption_text || 'Image match', image.section_path, image.source_path]
            .filter(Boolean)
            .join(' · ');
          return `
          <article class="image-card">
            <button type="button" data-image-url="${image.image_url}" data-caption="${escapeHtmlAttr(modalCaption)}">
              <img src="${image.image_url}" alt="Matched image" />
            </button>
          </article>
        `;
        }).join('')}
      </div>
    </section>`;
}

function renderSupportingSources(sources) {
  if (!sources.length) {
    return '<div class="empty-state">No supporting text sources returned.</div>';
  }
  return sources.map((source, index) => `
    <article class="assistant-card">
      <div class="assistant-card-head">
        <span class="assistant-label">Evidence ${index + 1}</span>
        <span class="result-score">${source.chunk_type.replaceAll('_', ' ')} · ${source.score.toFixed(3)}</span>
      </div>
      <h3>${escapeHtml(source.title)}</h3>
      <div class="result-meta">${escapeHtml(source.section_path)} · ${escapeHtml(source.source_path)}</div>
      <p class="result-excerpt">${escapeHtml(source.excerpt)}</p>
    </article>
  `).join('');
}

function renderSupportingSourcesSection(sources) {
  const label = sources.length ? `Supporting Sources (${sources.length})` : 'Supporting Sources';
  return `
    <details class="assistant-disclosure">
      <summary class="assistant-disclosure-summary">
        <span>${label}</span>
        <span class="assistant-disclosure-hint">Expand</span>
      </summary>
      <div class="assistant-disclosure-body">
        <div class="assistant-stream">${renderSupportingSources(sources)}</div>
      </div>
    </details>
  `;
}

function renderHistory() {
  if (!elements.assistantOutput) {
    return;
  }
  if (!state.chatHistory.length) {
    elements.assistantOutput.innerHTML = `
      <article class="mockup-card mockup-answer-card">
        <div class="mockup-card-headline mockup-answer-headline">
          <h3>Answer</h3>
          <span class="mockup-confidence-pill">Ready</span>
        </div>
        <p>Start with a question. Grounded answers, supporting sources, and relevant image context will appear here.</p>
      </article>
    `;
    syncClearChatButton();
    return;
  }

  elements.assistantOutput.innerHTML = state.chatHistory.map((entry) => `
    <section class="assistant-thread-turn" id="history-${escapeHtmlAttr(entry.id)}">
      <article class="assistant-message assistant-message-user">
        <div class="assistant-bubble">${escapeHtml(entry.question)}</div>
      </article>
      <article class="assistant-message assistant-message-assistant">
        <div class="assistant-bubble assistant-bubble-answer">
          <div class="answer-text">${escapeHtml(entry.payload.answer)}</div>
        </div>
      </article>
      <section class="assistant-subsection">
        <div class="section-heading"><div><p class="eyebrow">Grounding</p><h3>Evidence</h3></div></div>
        ${renderSupportingSourcesSection(entry.payload.sources || [])}
      </section>
      ${renderMatchedImages(entry.payload.matched_images || [])}
    </section>
  `).join('');
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
    anchor.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
}

function clearChatHistory() {
  if (!state.chatHistory.length && !state.recentQueries.length) {
    showToast('Chat is already clear.');
    return;
  }
  state.chatHistory = [];
  state.recentQueries = [];
  try {
    window.sessionStorage.removeItem(SESSION_STORAGE_KEY);
  } catch (error) {
    console.warn('Failed to clear chat history', error);
  }
  renderHistory();
  renderRecentQueries();
  renderDefaultEvidenceSummary();
  closeImageModal();
  showToast('Chat cleared.');
}

async function refreshWorkspace() {
  renderStatus(await api('/api/status'));
}

function openImageModal(url, caption) {
  if (!elements.imageModal) {
    return;
  }
  elements.modalImage.src = url;
  elements.modalCaption.textContent = caption || 'Image preview';
  elements.imageModal.classList.remove('hidden');
}

function closeImageModal() {
  if (!elements.imageModal) {
    return;
  }
  elements.imageModal.classList.add('hidden');
  elements.modalImage.src = '';
}

function scrollToHistoryItem(id) {
  const anchor = document.getElementById(`history-${id}`);
  if (anchor) {
    anchor.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
}

const refreshButton = document.getElementById('refreshAll');
if (refreshButton) {
  refreshButton.addEventListener('click', () => refreshWorkspace().catch(handleError));
}

if (elements.clearChatButton) {
  elements.clearChatButton.addEventListener('click', clearChatHistory);
}

if (elements.chatForm) {
  elements.chatForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    const questionField = document.getElementById('chatQuestion');
    const question = questionField.value.trim();
    if (!question) {
      showToast('Enter a question for chat.', true);
      return;
    }
    questionField.value = '';
    elements.assistantOutput.insertAdjacentHTML('beforeend', '<div class="empty-state" id="pendingAnswer">Generating answer...</div>');
    try {
      const result = await api('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          question,
          top_k: Number(document.getElementById('chatTopK').value || 4),
          include_images: document.getElementById('chatIncludeImages').checked,
        }),
      });
      document.getElementById('pendingAnswer')?.remove();
      appendChatResult(result, question);
    } catch (error) {
      document.getElementById('pendingAnswer')?.remove();
      handleError(error);
      elements.assistantOutput.insertAdjacentHTML('beforeend', '<div class="empty-state">Chat failed.</div>');
    }
  });
}

document.body.addEventListener('click', (event) => {
  const trigger = event.target.closest('button[data-image-url]');
  if (trigger) {
    openImageModal(trigger.dataset.imageUrl, trigger.dataset.caption || 'Image preview');
    return;
  }
  const historyButton = event.target.closest('button[data-history-id]');
  if (historyButton) {
    scrollToHistoryItem(historyButton.dataset.historyId);
  }
});

const closeImageModalButton = document.getElementById('closeImageModal');
if (closeImageModalButton) {
  closeImageModalButton.addEventListener('click', closeImageModal);
}
if (elements.imageModal) {
  elements.imageModal.addEventListener('click', (event) => {
    if (event.target === elements.imageModal) {
      closeImageModal();
    }
  });
}

function handleError(error) {
  console.error(error);
  showToast(error.message || 'Something went wrong.', true);
}

loadSessionState();
renderRecentQueries();
renderHistory();
if (state.chatHistory.length) {
  const latest = state.chatHistory[state.chatHistory.length - 1];
  renderEvidenceSummary(latest.payload);
} else {
  renderDefaultEvidenceSummary();
}
refreshWorkspace().catch(handleError);
