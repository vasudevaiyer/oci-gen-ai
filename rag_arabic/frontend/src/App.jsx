import { useEffect, useMemo, useState } from "react";

const starterQuestions = [
  "ما نطاق هذه السياسة؟",
  "ما أهداف العمل عن بعد؟",
  "ما واجبات ومسؤوليات العامل؟",
  "ما واجبات ومسؤوليات المدير المباشر؟"
];

const introMessage =
  "اسأل عن سياسة العمل عن بعد، وستحصل على إجابة مستندة إلى نص الوثيقة مع الإشارة إلى المصدر.";

export default function App() {
  const [theme, setTheme] = useState("light");
  const [status, setStatus] = useState(null);
  const [messages, setMessages] = useState([
    {
      role: "assistant",
      content: introMessage,
      sources: [],
      followUpQuestions: []
    }
  ]);
  const [question, setQuestion] = useState("");
  const [pending, setPending] = useState(false);
  const [ingesting, setIngesting] = useState(false);

  async function loadStatus() {
    const response = await fetch("/api/status");
    const payload = await response.json();
    setStatus(payload);
    setIngesting(payload.ingest_running);
  }

  useEffect(() => {
    loadStatus();
    const timer = window.setInterval(loadStatus, 5000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    document.documentElement.lang = "ar";
    document.documentElement.dir = "rtl";
  }, [theme]);

  const stats = useMemo(() => {
    if (!status) {
      return [];
    }
    return [
      { label: "الوثائق", value: status.documents },
      { label: "المقاطع", value: status.chunks },
      { label: "الصور", value: status.images }
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
    setMessages((existing) => [
      ...existing,
      {
        role: "user",
        content: prompt
      }
    ]);
    setQuestion("");

    try {
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: prompt,
          top_k: 6
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
          followUpQuestions: payload.follow_up_questions || [],
          model: payload.model
        }
      ]);
      await loadStatus();
    } catch (error) {
      setMessages((existing) => [
        ...existing,
        {
          role: "assistant",
          content: `خطأ: ${error.message}`,
          sources: [],
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
        content: introMessage,
        sources: [],
        followUpQuestions: []
      }
    ]);
    setQuestion("");
  }

  return (
    <div className="shell">
      <aside className="panel brand-panel">
        <div className="brand-mark">OCI</div>
        <h1>AgentStudio</h1>
        <p className="lede">
          مساعد بحث ذكي لسياسة العمل عن بعد باستخدام Oracle AI Database و OCI Generative AI مع
          واجهة React مهيأة للأسئلة العربية.
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
          <h2>النماذج</h2>
          <p>Embeddings: {status?.models?.embedding || "..."}</p>
          <p>Chat: {status?.models?.chat || "..."}</p>
        </div>

        <div className="action-stack">
          <button className="primary-button" onClick={runIngest} disabled={ingesting}>
            {ingesting ? "جارٍ الفهرسة..." : "إعادة بناء الفهرس"}
          </button>
          <button className="secondary-button" onClick={() => setTheme(theme === "light" ? "dark" : "light")}>
            {theme === "light" ? "الوضع الداكن" : "الوضع الفاتح"}
          </button>
          <button className="secondary-button" onClick={clearChat}>
            مسح المحادثة
          </button>
        </div>

        <div className="hint-list">
          <h2>أسئلة مقترحة</h2>
          {starterQuestions.map((item) => (
            <button key={item} className="hint-chip" onClick={() => ask(item)}>
              {item}
            </button>
          ))}
        </div>
      </aside>

      <main className="panel chat-panel">
        <div className="chat-header">
          <div>
            <p className="eyebrow">AgentStudio workspace</p>
            <h2>اسأل الوثيقة</h2>
          </div>
          <div className="header-actions">
            <div className={`status-pill ${status?.chunks ? "ready" : "empty"}`}>
              {status?.chunks ? "مفهرس" : "لا يوجد فهرس"}
            </div>
            <button className="ghost-button" onClick={clearChat}>
              إعادة ضبط المحادثة
            </button>
          </div>
        </div>

        <div className="message-list">
          {messages.map((message, index) => (
            <article key={`${message.role}-${index}`} className={`message ${message.role}`}>
              <div className="message-meta">
                <span>{message.role === "assistant" ? "AgentStudio" : "أنت"}</span>
                {message.model ? <small>{message.model}</small> : null}
              </div>
              <p>{message.content}</p>
              {message.followUpQuestions?.length ? (
                <div className="follow-up-block">
                  <div className="follow-up-label">أسئلة متابعة مقترحة</div>
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
                      <p>{source.excerpt}</p>
                    </div>
                  ))}
                </div>
              ) : null}
            </article>
          ))}
        </div>

        <div className="composer">
          <textarea
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="اكتب سؤالك بالعربية حول سياسة العمل عن بعد."
            rows={4}
          />
          <button className="primary-button" onClick={() => ask(question)} disabled={pending}>
            {pending ? "جارٍ التفكير..." : "إرسال"}
          </button>
        </div>
      </main>
    </div>
  );
}
