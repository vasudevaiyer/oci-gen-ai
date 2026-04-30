import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import rehypeKatex from "rehype-katex";
import remarkMath from "remark-math";
import "katex/dist/katex.min.css";
import simviaLogo from "./assets/simvia-logo.svg";

const STARTER_PROMPTS = [
  "Explique la méthode de Craig-Bampton.",
  "Quel mot-clé permet de définir le coefficient de dilatation ?",
  "Trouver un test de validation d'une analyse thermo-mécanique d'un tuyau.",
];

const DEFAULT_MESSAGES = [
  {
    role: "assistant",
    content:
      "Posez une question sur la documentation Code_Aster issue du corpus source Sphinx. Vous pouvez aussi joindre une image technique pour activer le chemin multimodal.",
    sources: [],
    images: [],
    followUpQuestions: [],
  },
];

const SESSION_STORAGE_KEY = "rag-source-v2-session-id";
const ADMIN_TOKEN_STORAGE_KEY = "rag-source-v2-admin-token";

function getSessionId() {
  const existing = window.localStorage.getItem(SESSION_STORAGE_KEY);
  if (existing) {
    return existing;
  }
  const created = `web-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
  window.localStorage.setItem(SESSION_STORAGE_KEY, created);
  return created;
}

function toDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

function looksLikeMathLine(line) {
  const trimmed = line.trim();
  if (!trimmed || trimmed.startsWith("où ")) {
    return false;
  }
  return (
    trimmed.startsWith("\\") ||
    trimmed.startsWith("{") ||
    trimmed.startsWith("[") ||
    trimmed.startsWith("(") ||
    trimmed.includes("\\begin{") ||
    /^[^A-Za-zÀ-ÖØ-öø-ÿ]*[=<>+\-]/u.test(trimmed)
  );
}

function normalizeMathMarkdown(content) {
  return content
    .split("\n")
    .map((line) => {
      const trimmed = line.trim();
      if (!looksLikeMathLine(trimmed)) {
        return line;
      }
      if (trimmed.startsWith("$$") && trimmed.endsWith("$$")) {
        return trimmed;
      }
      return `$$${trimmed}$$`;
    })
    .join("\n")
    .replace(/\[Math\]/g, "")
    .replace(/^:label:[^\n]*$/gm, "")
    .replace(/\\\[((?:\\.|[^\]])+?)\\\]/g, (_, expression) => `$$${expression.trim()}$$`)
    .replace(/\\\(((?:\\.|[^\\)])+?)\\\)/g, (_, expression) => `$${expression.trim()}$`)
    .replace(/:math:`([^`]+)`/g, (_, expression) => `$${expression.trim()}$`)
    .replace(/:math:`[^`\n]*$/g, "")
    .trim();
}

function cleanLabelText(content) {
  return content
    .replace(/\*\*(.*?)\*\*/g, "$1")
    .replace(/\s+/g, " ")
    .trim();
}

function MessageBody({ content, renderMarkdown = false }) {
  if (!renderMarkdown) {
    return <p className="plain-message">{content}</p>;
  }
  return (
    <div className="message-body">
      <ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[rehypeKatex]}>
        {normalizeMathMarkdown(content)}
      </ReactMarkdown>
    </div>
  );
}

async function readJsonResponse(response, fallbackMessage) {
  const contentType = response.headers.get("content-type") || "";
  const rawBody = await response.text();

  if (!contentType.includes("application/json")) {
    if (rawBody.trimStart().startsWith("<!doctype html") || rawBody.trimStart().startsWith("<html")) {
      throw new Error("Admin API returned HTML instead of JSON. Restart the backend on port 8015.");
    }
    throw new Error(fallbackMessage);
  }

  try {
    return JSON.parse(rawBody);
  } catch {
    throw new Error(fallbackMessage);
  }
}

function StatusPill({ indexed, running, phase }) {
  let label = indexed ? "Indexed" : "No index";
  if (running) {
    label = phase ? `Indexing: ${phase}` : "Indexing";
  }
  return <div className={`status-pill ${indexed ? "ready" : "empty"}`}>{label}</div>;
}

