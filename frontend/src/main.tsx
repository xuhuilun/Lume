import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import "./style.css";
import { validateResponse } from "./protocol";

type Space = {
  id: string;
  name: string;
  read: boolean;
  maintain: boolean;
  message_count: number;
};
type Task = {
  id: string;
  question: string;
  state: string;
  model_calls?: number;
  tool_calls?: number;
  answer_id?: string;
  error?: string;
};
type Answer = {
  id: string;
  text: string;
  citation_ids: string[];
  dependencies: unknown[];
};
type Picture = {
  id: string;
  filename: string;
  status: string;
  ocr_text: string;
  error?: string;
};
type Message = {
  message_id: string;
  source_id: string;
  text: string;
  author: string;
  sent_at: string;
  version: number;
  images: Picture[];
};
type Evidence = {
  id: string;
  kind: string;
  content: {
    messages?: Message[];
    image_id?: string;
    text?: string;
    semantic?: boolean;
  };
};
const states: Record<string, string> = {
  queued: "等待执行",
  running: "正在查证",
  cancel_requested: "取消已受理",
  cancelled: "已取消",
  completed: "查证完成",
  insufficient: "依据不足",
  limited: "达到执行限制",
  failed: "执行失败",
};
const terminal = new Set([
  "completed",
  "insufficient",
  "limited",
  "failed",
  "cancelled",
]);

