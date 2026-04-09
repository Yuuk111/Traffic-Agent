import asyncio
import contextlib
import json
from collections import deque
from datetime import datetime, timezone
from typing import Deque

from aiohttp import web


class ResponseEventStore:
    def __init__(self, max_items: int = 100):
        self._events: Deque[dict] = deque(maxlen=max_items)
        self._subscribers: set[asyncio.Queue] = set()
        self._lock = asyncio.Lock()

    async def add_event(self, event: dict) -> None:
        async with self._lock:
            self._events.appendleft(event)
            subscribers = list(self._subscribers)

        for queue in subscribers:
            with contextlib.suppress(asyncio.QueueFull):
                queue.put_nowait(event)

    async def get_events(self) -> list[dict]:
        async with self._lock:
            return list(self._events)

    async def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=20)
        async with self._lock:
            self._subscribers.add(queue)
        return queue

    async def unsubscribe(self, queue: asyncio.Queue) -> None:
        async with self._lock:
            self._subscribers.discard(queue)


def build_response_event(trace_id: str, step: int, response_text: str) -> dict:
    return {
        "trace_id": trace_id,
        "step": step,
        "response": response_text,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


INDEX_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Agent Responses</title>
  <style>
    :root {
      --bg: #f4efe6;
      --panel: rgba(255, 251, 245, 0.92);
      --panel-border: rgba(68, 48, 34, 0.14);
      --text: #2e2219;
      --muted: #786658;
      --accent: #c35b2d;
      --accent-soft: rgba(195, 91, 45, 0.12);
      --shadow: 0 18px 60px rgba(61, 38, 19, 0.12);
      --code-bg: #201712;
      --code-text: #f6e9dc;
    }

    * {
      box-sizing: border-box;
    }

    body {
      margin: 0;
      font-family: "Segoe UI", "PingFang SC", "Hiragino Sans GB", sans-serif;
      color: var(--text);
      background:
        radial-gradient(circle at top left, rgba(240, 171, 120, 0.35), transparent 28%),
        radial-gradient(circle at top right, rgba(142, 196, 191, 0.28), transparent 24%),
        linear-gradient(160deg, #f7f1e9 0%, #efe3d1 100%);
      min-height: 100vh;
      padding: 24px;
    }

    .shell {
      max-width: 980px;
      margin: 0 auto;
    }

    .hero {
      padding: 20px 24px;
      border: 1px solid var(--panel-border);
      border-radius: 24px;
      background: var(--panel);
      box-shadow: var(--shadow);
      backdrop-filter: blur(12px);
    }

    .hero h1 {
      margin: 0;
      font-size: clamp(28px, 5vw, 48px);
      letter-spacing: -0.04em;
    }

    .hero p {
      margin: 10px 0 0;
      color: var(--muted);
      font-size: 15px;
    }

    .status {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      margin-top: 16px;
      padding: 8px 12px;
      border-radius: 999px;
      background: var(--accent-soft);
      color: var(--accent);
      font-size: 13px;
      font-weight: 600;
    }

    .status-dot {
      width: 10px;
      height: 10px;
      border-radius: 50%;
      background: currentColor;
      box-shadow: 0 0 0 0 rgba(195, 91, 45, 0.5);
      animation: pulse 1.8s infinite;
    }

    .list {
      margin-top: 20px;
      display: grid;
      gap: 14px;
    }

    .card {
      padding: 18px;
      border-radius: 20px;
      border: 1px solid var(--panel-border);
      background: var(--panel);
      box-shadow: var(--shadow);
      opacity: 0;
      transform: translateY(10px);
      animation: rise 0.35s ease forwards;
    }

    .meta {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-bottom: 12px;
      color: var(--muted);
      font-size: 13px;
    }

    .pill {
      padding: 4px 10px;
      border-radius: 999px;
      background: rgba(46, 34, 25, 0.06);
    }

    pre {
      margin: 0;
      padding: 16px;
      white-space: pre-wrap;
      word-break: break-word;
      border-radius: 16px;
      background: var(--code-bg);
      color: var(--code-text);
      overflow-x: auto;
      font-size: 13px;
      line-height: 1.6;
    }

    .empty {
      padding: 24px;
      text-align: center;
      color: var(--muted);
      border: 1px dashed rgba(68, 48, 34, 0.2);
      border-radius: 20px;
      background: rgba(255, 251, 245, 0.6);
    }

    @keyframes rise {
      to {
        opacity: 1;
        transform: translateY(0);
      }
    }

    @keyframes pulse {
      0% {
        box-shadow: 0 0 0 0 rgba(195, 91, 45, 0.45);
      }
      70% {
        box-shadow: 0 0 0 10px rgba(195, 91, 45, 0);
      }
      100% {
        box-shadow: 0 0 0 0 rgba(195, 91, 45, 0);
      }
    }
  </style>
</head>
<body>
  <main class="shell">
    <section class="hero">
      <h1>Model Response Feed</h1>
      <p>实时展示每次调用大模型 API 后返回的内容，最新记录会出现在最上方。</p>
      <div class="status"><span class="status-dot"></span><span id="status-text">正在连接事件流...</span></div>
    </section>

    <section id="list" class="list">
      <div class="empty">还没有收到模型响应。</div>
    </section>
  </main>

  <script>
    const listEl = document.getElementById("list");
    const statusTextEl = document.getElementById("status-text");

    function escapeHtml(value) {
      return value
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;");
    }

    function renderCard(item) {
      const localTime = new Date(item.timestamp).toLocaleString();
      return `
        <article class="card">
          <div class="meta">
            <span class="pill">Trace ID: ${escapeHtml(item.trace_id || "-")}</span>
            <span class="pill">Step: ${item.step}</span>
            <span class="pill">${escapeHtml(localTime)}</span>
          </div>
          <pre>${escapeHtml(item.response || "")}</pre>
        </article>
      `;
    }

    function renderList(items) {
      if (!items.length) {
        listEl.innerHTML = '<div class="empty">还没有收到模型响应。</div>';
        return;
      }
      listEl.innerHTML = items.map(renderCard).join("");
    }

    function prependItem(item) {
      const empty = listEl.querySelector(".empty");
      if (empty) {
        listEl.innerHTML = renderCard(item);
        return;
      }
      listEl.insertAdjacentHTML("afterbegin", renderCard(item));
    }

    async function loadHistory() {
      const response = await fetch("/api/responses");
      const items = await response.json();
      renderList(items);
    }

    function connectEvents() {
      const source = new EventSource("/events");
      source.onopen = () => {
        statusTextEl.textContent = "已连接，等待新的模型响应";
      };
      source.onmessage = (event) => {
        const item = JSON.parse(event.data);
        prependItem(item);
      };
      source.onerror = () => {
        statusTextEl.textContent = "连接断开，正在重连...";
      };
    }

    loadHistory().catch(() => {
      statusTextEl.textContent = "历史记录加载失败";
    }).finally(connectEvents);
  </script>
</body>
</html>
"""


async def index(_: web.Request) -> web.Response:
    return web.Response(text=INDEX_HTML, content_type="text/html")


async def get_responses(request: web.Request) -> web.Response:
    store: ResponseEventStore = request.app["response_store"]
    return web.json_response(await store.get_events())


async def stream_responses(request: web.Request) -> web.StreamResponse:
    store: ResponseEventStore = request.app["response_store"]
    queue = await store.subscribe()

    response = web.StreamResponse(
        status=200,
        headers={
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )
    await response.prepare(request)

    try:
        await response.write(b": connected\n\n")
        while True:
            event = await queue.get()
            payload = json.dumps(event, ensure_ascii=False).encode("utf-8")
            await response.write(b"data: " + payload + b"\n\n")
    except (asyncio.CancelledError, ConnectionResetError):
        raise
    finally:
        await store.unsubscribe(queue)
        with contextlib.suppress(ConnectionResetError):
            await response.write_eof()


async def start_dashboard(response_store: ResponseEventStore, host: str = "0.0.0.0", port: int = 50052):
    app = web.Application()
    app["response_store"] = response_store
    app.router.add_get("/", index)
    app.router.add_get("/api/responses", get_responses)
    app.router.add_get("/events", stream_responses)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host=host, port=port)
    await site.start()
    return runner