function ChatWorkspace({ theme, onToggleTheme, publicStatus }) {
  const [messages, setMessages] = useState(DEFAULT_MESSAGES);
  const [draft, setDraft] = useState("");
  const [file, setFile] = useState(null);
  const [isSending, setIsSending] = useState(false);

  async function sendMessage(rawQuestion) {
    const question = rawQuestion.trim();
    if (!question || isSending) {
      return;
    }

    const attachedFile = file;
    setMessages((current) => [
      ...current,
      {
        role: "user",
        content: question,
        fileName: attachedFile?.name ?? null,
      },
    ]);
    setDraft("");
    setFile(null);
    setIsSending(true);

    try {
      const imageDataUrl = attachedFile ? await toDataUrl(attachedFile) : null;
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question,
          top_k: 6,
          image_data_url: imageDataUrl,
          session_id: getSessionId(),
        }),
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail || "Request failed");
      }
      setMessages((current) => [
        ...current,
        {
          role: "assistant",
          content: payload.answer,
          sources: payload.sources,
          images: payload.matched_images,
          followUpQuestions: payload.follow_up_questions || [],
          model: payload.model,
        },
      ]);
    } catch (error) {
      setMessages((current) => [
        ...current,
        {
          role: "assistant",
          content: `Erreur: ${error.message}`,
          sources: [],
          images: [],
          followUpQuestions: [],
        },
      ]);
    } finally {
      setIsSending(false);
    }
  }

  function clearChat() {
    setMessages(DEFAULT_MESSAGES);
    setDraft("");
    setFile(null);
  }

  return (
    <div className="shell">
      <aside className="panel brand-panel">
        <div className="brand-mark brand-mark-image">
          <img className="brand-logo" src={simviaLogo} alt="SIMVIA" />
        </div>
        <h1>SIMVIA Technical Knowledge Assistant</h1>
        <p className="lede">
          A focused assistant for exploring technical manuals, procedures, and engineering equations from the source documentation.
        </p>
        <div className="model-card">
          <h2>Workspace</h2>
          <p>Public assistant for the indexed documentation corpus.</p>
          <p>Status is visible here, while metrics and rebuild controls are reserved for admins.</p>
        </div>
        <div className="action-stack">
          <a className="secondary-button nav-link" href="/admin">
            Open Admin Page
          </a>
          <button className="secondary-button" onClick={onToggleTheme}>
            {theme === "light" ? "Dark Mode" : "Light Mode"}
          </button>
          <button className="secondary-button" onClick={clearChat}>
            Clear Chat
          </button>
        </div>
        <div className="hint-list">
          <h2>Starter prompts</h2>
          {STARTER_PROMPTS.map((prompt) => (
            <button key={prompt} className="hint-chip" onClick={() => sendMessage(prompt)}>
              {prompt}
            </button>
          ))}
        </div>
      </aside>

      <main className="panel chat-panel">
        <div className="chat-header">
          <div>
            <h2>Ask the manuals</h2>
          </div>
          <div className="header-actions">
            <StatusPill
              indexed={Boolean(publicStatus?.indexed)}
              running={Boolean(publicStatus?.ingest_running)}
              phase={publicStatus?.phase}
            />
            <button className="ghost-button" onClick={clearChat}>
              Reset Conversation
            </button>
          </div>
        </div>

        <div className="message-list">
          {messages.map((message, index) => (
            <article key={`${message.role}-${index}`} className={`message ${message.role}`}>
              <div className="message-meta">
                <span>{message.role === "assistant" ? "Oracle RAG" : "You"}</span>
                {message.model ? <small>{message.model}</small> : null}
              </div>

              <MessageBody content={message.content} renderMarkdown={message.role === "assistant"} />

              {message.fileName ? <div className="attachment">Image: {message.fileName}</div> : null}

              {message.followUpQuestions?.length ? (
                <div className="follow-up-block">
                  <div className="follow-up-label">Suggested follow-up questions</div>
                  <div className="follow-up-list">
                    {message.followUpQuestions.map((question) => (
                      <button key={question} className="hint-chip follow-up-chip" onClick={() => sendMessage(question)}>
                        {question}
                      </button>
                    ))}
                  </div>
                </div>
              ) : null}

              {message.sources?.length ? (
                <div className="source-grid">
                  {message.sources.map((source) => (
                    <div key={`${source.source_path}-${source.section_path}`} className="source-card">
                      <strong>{cleanLabelText(source.title)}</strong>
                      <span>{cleanLabelText(source.section_path)}</span>
                      <small>{source.source_path}</small>
                      <MessageBody content={source.excerpt} renderMarkdown />
                      {source.image_urls?.length ? (
                        <div className="thumb-row">
                          {source.image_urls.slice(0, 3).map((url) => (
                            <img key={url} src={url} alt="" />
                          ))}
                        </div>
                      ) : null}
                    </div>
                  ))}
                </div>
              ) : null}

              {message.images?.length ? (
                <div className="vision-grid">
                  {message.images.map((image) => (
                    <div key={image.image_url} className="vision-card">
                      <img src={image.image_url} alt={image.caption_text} />
                      <div>
                        <strong>{image.section_path}</strong>
                        <p>{image.caption_text}</p>
                      </div>
                    </div>
                  ))}
                </div>
              ) : null}
            </article>
          ))}
        </div>

        <div className="composer">
          <label className="file-input">
            <input
              type="file"
              accept="image/*"
              onChange={(event) => setFile(event.target.files?.[0] || null)}
            />
            <span>{file ? file.name : "Attach image"}</span>
          </label>
          <textarea
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder="Ask in French or English about equations, operators, procedures, or validation cases."
            rows={4}
          />
          <button className="primary-button" onClick={() => sendMessage(draft)} disabled={isSending}>
            {isSending ? "Thinking..." : "Send"}
          </button>
        </div>
      </main>
    </div>
  );
}

