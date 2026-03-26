const elements = {
  documentsCount: document.getElementById('documentsCount'),
  chunksCount: document.getElementById('chunksCount'),
  imagesCount: document.getElementById('imagesCount'),
  indexedCount: document.getElementById('indexedCount'),
  documentTable: document.getElementById('documentTable'),
  documentCountBadge: document.getElementById('documentCountBadge'),
  fileInput: document.getElementById('fileInput'),
  uploadSelection: document.getElementById('uploadSelection'),
  uploadStatus: document.getElementById('uploadStatus'),
  uploadButton: document.getElementById('uploadButton'),
  toast: document.getElementById('toast'),
  governanceStatusBadge: document.getElementById('governanceStatusBadge'),
};

function showToast(message, isError = false) {
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

function renderSelectedFiles(files) {
  if (!files.length) {
    elements.uploadSelection.className = 'upload-selection empty-state';
    elements.uploadSelection.textContent = 'No files selected yet.';
    return;
  }

  const fileMarkup = files
    .map((file) => `<span class="upload-file-chip">${escapeHtml(file.name)}</span>`)
    .join('');
  const label = files.length === 1 ? '1 file selected' : `${files.length} files selected`;
  elements.uploadSelection.className = 'upload-selection';
  elements.uploadSelection.innerHTML = `<div class="upload-selection-label">${label}</div><div class="upload-file-list">${fileMarkup}</div>`;
}

function setUploadState(isUploading, message = '', isError = false) {
  elements.uploadButton.disabled = isUploading;
  elements.uploadButton.textContent = isUploading ? 'Uploading and Indexing...' : 'Upload and Index';
  elements.uploadStatus.textContent = message;
  elements.uploadStatus.classList.toggle('is-active', Boolean(message));
  elements.uploadStatus.classList.toggle('is-error', Boolean(message) && isError);
  if (elements.governanceStatusBadge) {
    elements.governanceStatusBadge.textContent = isUploading ? 'Running' : (message ? (isError ? 'Attention' : 'Ready') : 'Ready');
  }
}

function renderStatus(status) {
  elements.documentsCount.textContent = status.documents;
  elements.chunksCount.textContent = status.chunks;
  elements.imagesCount.textContent = status.images;
  elements.indexedCount.textContent = status.indexed_documents;
}

function renderDocuments(documents) {
  elements.documentCountBadge.textContent = `${documents.length} records`;
  if (!documents.length) {
    elements.documentTable.innerHTML = '<div class="empty-state">No indexed documents yet. Upload files or import a folder to start building the corpus.</div>';
    return;
  }
  elements.documentTable.innerHTML = documents.map((doc) => {
    const languages = (doc.language_tags || []).join(', ') || 'unknown';
    const parser = doc.metadata?.parser_used || 'n/a';
    return `
      <article class="document-row">
        <div class="document-main">
          <div class="doc-stat">${doc.file_type.toUpperCase()} · ${languages} · ${parser}</div>
          <h4>${escapeHtml(doc.title || doc.file_name)}</h4>
          <div class="document-meta">${escapeHtml(doc.file_name)}</div>
          <div class="document-path">${escapeHtml(doc.source_path)}</div>
        </div>
        <div class="document-actions">
          <button class="icon-button" data-action="inspect" data-id="${doc.document_id}">Inspect</button>
          <button class="icon-button" data-action="reindex" data-id="${doc.document_id}">Reindex</button>
          <button class="icon-button" data-action="delete" data-id="${doc.document_id}">Delete</button>
        </div>
      </article>
    `;
  }).join('');
}

async function refreshStatus() {
  renderStatus(await api('/api/status'));
}

async function refreshDocuments() {
  renderDocuments(await api('/api/documents'));
}

async function refreshWorkspace() {
  await Promise.all([refreshStatus(), refreshDocuments()]);
}

async function inspectDocument(documentId) {
  const detail = await api(`/api/documents/${documentId}`);
  showToast(`Document ${detail.document.file_name}: ${detail.chunk_count} chunks, ${detail.image_count} images.`);
}

async function reindexDocument(documentId) {
  const result = await api(`/api/documents/${documentId}/reindex`, { method: 'POST' });
  showToast(result.detail || 'Reindex started.');
  window.setTimeout(refreshWorkspace, 2500);
}

async function deleteDocument(documentId) {
  if (!window.confirm('Delete this document and its extracted assets?')) {
    return;
  }
  const result = await api(`/api/documents/${documentId}`, { method: 'DELETE' });
  showToast(`Deleted ${result.deleted_document_id}`);
  await refreshWorkspace();
}

document.getElementById('refreshGovernance').addEventListener('click', () => refreshWorkspace().catch(handleError));
document.getElementById('reloadDocuments').addEventListener('click', () => refreshDocuments().catch(handleError));

document.getElementById('bootstrapButton').addEventListener('click', async () => {
  try {
    const result = await api('/api/bootstrap', { method: 'POST' });
    showToast(result.detail);
    await refreshWorkspace();
  } catch (error) {
    handleError(error);
  }
});

document.getElementById('reindexButton').addEventListener('click', async () => {
  try {
    const result = await api('/api/reindex', { method: 'POST' });
    showToast(result.detail || 'Full reindex started.');
    window.setTimeout(refreshWorkspace, 3000);
  } catch (error) {
    handleError(error);
  }
});

function syncSelectedFiles() {
  const files = Array.from(elements.fileInput.files || []);
  renderSelectedFiles(files);
  if (files.length) {
    setUploadState(false, 'Files are ready. Click Upload and Index to start ingestion.');
  } else {
    setUploadState(false, '');
  }
}

elements.fileInput.addEventListener('input', syncSelectedFiles);
elements.fileInput.addEventListener('change', syncSelectedFiles);

document.getElementById('uploadForm').addEventListener('submit', async (event) => {
  event.preventDefault();
  if (!elements.fileInput.files.length) {
    showToast('Select one or more files first.', true);
    setUploadState(false, 'Choose at least one file before starting ingestion.', true);
    return;
  }
  const formData = new FormData();
  const files = Array.from(elements.fileInput.files);
  for (const file of files) {
    formData.append('files', file);
  }
  try {
    setUploadState(true, `Ingestion in progress for ${files.length} file(s). This may take a moment depending on document size.`);
    const result = await api('/api/documents/upload', { method: 'POST', body: formData });
    const skipped = result.skipped?.length ? ` ${result.skipped.length} file(s) were skipped.` : '';
    setUploadState(false, `Ingestion complete. Indexed ${result.ingested.length} document(s).${skipped}`);
    showToast(`Uploaded ${result.ingested.length} document(s).`);
    elements.fileInput.value = '';
    renderSelectedFiles([]);
    await refreshWorkspace();
  } catch (error) {
    setUploadState(false, error.message || 'Upload failed.', true);
    handleError(error);
  }
});

document.getElementById('folderForm').addEventListener('submit', async (event) => {
  event.preventDefault();
  const folderPath = document.getElementById('folderPath').value.trim();
  if (!folderPath) {
    showToast('Enter a server-side folder path.', true);
    return;
  }
  try {
    const result = await api('/api/documents/import-folder', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        folder_path: folderPath,
        recurse: document.getElementById('folderRecurse').checked,
        ingest: true,
      }),
    });
    showToast(`Imported ${result.ingested.length} document(s).`);
    await refreshWorkspace();
  } catch (error) {
    handleError(error);
  }
});

elements.documentTable.addEventListener('click', async (event) => {
  const button = event.target.closest('button[data-action]');
  if (!button) {
    return;
  }
  const { action, id } = button.dataset;
  try {
    if (action === 'inspect') await inspectDocument(id);
    if (action === 'reindex') await reindexDocument(id);
    if (action === 'delete') await deleteDocument(id);
  } catch (error) {
    handleError(error);
  }
});

function handleError(error) {
  console.error(error);
  showToast(error.message || 'Something went wrong.', true);
}

syncSelectedFiles();
refreshWorkspace().catch(handleError);