function App() {
  const [token, setToken] = useState("");
  const [draftToken, setDraftToken] = useState("");
  const [user, setUser] = useState("");
  const [spaces, setSpaces] = useState<Space[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [current, setCurrent] = useState<Task | null>(null);
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [evidence, setEvidence] = useState<Evidence | null>(null);
  const [question, setQuestion] = useState("");
  const [error, setError] = useState("");
  const [provider, setProvider] = useState("正在连接");
  const [events, setEvents] = useState<{ id: number; kind: string }[]>([]);
  const [importing, setImporting] = useState(false);
  const [importText, setImportText] = useState("");
  const [busy, setBusy] = useState(false);
  const active = useRef("");
  const [refreshSerial, setRefreshSerial] = useState(0);
  const generation = useRef(0);
  const requests = useRef(new AbortController());
  const valid = (g: number, task?: string) =>
    generation.current === g && (task === undefined || active.current === task);

  function logout() {
    generation.current += 1;
    requests.current.abort();
    requests.current = new AbortController();
    active.current = "";
    setToken("");
    setDraftToken("");
    setUser("");
    setSpaces([]);
    setSelected([]);
    setTasks([]);
    setCurrent(null);
    setAnswer(null);
    setEvidence(null);
    setEvents([]);
    setQuestion("");
    setError("");
    setImportText("");
    setImporting(false);
    setBusy(false);
  }

  async function api<T>(
    path: string,
    options: RequestInit = {},
    access = token,
  ): Promise<T> {
    const response = await fetch("/api" + path, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        Authorization: "Bearer " + access,
        ...options.headers,
      },
      signal: options.signal || requests.current.signal,
      cache: "no-store",
    });
    let data: unknown;
    try {
      data = await response.json();
    } catch {
      throw new Error("服务返回格式异常，请稍后重试");
    }
    if (!response.ok) {
      const record = data as { message?: string; detail?: unknown };
      throw new Error(
        record.message ||
          (response.status === 422 ? "输入格式不符合要求" : "请求未完成"),
      );
    }
    validateResponse(path, options.method || "GET", data);
    return data as T;
  }

  useEffect(() => {
    fetch("/api/health")
      .then((r) => r.json())
      .then((d) => setProvider(String(d.provider_label || "服务不可用")))
      .catch(() => setProvider("服务未连接"));
  }, []);
  async function login(event: React.FormEvent) {
    event.preventDefault();
    const g = ++generation.current;
    requests.current.abort();
    requests.current = new AbortController();
    const access = draftToken.trim();
    setError("");
    setBusy(true);
    try {
      const [me, sources, history] = await Promise.all([
        api<{ name: string }>("/me", {}, access),
        api<Space[]>("/spaces", {}, access),
        api<Task[]>("/tasks", {}, access),
      ]);
      if (!valid(g)) return;
      setToken(access);
      setDraftToken("");
      setUser(me.name);
      setSpaces(sources);
      setSelected(sources.filter((s) => s.read).map((s) => s.id));
      setTasks(history);
    } catch (e) {
      if (valid(g)) setError((e as Error).message);
    } finally {
      if (valid(g)) setBusy(false);
    }
  }

  async function openTask(task: Task) {
    setRefreshSerial((n) => n + 1);
    active.current = task.id;
    setCurrent(task);
    setAnswer(null);
    setEvidence(null);
    setEvents([]);
    setError("");
  }
  useEffect(() => {
    if (!token || !current) return;
    const id = current.id;
    const g = generation.current;
    let disposed = false;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const task = await api<Task>("/tasks/" + id);
        if (disposed || !valid(g, id)) return;
        const progress = await api<{ id: number; kind: string }[]>(
          "/tasks/" + id + "/events",
        );
        if (disposed || !valid(g, id)) return;
        setCurrent(task);
        setEvents(progress);
        if (task.answer_id) {
          try {
            const result = await api<Answer>("/answers/" + task.answer_id);
            if (!disposed && valid(g, id)) setAnswer(result);
          } catch (e) {
            if (!disposed && valid(g, id)) {
              setAnswer(null);
              setEvidence(null);
              setError((e as Error).message);
            }
          }
        }
        if (!terminal.has(task.state) && !disposed && valid(g, id))
          timer = setTimeout(poll, 650);
        else if (!disposed && valid(g, id)) {
          const history = await api<Task[]>("/tasks");
          if (!disposed && valid(g, id)) setTasks(history);
        }
      } catch (e) {
        if (!disposed && valid(g, id)) setError((e as Error).message);
      }
    }
    void poll();
    return () => {
      disposed = true;
      clearTimeout(timer);
    };
  }, [current?.id, token, refreshSerial]);

  async function submit(event?: React.FormEvent, preset?: string) {
    event?.preventDefault();
    const g = generation.current;
    const text = (preset || question).trim();
    if (!text || !selected.length || busy) return;
    setBusy(true);
    setError("");
    try {
      const result = await api<Task>("/tasks", {
        method: "POST",
        body: JSON.stringify({ question: text, space_ids: selected }),
      });
      if (!valid(g)) return;
      await openTask({ ...result, question: text });
      setQuestion("");
    } catch (e) {
      if (valid(g)) setError((e as Error).message);
    } finally {
      if (valid(g)) setBusy(false);
    }
  }
  async function loadEvidence(id: string) {
    const task = active.current,
      g = generation.current;
    setError("");
    try {
      const data = await api<Evidence>("/observations/" + id);
      if (valid(g, task)) setEvidence(data);
    } catch (e) {
      if (valid(g, task)) {
        setEvidence(null);
        setError((e as Error).message);
      }
    }
  }
  async function cancel() {
    if (!current) return;
    const id = current.id,
      g = generation.current;
    try {
      const result = await api<Task>("/tasks/" + id + "/cancel", {
        method: "POST",
      });
      if (valid(g, id)) setCurrent((t) => t && { ...t, state: result.state });
    } catch (e) {
      if (valid(g, id)) setError((e as Error).message);
    }
  }
  async function importMessages() {
    const target = spaces.find((s) => selected.includes(s.id) && s.maintain);
    const g = generation.current;
    if (!target) {
      setError("请先选择一个具有维护资格的资料源");
      return;
    }
    try {
      const body: unknown = JSON.parse(importText);
      await api("/spaces/" + target.id + "/imports", {
        method: "POST",
        body: JSON.stringify(body),
      });
      if (!valid(g)) return;
      const sources = await api<Space[]>("/spaces");
      if (!valid(g)) return;
      setSpaces(sources);
      setImporting(false);
      setImportText("");
    } catch (e) {
      if (valid(g)) setError((e as Error).message);
    }
  }
  const readable = spaces.filter((s) => s.read);

  if (!token)
    return (
      <main className="entry">
        <section className="entry-copy">
          <div className="wordmark">
            Lume<span> / </span>
          </div>
          <p className="eyebrow">MESSAGES INTO EVIDENCE</p>
          <h1>
            让讨论中的线索，
            <br />
            成为可核对的依据。
          </h1>
          <p>
            从消息、回复和图片出发，找回处理过程，
            <br />
            看清每一次回答的出处与边界。
          </p>
          <div className="entry-line" />
          <small>{provider}</small>
        </section>
        <form className="login" onSubmit={login}>
          <span className="eyebrow">WORKSPACE ACCESS</span>
          <h2>进入查证工作台</h2>
          <p>输入命令行初始化时生成的访问令牌。令牌仅保存在当前页面内存中。</p>
          <label htmlFor="token">访问令牌</label>
          <input
            id="token"
            type="password"
            autoComplete="off"
            value={draftToken}
            onChange={(e) => setDraftToken(e.target.value)}
            required
            placeholder="粘贴本地生成的令牌"
          />
          <button className="primary" type="submit" disabled={busy}>
            连接工作空间 <span>↗</span>
          </button>
          {error && (
            <p role="alert" className="error">
              {error}
            </p>
          )}
          <small>首次运行：lume init → lume seed → lume worker</small>
        </form>
      </main>
    );

  return (
    <div className="workspace">
      <aside className="rail">
        <div className="wordmark">
          Lume<span> / </span>
        </div>
        <div className="rail-heading">
          资料范围 <span>{readable.length.toString().padStart(2, "0")}</span>
        </div>
        <div className="spaces">
          {readable.map((s) => (
            <label
              className={"space " + (selected.includes(s.id) ? "chosen" : "")}
              key={s.id}
            >
              <input
                type="checkbox"
                checked={selected.includes(s.id)}
                onChange={(e) =>
                  setSelected((v) =>
                    e.target.checked
                      ? [...v, s.id]
                      : v.filter((id) => id !== s.id),
                  )
                }
              />
              <div>
                <strong>{s.name}</strong>
                <small>QQ 示例 · {s.message_count} 条记录</small>
              </div>
            </label>
          ))}
        </div>
        {!spaces.length && (
          <p className="rail-note">暂无资料范围。请由管理者授予读取资格。</p>
        )}
        <button className="rail-action" onClick={() => setImporting(true)}>
          ＋ 导入资料
        </button>
        <div className="rail-heading history-title">近期查证</div>
        <nav className="history">
          {tasks.map((t) => (
            <button
              className={current?.id === t.id ? "active-task" : ""}
              key={t.id}
              onClick={() => void openTask(t)}
            >
              <span className="tiny-dot" />
              <span>{t.question}</span>
            </button>
          ))}
        </nav>
        <div className="rail-footer">
          <span className="avatar">{user.slice(0, 1).toUpperCase()}</span>
          <div>
            <strong>{user}</strong>
            <small>已验证身份</small>
          </div>
          <button aria-label="退出" onClick={logout}>
            ↗
          </button>
        </div>
      </aside>
      <main className="desk">
        <header className="topbar">
          <div>
            <span className="eyebrow">RETRIEVAL WORKBENCH</span>
            <p>知识查证</p>
          </div>
          <span className="mode">
            <i />
            {provider}
          </span>
        </header>
        <div className="desk-body">
          {!current ? (
            <section className="welcome">
              <span className="index">01 / 开始一次查证</span>
              <h1>
                问题之后，
                <br />
                <em>有迹可循。</em>
              </h1>
              <p>
                给出一个错误码、一段现象，或截图中的疑问。
                <br />
                Lume 会在所选资料范围内寻找可以核对的来源。
              </p>
              <div className="suggestions">
                {[
                  "E_CONN_42 之前是如何处理的？",
                  "连接池调整后是否有结果确认？",
                  "截图中的连接池参数是多少？",
                ].map((q, i) => (
                  <button key={q} onClick={() => void submit(undefined, q)}>
                    <span>0{i + 1}</span>
                    {q}
                    <b>↗</b>
                  </button>
                ))}
              </div>
              <p className="fixture-note">
                演示资料为人工构造；演示引擎不代表真实模型效果。
              </p>
            </section>
          ) : (
            <section className="conversation">
              <div className="question-heading">
                <span className="eyebrow">INVESTIGATION</span>
                <h1>{current.question}</h1>
                <div className="statusline">
                  <span className={"state " + current.state}>
                    {states[current.state] || current.state}
                  </span>
                  <span>
                    模型尝试 {current.model_calls || 0} · 工具动作{" "}
                    {current.tool_calls || 0}
                  </span>
                  {!terminal.has(current.state) && (
                    <button onClick={() => void cancel()}>取消任务</button>
                  )}
                </div>
              </div>
              <div className="answer-block">
                <div className="answer-label">
                  <span className="lume-mark">L</span>
                  <b>Lume</b>
                  <small>来源可追踪的回答</small>
                </div>
                {answer ? (
                  <>
                    <div className="answer-text">{answer.text}</div>
                    <div className="citation-row">
                      {answer.citation_ids.map((id, i) => (
                        <button
                          className={
                            evidence?.id === id ? "selected-citation" : ""
                          }
                          key={id}
                          onClick={() => void loadEvidence(id)}
                        >
                          <span>{(i + 1).toString().padStart(2, "0")}</span>
                          查看来源 ↗
                        </button>
                      ))}
                    </div>
                    <p className="answer-footnote">
                      已核对引用归属与访问条件；内容支持性仍需结合原文判断。
                    </p>
                  </>
                ) : (
                  <div className="waiting">
                    {terminal.has(current.state) ? (
                      current.error || "本次任务没有可展示的回答。"
                    ) : (
                      <>
                        <span className="pulse" />
                        正在定位与读取相关资料…
                      </>
                    )}
                  </div>
                )}
              </div>
              {events.length > 0 && (
                <details className="trace">
                  <summary>
                    查看执行阶段 <span>{events.length} 项</span>
                  </summary>
                  <ol>
                    {events.map((e) => (
                      <li key={e.id}>{e.kind}</li>
                    ))}
                  </ol>
                </details>
              )}
            </section>
          )}
        </div>
        {error && (
          <div className="error banner" role="alert">
            {error}
          </div>
        )}
        <form className="composer" onSubmit={(e) => void submit(e)}>
          <textarea
            aria-label="查证问题"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            maxLength={2000}
            placeholder="描述你想核查的问题…"
            rows={2}
          />
          <div>
            <small>{selected.length} 个资料源 · 只读查证</small>
            <button
              className="primary"
              disabled={!question.trim() || !selected.length || busy}
            >
              {busy ? "正在提交" : "开始查证"} <span>↑</span>
            </button>
          </div>
        </form>
      </main>
      <aside className="evidence">
        <header>
          <span className="eyebrow">EVIDENCE</span>
          <h2>
            来源与观察 <span>↙</span>
          </h2>
        </header>
        {!evidence ? (
          <div className="evidence-empty">
            <div className="paper-icon">≡</div>
            <h3>依据，在这里展开。</h3>
            <p>选择回答中的来源，查看实际读取的消息、上下文和图片。</p>
            <span>候选相关 ≠ 事实支持</span>
          </div>
        ) : (
          <div className="evidence-content">
            <div className="evidence-kind">
              {evidence.kind === "image_observation"
                ? "图片观察"
                : "消息上下文"}
            </div>
            {evidence.content.messages?.map((m) => (
              <article className="source-card" key={m.message_id}>
                <div className="source-meta">
                  <strong>{m.author || "来源记录"}</strong>
                  <span>v{m.version}</span>
                </div>
                <p>{m.text}</p>
                <small>
                  {m.source_id} ·{" "}
                  {new Date(m.sent_at).toLocaleDateString("zh-CN")}
                </small>
                {m.images.map((i) => (
                  <ImageCard key={i.id} image={i} token={token} />
                ))}
              </article>
            ))}
            {evidence.content.image_id && (
              <ImageCard
                image={{
                  id: evidence.content.image_id,
                  filename: "原始图片",
                  status: "ready",
                  ocr_text: "",
                }}
                token={token}
              />
            )}{" "}
            {evidence.content.text && (
              <p className="vision-text">{evidence.content.text}</p>
            )}
          </div>
        )}
      </aside>
      {importing && (
        <div className="modal-shade">
          <section
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-label="导入资料"
          >
            <button
              className="close"
              aria-label="关闭"
              onClick={() => setImporting(false)}
            >
              ×
            </button>
            <span className="eyebrow">DATA INGESTION</span>
            <h2>导入可核查资料</h2>
            <p>
              导入到所选的第一个可维护资料源。格式为包含 messages 数组的
              JSON；图片可附 base64 数据。导入受理后由 worker 处理。
            </p>
            <textarea
              aria-label="消息JSON"
              value={importText}
              onChange={(e) => setImportText(e.target.value)}
              placeholder={
                '{"messages":[{"source_id":"m1","text":"消息正文","sent_at":"2026-11-01T08:00:00Z"}]}'
              }
            />
            <button className="primary" onClick={() => void importMessages()}>
              提交接入
            </button>
          </section>
        </div>
      )}
    </div>
  );
}