function AdminLogin({ tokenInput, setTokenInput, loginError, statusMessage, onSaveToken, theme, onToggleTheme }) {
  return (
    <div className="admin-shell">
      <section className="panel admin-login">
        <div className="brand-mark brand-mark-image">
          <img className="brand-logo" src={simviaLogo} alt="SIMVIA" />
        </div>
        <h1>Admin Console</h1>
        <p className="lede">
          Document metrics, ingestion controls, and analytics are available here only with the configured admin token.
        </p>
        <div className="admin-form">
          <label className="admin-field">
            <span>Admin token</span>
            <input
              type="password"
              value={tokenInput}
              onChange={(event) => setTokenInput(event.target.value)}
              placeholder="Enter X-Admin-Token value"
            />
          </label>
          <button className="primary-button" onClick={onSaveToken} disabled={!tokenInput.trim()}>
            Enter Admin Page
          </button>
          <a className="secondary-button nav-link" href="/">
            Back To Chat
          </a>
          <button className="secondary-button" onClick={onToggleTheme}>
            {theme === "light" ? "Dark Mode" : "Light Mode"}
          </button>
        </div>
        {statusMessage ? <div className="admin-note">{statusMessage}</div> : null}
        {loginError ? <div className="admin-error">{loginError}</div> : null}
      </section>
    </div>
  );
}

