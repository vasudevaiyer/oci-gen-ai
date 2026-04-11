import { useEffect, useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import rehypeKatex from "rehype-katex";
import remarkMath from "remark-math";

import "katex/dist/katex.min.css";

const starterQuestions = [
  "Explique la méthode de Craig-Bampton.",
  "Quel mot-clé permet de définir le coefficient de dilatation ?",
  "Trouver un test de validation d'une analyse thermo-mécanique d'un tuyau."
];

function getSessionId() {
  const storageKey = "rag-session-id";
  const existing = window.localStorage.getItem(storageKey);
  if (existing) {
    return existing;
  }
  const created = `web-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
  window.localStorage.setItem(storageKey, created);
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
  if (!trimmed) {
    return false;
  }

  if (trimmed.startsWith("où ")) {
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
  const lines = content.split("\n");
  const normalized = [];

  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index].trimEnd();
    const trimmed = line.trim();

    if (trimmed === "[Math]") {
      const mathLines = [];
      let cursor = index + 1;

      if (cursor < lines.length && lines[cursor].trim().startsWith(":label:")) {
        cursor += 1;
      }

      while (cursor < lines.length && looksLikeMathLine(lines[cursor])) {
        mathLines.push(lines[cursor].trim());
        cursor += 1;
      }

      if (mathLines.length) {
        normalized.push("", "$$", mathLines.join("\n"), "$$", "");
        index = cursor - 1;
        continue;
      }
    }

    if (trimmed.startsWith(":label:")) {
      continue;
    }

    normalized.push(line);
  }

  return normalized
    .join("\n")
    .replace(/\\\[((?:.|\n)+?)\\\]/g, (_, expression) => `\n\n$$\n${expression.trim()}\n$$\n\n`)
    .replace(/\\\(((?:\\.|[^\\)])+?)\\\)/g, (_, expression) => `$${expression.trim()}$`)
    .replace(/:math:`([^`]+)`/g, (_, expression) => `$${expression.trim()}$`)
    .replace(/:math:`[^`\n]*$/g, "")
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

export default function App() {
  const [theme, setTheme] = useState("light");
  const [status, setStatus] = useState(null);
  const [analytics, setAnalytics] = useState(null);
  const [messages, setMessages] = useState([
    {
      role: "assistant",
      content:
        "Posez une question sur la documentation Code_Aster. Vous pouvez aussi joindre une image technique pour activer le chemin multimodal.",
      sources: [],
      images: [],
      followUpQuestions: []
    }
  ]);
  const [question, setQuestion] = useState("");
  const [imageFile, setImageFile] = useState(null);
  const [pending, setPending] = useState(false);
  const [ingesting, setIngesting] = useState(false);

  async function loadStatus() {
    const response = await fetch("/api/status");
    const payload = await response.json();
    setStatus(payload);
    setIngesting(payload.ingest_running);
  }

  async function loadAnalytics() {
    const response = await fetch("/api/analytics/summary?days=30&top_n=6");
    if (!response.ok) {
      return;
    }
    const payload = await response.json();
    setAnalytics(payload);
  }

  useEffect(() => {
    loadStatus();
    loadAnalytics();
    const timer = window.setInterval(() => {
      loadStatus();
      loadAnalytics();
    }, 5000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  const stats = useMemo(() => {
    if (!status) {
      return [];
    }
    return [
      { label: "Documents", value: status.documents },
      { label: "Chunks", value: status.chunks },
      { label: "Images", value: status.images }
    ];
  }, [status]);

  async function runIngest() {
    setIngesting(true);
    await fetch("/api/ingest", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ rebuild: true })
    });
    await loadStatus();
  }

  async function ask(rawQuestion) {
    const prompt = rawQuestion.trim();
    if (!prompt || pending) {
      return;
    }

    setPending(true);
    const currentImage = imageFile;
    setMessages((existing) => [
      ...existing,
      {
        role: "user",
        content: prompt,
        fileName: currentImage?.name ?? null
      }
    ]);
    setQuestion("");
    setImageFile(null);

    try {
      const imageDataUrl = currentImage ? await toDataUrl(currentImage) : null;
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: prompt,
          top_k: 6,
          image_data_url: imageDataUrl,
          session_id: getSessionId()
        })
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail || "Request failed");
      }
      setMessages((existing) => [
        ...existing,
        {
          role: "assistant",
          content: payload.answer,
          sources: payload.sources,
          images: payload.matched_images,
          followUpQuestions: payload.follow_up_questions || [],
          model: payload.model
        }
      ]);
      await loadStatus();
      await loadAnalytics();
    } catch (error) {
      setMessages((existing) => [
        ...existing,
        {
          role: "assistant",
          content: `Erreur: ${error.message}`,
          sources: [],
          images: [],
          followUpQuestions: []
        }
      ]);
    } finally {
      setPending(false);
    }
  }

  function clearChat() {
    setMessages([
      {
        role: "assistant",
        content:
          "Posez une question sur la documentation Code_Aster. Vous pouvez aussi joindre une image technique pour activer le chemin multimodal.",
        sources: [],
        images: [],
        followUpQuestions: []
      }
    ]);
    setQuestion("");
    setImageFile(null);
  }

  function downloadAnalytics(days) {
    const suffix = typeof days === "number" ? `?days=${days}` : "";
    window.open(`/api/analytics/export${suffix}`, "_blank", "noopener,noreferrer");
  }

  return (
    <div className="shell">
      <aside className="panel brand-panel">
        <div className="brand-mark">OCI</div>
        <h1>French Technical RAG</h1>
        <p className="lede">
          Oracle AI Database vector search, OCI GenAI embeddings, multimodal chat, and a corpus of
          equation-heavy RST manuals.
        </p>

        <div className="stat-grid">
          {stats.map((item) => (
            <div key={item.label} className="stat-card">
              <span>{item.label}</span>
              <strong>{item.value}</strong>
            </div>
          ))}
        </div>

        <div className="model-card">
          <h2>Models</h2>
          <p>Embeddings: {status?.models?.embedding || "..."}</p>
          <p>Chat: {status?.models?.chat || "..."}</p>
          <p>Vision: {status?.models?.vision || "..."}</p>
        </div>

        <div className="action-stack">
          <button className="primary-button" onClick={runIngest} disabled={ingesting}>
            {ingesting ? "Indexing..." : "Rebuild Index"}
          </button>
          <button className="secondary-button" onClick={() => downloadAnalytics(30)}>
            Export 30d CSV
          </button>
          <button className="secondary-button" onClick={() => setTheme(theme === "light" ? "dark" : "light")}>
            {theme === "light" ? "Dark Mode" : "Light Mode"}
          </button>
          <button className="secondary-button" onClick={clearChat}>
            Clear Chat
          </button>
        </div>

        <div className="hint-list">
          <h2>Starter prompts</h2>
          {starterQuestions.map((item) => (
            <button key={item} className="hint-chip" onClick={() => ask(item)}>
              {item}
            </button>
          ))}
        </div>

        <div className="analytics-card">
          <div className="analytics-heading">
            <h2>Usage analytics</h2>
            <span>Last 30 days</span>
          </div>
          <div className="analytics-mini-grid">
            <div className="analytics-mini-card">
              <span>Total questions</span>
              <strong>{analytics?.total_questions ?? 0}</strong>
            </div>
            <div className="analytics-mini-card">
              <span>Unique</span>
              <strong>{analytics?.unique_questions ?? 0}</strong>
            </div>
            <div className="analytics-mini-card">
              <span>With images</span>
              <strong>{analytics?.questions_with_images ?? 0}</strong>
            </div>
            <div className="analytics-mini-card">
              <span>Avg latency</span>
              <strong>{Math.round(analytics?.avg_latency_ms ?? 0)} ms</strong>
            </div>
          </div>

          <div className="analytics-section">
            <div className="analytics-section-title">Top questions</div>
            <div className="analytics-list">
              {analytics?.top_questions?.length ? (
                analytics.top_questions.map((item) => (
                  <button
                    key={`${item.normalized_question}-${item.last_asked_at}`}
                    className="analytics-item"
                    onClick={() => ask(item.question)}
                  >
                    <span>{item.question}</span>
                    <strong>{item.count}</strong>
                  </button>
                ))
              ) : (
                <div className="analytics-empty">No questions logged yet.</div>
              )}
            </div>
          </div>

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
      </aside>

      <main className="panel chat-panel">
        <div className="chat-header">
          <div>
            <p className="eyebrow">OCI-specific workspace</p>
            <h2>Ask the manuals</h2>
          </div>
          <div className="header-actions">
            <div className={`status-pill ${status?.chunks ? "ready" : "empty"}`}>
              {status?.chunks ? "Indexed" : "No index"}
            </div>
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
                    {message.followUpQuestions.map((item) => (
                      <button key={item} className="hint-chip follow-up-chip" onClick={() => ask(item)}>
                        {item}
                      </button>
                    ))}
                  </div>
                </div>
              ) : null}
              {message.sources?.length ? (
                <div className="source-grid">
                  {message.sources.map((source) => (
                    <div key={`${source.source_path}-${source.section_path}`} className="source-card">
                      <strong>{source.title}</strong>
                      <span>{source.section_path}</span>
                      <small>{source.source_path}</small>
                      <MessageBody content={source.excerpt} renderMarkdown />
                      {source.image_urls?.length ? (
                        <div className="thumb-row">
                          {source.image_urls.slice(0, 3).map((imageUrl) => (
                            <img key={imageUrl} src={imageUrl} alt="" />
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
              onChange={(event) => setImageFile(event.target.files?.[0] || null)}
            />
            <span>{imageFile ? imageFile.name : "Attach image"}</span>
          </label>
          <textarea
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="Ask in French or English about equations, operators, procedures, or validation cases."
            rows={4}
          />
          <button className="primary-button" onClick={() => ask(question)} disabled={pending}>
            {pending ? "Thinking..." : "Send"}
          </button>
        </div>
      </main>
    </div>
  );
}