function ImageCard({ image, token }: { image: Picture; token: string }) {
  const [url, setUrl] = useState("");
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    setUrl("");
    setFailed(false);
    let disposed = false;
    let objectUrl = "";
    const controller = new AbortController();
    fetch("/api/images/" + image.id, {
      headers: { Authorization: "Bearer " + token },
      cache: "no-store",
      signal: controller.signal,
    })
      .then((r) => {
        if (!r.ok) throw new Error();
        return r.blob();
      })
      .then((blob) => {
        objectUrl = URL.createObjectURL(blob);
        if (!disposed) setUrl(objectUrl);
        else URL.revokeObjectURL(objectUrl);
      })
      .catch((e) => {
        if (!disposed && e.name !== "AbortError") setFailed(true);
      });
    return () => {
      disposed = true;
      controller.abort();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [image.id, token]);
  return (
    <figure className="image-card">
      {url ? (
        <a href={url} target="_blank" rel="noreferrer">
          <img src={url} alt={image.filename} />
        </a>
      ) : (
        <p>{failed ? "图片不可用或资格已变化" : "读取图片…"}</p>
      )}
      <figcaption>
        {image.filename} · {image.status}
      </figcaption>
      {image.ocr_text && (
        <details>
          <summary>OCR 文字</summary>
          <pre>{image.ocr_text}</pre>
        </details>
      )}
    </figure>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