function AdminWorkspace({
  analytics,
  adminStatus,
  onExportCsv,
  onLogout,
  onRebuild,
  rebuildPending,
  theme,
  onToggleTheme,
}) {
  const statCards = [
    { label: "Documents", value: adminStatus?.documents ?? 0 },
    { label: "Chunks", value: adminStatus?.chunks ?? 0 },
    { label: "Images", value: adminStatus?.images ?? 0 },
  ];

  const progress = adminStatus?.stats || {};

  return (
    <div className="admin-shell">
      <aside className="panel brand-panel">
        <div className="brand-mark brand-mark-image">
          <img className="brand-logo" src={simviaLogo} alt="SIMVIA" />
        </div>
        <h1>Admin Console</h1>
        <p className="lede">
          Protected controls for corpus visibility, ingestion monitoring, and usage analytics in the source-based app.
        </p>

        <div className="stat-grid">
          {statCards.map((card) => (
            <div key={card.label} className="stat-card">
              <span>{card.label}</span>
              <strong>{card.value}</strong>
            </div>
          ))}
        </div>

        <div className="model-card">
          <h2>Models</h2>
          <p>Embeddings: {adminStatus?.models?.embedding || "..."}</p>
          <p>Chat: {adminStatus?.models?.chat || "..."}</p>
          <p>Vision: {adminStatus?.models?.vision || "..."}</p>
        </div>

        <div className="action-stack">
          <button className="primary-button" onClick={onRebuild} disabled={rebuildPending || adminStatus?.ingest_running}>
            {rebuildPending || adminStatus?.ingest_running ? "Indexing..." : "Rebuild Index"}
          </button>
          <button className="secondary-button" onClick={() => onExportCsv(30)}>
            Export 30d CSV
          </button>
          <button className="secondary-button" onClick={onToggleTheme}>
            {theme === "light" ? "Dark Mode" : "Light Mode"}
          </button>
          <button className="secondary-button" onClick={onLogout}>
            Logout
          </button>
          <a className="secondary-button nav-link" href="/">
            Back To Chat
          </a>
        </div>
      </aside>

      <main className="admin-main">
        <section className="panel admin-section">
          <div className="chat-header">
            <div>
              <p className="eyebrow">Corpus operations</p>
              <h2>Document metrics</h2>
            </div>
            <StatusPill
              indexed={Boolean(adminStatus?.chunks)}
              running={Boolean(adminStatus?.ingest_running)}
              phase={adminStatus?.stats?.phase}
            />
          </div>

          <div className="admin-grid">
            <div className="analytics-card">
              <div className="analytics-heading">
                <h2>Index health</h2>
                <span>{adminStatus?.ingest_running ? "Live" : "Latest snapshot"}</span>
              </div>
              <div className="analytics-mini-grid">
                <div className="analytics-mini-card">
                  <span>Ingestion phase</span>
                  <strong>{progress.phase || "idle"}</strong>
                </div>
                <div className="analytics-mini-card">
                  <span>Chunks embedded</span>
                  <strong>{progress.embedded_chunks ?? adminStatus?.chunks ?? 0}</strong>
                </div>
                <div className="analytics-mini-card">
                  <span>Images embedded</span>
                  <strong>{progress.embedded_images ?? adminStatus?.images ?? 0}</strong>
                </div>
                <div className="analytics-mini-card">
                  <span>Discovered docs</span>
                  <strong>{progress.total_documents ?? adminStatus?.documents ?? 0}</strong>
                </div>
              </div>
            </div>

            <div className="analytics-card">
              <div className="analytics-heading">
                <h2>Progress details</h2>
                <span>Indexer telemetry</span>
              </div>
              <div className="admin-progress-list">
                <div className="admin-progress-row">
                  <span>Chunk batches</span>
                  <strong>{progress.chunk_batches_completed ?? 0}</strong>
                </div>
                <div className="admin-progress-row">
                  <span>Image batches</span>
                  <strong>{progress.image_batches_completed ?? 0}</strong>
                </div>
                <div className="admin-progress-row">
                  <span>Chunk queue</span>
                  <strong>{progress.total_chunks ?? adminStatus?.chunks ?? 0}</strong>
                </div>
                <div className="admin-progress-row">
                  <span>Image queue</span>
                  <strong>{progress.total_images ?? adminStatus?.images ?? 0}</strong>
                </div>
                <div className="admin-progress-row">
                  <span>Last completed</span>
                  <strong>{progress.completed_at || "not yet"}</strong>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section className="panel admin-section">
          <div className="analytics-heading">
            <h2>Usage analytics</h2>
            <span>Last 30 days</span>
          </div>

          <div className="admin-grid">
            <div className="analytics-card">
              <div className="analytics-mini-grid">
                <div className="analytics-mini-card">
                  <span>Total questions</span>
                  <strong>{analytics?.total_questions ?? 0}</strong>
                </div>
                <div className="analytics-mini-card">
                  <span>Successful</span>
                  <strong>{analytics?.successful_questions ?? 0}</strong>
                </div>
                <div className="analytics-mini-card">
                  <span>Unique</span>
                  <strong>{analytics?.unique_questions ?? 0}</strong>
                </div>
                <div className="analytics-mini-card">
                  <span>Avg latency</span>
                  <strong>{Math.round(analytics?.avg_latency_ms ?? 0)} ms</strong>
                </div>
              </div>
            </div>

            <div className="analytics-card">
              <div className="analytics-mini-grid">
                <div className="analytics-mini-card">
                  <span>Failed</span>
                  <strong>{analytics?.failed_questions ?? 0}</strong>
                </div>
                <div className="analytics-mini-card">
                  <span>With images</span>
                  <strong>{analytics?.questions_with_images ?? 0}</strong>
                </div>
              </div>
            </div>
          </div>

          <div className="admin-grid admin-grid-wide">
            <div className="analytics-card">
              <div className="analytics-section">
                <div className="analytics-section-title">Top questions</div>
                <div className="analytics-list">
                  {analytics?.top_questions?.length ? (
                    analytics.top_questions.map((item) => (
                      <div key={`${item.normalized_question}-${item.last_asked_at}`} className="analytics-item static">
                        <span>{item.question}</span>
                        <strong>{item.count}</strong>
                      </div>
                    ))
                  ) : (
                    <div className="analytics-empty">No questions logged yet.</div>
                  )}
                </div>
              </div>
            </div>

            <div className="analytics-card">
              <div className="analytics-section">
                <div className="analytics-section-title">Top source paths</div>
                <div className="analytics-list">
                  {analytics?.top_sources?.length ? (
                    analytics.top_sources.map((item) => (
                      <div key={`${item.source_path}-${item.section_path}`} className="analytics-item static">
                        <span>{item.source_path}</span>
                        <strong>{item.count}</strong>
                      </div>
                    ))
                  ) : (
                    <div className="analytics-empty">No source usage yet.</div>
                  )}
                </div>
              </div>
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}

export default function App() {
  const isAdminRoute = window.location.pathname.startsWith("/admin");
  const [theme, setTheme] = useState("light");
  const [publicStatus, setPublicStatus] = useState(null);
  const [adminStatus, setAdminStatus] = useState(null);
  const [analytics, setAnalytics] = useState(null);
  const [adminToken, setAdminToken] = useState(() => window.localStorage.getItem(ADMIN_TOKEN_STORAGE_KEY) || "");
  const [tokenInput, setTokenInput] = useState(() => window.localStorage.getItem(ADMIN_TOKEN_STORAGE_KEY) || "");
  const [adminError, setAdminError] = useState("");
  const [adminMessage, setAdminMessage] = useState("");
  const [rebuildPending, setRebuildPending] = useState(false);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  useEffect(() => {
    if (isAdminRoute) {
      return undefined;
    }

    async function loadPublicStatus() {
      try {
        const response = await fetch("/api/public-status");
        if (!response.ok) {
          throw new Error("Unable to load status");
        }
        const payload = await readJsonResponse(response, "Unable to load status");
        setPublicStatus(payload);
      } catch {
        setPublicStatus(null);
      }
    }

    loadPublicStatus();
    const timer = window.setInterval(loadPublicStatus, 5000);
    return () => window.clearInterval(timer);
  }, [isAdminRoute]);

  useEffect(() => {
    if (!isAdminRoute || !adminToken) {
      return undefined;
    }

    let cancelled = false;

    async function loadAdminData() {
      try {
        const headers = { "X-Admin-Token": adminToken };
        const [statusResponse, analyticsResponse] = await Promise.all([
          fetch("/api/admin/status", { headers }),
          fetch("/api/admin/analytics/summary?days=30&top_n=6", { headers }),
        ]);

        const statusPayload = await readJsonResponse(statusResponse, "Unable to load admin status");
        const analyticsPayload = await readJsonResponse(analyticsResponse, "Unable to load analytics");

        if (!statusResponse.ok) {
          throw new Error(statusPayload.detail || "Unable to load admin status");
        }

        if (!analyticsResponse.ok) {
          throw new Error(analyticsPayload.detail || "Unable to load analytics");
        }

        if (cancelled) {
          return;
        }

        setAdminStatus(statusPayload);
        setAnalytics(analyticsPayload);
        setAdminError("");
        setAdminMessage("");
      } catch (error) {
        if (cancelled) {
          return;
        }
        setAdminStatus(null);
        setAnalytics(null);
        setAdminError(error.message);
      }
    }

    loadAdminData();
    const timer = window.setInterval(loadAdminData, 5000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [adminToken, isAdminRoute]);

  function toggleTheme() {
    setTheme((current) => (current === "light" ? "dark" : "light"));
  }

  function saveAdminToken() {
    const nextToken = tokenInput.trim();
    window.localStorage.setItem(ADMIN_TOKEN_STORAGE_KEY, nextToken);
    setAdminToken(nextToken);
    setAdminError("");
    setAdminMessage(nextToken ? "Checking admin access..." : "");
  }

  function logoutAdmin() {
    window.localStorage.removeItem(ADMIN_TOKEN_STORAGE_KEY);
    setAdminToken("");
    setTokenInput("");
    setAdminStatus(null);
    setAnalytics(null);
    setAdminMessage("");
    setAdminError("");
  }

  async function rebuildIndex() {
    if (!adminToken || rebuildPending) {
      return;
    }

    setRebuildPending(true);
    setAdminMessage("");
    setAdminError("");

    try {
      const response = await fetch("/api/admin/ingest", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Admin-Token": adminToken,
        },
        body: JSON.stringify({ rebuild: true }),
      });
      const payload = await readJsonResponse(response, "Failed to start ingestion");
      if (!response.ok) {
        throw new Error(payload.detail || "Failed to start ingestion");
      }
      setAdminMessage(payload.detail || "Ingestion started.");
    } catch (error) {
      setAdminError(error.message);
    } finally {
      setRebuildPending(false);
    }
  }

  async function exportCsv(days) {
    try {
      const response = await fetch(`/api/admin/analytics/export?days=${days}`, {
        headers: { "X-Admin-Token": adminToken },
      });
      if (!response.ok) {
        const payload = await readJsonResponse(response, "Export failed");
        throw new Error(payload.detail || "Export failed");
      }
      const blob = await response.blob();
      const objectUrl = window.URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = objectUrl;
      anchor.download = `rag-analytics-${days}d.csv`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.URL.revokeObjectURL(objectUrl);
    } catch (error) {
      setAdminError(error.message);
    }
  }

  const shouldShowAdminLogin =
    !adminToken || (!adminStatus && /admin access is not configured|authentication failed|returned html instead of json/i.test(adminError));

  if (!isAdminRoute) {
    return (
      <ChatWorkspace
        theme={theme}
        onToggleTheme={toggleTheme}
        publicStatus={publicStatus}
      />
    );
  }

  if (shouldShowAdminLogin) {
    return (
      <AdminLogin
        tokenInput={tokenInput}
        setTokenInput={setTokenInput}
        loginError={adminError}
        statusMessage={adminMessage}
        onSaveToken={saveAdminToken}
        theme={theme}
        onToggleTheme={toggleTheme}
      />
    );
  }

  return (
    <div>
      {(adminMessage || adminError) && (
        <div className={`admin-banner ${adminError ? "error" : ""}`}>
          {adminError || adminMessage}
        </div>
      )}
      <AdminWorkspace
        analytics={analytics}
        adminStatus={adminStatus}
        onExportCsv={exportCsv}
        onLogout={logoutAdmin}
        onRebuild={rebuildIndex}
        rebuildPending={rebuildPending}
        theme={theme}
        onToggleTheme={toggleTheme}
      />
    </div>
  );
}
