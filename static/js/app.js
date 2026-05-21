// === State ===
const msgsEl = document.getElementById('messages');
const inner = document.getElementById('messagesInner');
const input = document.getElementById('input');
const sendBtn = document.getElementById('sendBtn');
const stopBtn = document.getElementById('stopBtn');
const emptyState = document.getElementById('emptyState');
const rightPanel = document.getElementById('rightPanel');
const vncStatus = document.getElementById('vncStatus');
const vncStatusText = document.getElementById('vncStatusText');
const panelSizeHint = document.getElementById('panelSizeHint');

// cached common nodes
const sbMsgCount = document.getElementById('sbMsgCount');
const sbToolCount = document.getElementById('sbToolCount');
const sbSessionId = document.getElementById('sbSessionId');
const sbProvider = document.getElementById('sbProvider');
const sbModel = document.getElementById('sbModel');
const topbarModel = document.getElementById('topbarModel');
const topbarTitle = document.getElementById('topbarTitle');
const inputFooter = document.getElementById('inputFooter');
const sidebar = document.getElementById('sidebar');
const sidebarOverlay = document.getElementById('sidebarOverlay');
const sidebarResizeHandle = document.getElementById('sidebarResizeHandle');
const rpVnc = document.getElementById('rpVnc');
const rpUrl = document.getElementById('rpUrl');
const ssGrid = document.getElementById('ssGrid');
const actionList = document.getElementById('actionList');
const actEmptyEl = document.getElementById('actEmpty');
const ssEmptyEl = document.getElementById('ssEmpty');
const vncContainer = document.getElementById('vncContainer');
const vncFrame = document.getElementById('vncFrame');
const vncResizeHandle = document.getElementById('vncResizeHandle');
const rpDrawer = document.getElementById('rpDrawer');
const panelSplitter = document.getElementById('panelSplitter');
const lightbox = document.getElementById('lightbox');
const lbImg = document.getElementById('lbImg');

let sessionId = new URLSearchParams(location.search).get('session_id') || '';
let msgCount = 0, toolCount = 0, allScreenshots = [];
let timeline = null, timelineSteps = [], currentTimelineStep = null;
let abortController = null;  // For cancellation
let panelHintTimer = null;
let vncBaseSize = { w: 1280, h: 720 };
let panelDragState = null;
let panelWidthManual = false;
let vncFitRaf = null;

if (sessionId) {
  const u = new URL(location); u.searchParams.set('session_id', sessionId);
  history.replaceState(null, '', u);
}

// === Helpers ===
const ts = () => {
  const d = new Date();
  return d.getHours().toString().padStart(2, '0') + ':' +
    d.getMinutes().toString().padStart(2, '0') + ':' +
    d.getSeconds().toString().padStart(2, '0');
};
const esc = s => { const d = document.createElement('div'); d.textContent = s; return d.innerHTML; };
const scrollBottom = () => { msgsEl.scrollTop = msgsEl.scrollHeight; };
const hideEmpty = () => { if (emptyState) emptyState.style.display = 'none'; };
const updateStats = () => {
  if (sbMsgCount) sbMsgCount.textContent = msgCount;
  if (sbToolCount) sbToolCount.textContent = toolCount;
  if (sessionId && sbSessionId) sbSessionId.textContent = sessionId;
};
const showPanelSizeHint = (value, autoHide = true) => {
  if (!panelSizeHint) return;
  panelSizeHint.textContent = value;
  panelSizeHint.classList.add('visible');
  if (panelHintTimer) clearTimeout(panelHintTimer);
  if (autoHide) {
    panelHintTimer = setTimeout(() => panelSizeHint.classList.remove('visible'), 1200);
  }
};

function setRunning(running) {
  sendBtn.disabled = running;
  if (running) {
    stopBtn.classList.add('visible');
    input.placeholder = 'Agent 正在执行中...';
  } else {
    stopBtn.classList.remove('visible');
    input.placeholder = '输入消息，Enter 发送，Shift+Enter 换行...';
    abortController = null;
  }
}

function setVncStatus(text, loading) {
  if (!vncStatus) return;
  if (vncStatusText) vncStatusText.textContent = text;
  vncStatus.style.display = loading ? 'flex' : 'none';
}

function setPanelOpen(isOpen) {
  if (!rightPanel) return;
  if (isOpen) {
    if (!rightPanel.classList.contains('open')) {
      rightPanel.classList.add('open');
      document.body.classList.add('layout-panel-open');
      if (!panelWidthManual) updatePanelWidth();
      scheduleFitVncFrame();
    }
    if (panelSplitter) panelSplitter.style.display = 'block';
    return;
  }
  rightPanel.classList.remove('open', 'max');
  document.body.classList.remove('layout-panel-open', 'panel-max');
  if (panelSizeHint) panelSizeHint.classList.remove('visible');
  if (panelSplitter) panelSplitter.style.display = 'none';
}

function setPanelMax(isMax) {
  if (!rightPanel) return;
  rightPanel.classList.toggle('max', isMax);
  document.body.classList.toggle('panel-max', isMax);
  if (panelSplitter && rightPanel.classList.contains('open')) {
    panelSplitter.style.display = isMax ? 'none' : 'block';
  }
  if (panelSizeHint) {
    const value = isMax ? '100%' : Math.round((rightPanel.offsetWidth / window.innerWidth) * 100) + '%';
    showPanelSizeHint(value, !isMax);
  }
  scheduleFitVncFrame();
}

// === Config ===
(async function loadConfig() {
  try {
    const r = await fetch('/api/config'); if (!r.ok) return;
    const c = await r.json();
    if (sbProvider) sbProvider.textContent = c.provider === 'openai' ? 'OpenAI 兼容' : c.provider;
    const ms = sbModel ? sbModel.querySelector('span:last-child') : null;
    if (ms) ms.textContent = c.model;
    if (topbarModel) topbarModel.textContent = c.model;
    if (sbSessionId) sbSessionId.textContent = sessionId || '(新会话)';
    if (inputFooter) {
      inputFooter.textContent =
        (c.provider === 'openai' ? 'OpenAI 兼容' : c.provider) + ' · ' +
        c.model + (c.sandbox_enabled ? ' · 沙箱就绪' : '');
    }

    if (c.sandbox_enabled && c.sandbox_url) {
      const base = c.sandbox_url.replace(/\/$/, '');
      const vncUrl = base + '/vnc/index.html?autoconnect=true';
      if (rpVnc) {
        setVncStatus('正在连接沙箱浏览器...', true);
        rpVnc.src = vncUrl;
        rpVnc.addEventListener('load', () => {
          setTimeout(() => setVncStatus('已加载沙箱浏览器', false), 600);
          fitVncFrame();
        }, { once: true });
      }
    }
  } catch (e) { console.warn(e); }
})();

// === Sidebar ===
function toggleSidebar() {
  if (!sidebar || !sidebarOverlay) return;
  sidebar.classList.toggle('open');
  sidebarOverlay.style.display = sidebar.classList.contains('open') ? 'block' : 'none';
}
function closeSidebar() {
  if (!sidebar || !sidebarOverlay) return;
  sidebar.classList.remove('open');
  sidebarOverlay.style.display = 'none';
}

// === Right Panel (slides in/out) ===
function openRightPanel() {
  setPanelOpen(true);
}
function closeRightPanel() {
  setPanelOpen(false);
}
async function togglePanelMax() {
  if (!rightPanel) return;
  if (document.fullscreenElement) {
    await document.exitFullscreen().catch(() => {});
    return;
  }
  openRightPanel();
  if (rightPanel.requestFullscreen) {
    try {
      await rightPanel.requestFullscreen({ navigationUI: 'hide' });
      setPanelMax(true);
      scheduleFitVncFrame();
      return;
    } catch (err) {
      console.warn('Fullscreen request failed:', err);
    }
  }
  setPanelMax(!rightPanel.classList.contains('max'));
}
function updatePanelWidth() {
  const w = window.innerWidth;
  let ratio = 0.7;
  if (w >= 1400) ratio = 0.6;
  else if (w >= 1100) ratio = 0.65;
  else if (w <= 900) ratio = 0.85;
  const nextWidth = Math.round(w * ratio) + 'px';
  document.body.style.setProperty('--panel-w', nextWidth);
  if (panelSizeHint && !rightPanel.classList.contains('max')) {
    showPanelSizeHint(Math.round(ratio * 100) + '%');
  }
}
function refreshVnc() {
  if (!rpVnc) return;
  setVncStatus('正在刷新沙箱浏览器...', true);
  // reload iframe
  rpVnc.src = rpVnc.src;
  scheduleFitVncFrame();
}
function syncPanelWidth(widthPx) {
  const w = Math.max(360, Math.min(window.innerWidth - 380, widthPx));
  panelWidthManual = true;
  document.body.style.setProperty('--panel-w', w + 'px');
  if (panelSizeHint) showPanelSizeHint(Math.round((w / window.innerWidth) * 100) + '%');
  scheduleFitVncFrame();
}
function switchPanelTab(tab) {
  const tabEl = document.querySelector('[data-tab="' + tab + '"]');
  const isActive = tabEl && tabEl.classList.contains('active');
  const isExpanded = rpDrawer && !rpDrawer.classList.contains('collapsed');

  if (rpDrawer) {
    if (isActive && isExpanded) {
      rpDrawer.classList.add('collapsed');
      scheduleFitVncFrame();
      return;
    }
    rpDrawer.classList.remove('collapsed');
  }

  document.querySelectorAll('.rp-tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.rp-tab-content').forEach(c => c.classList.remove('active'));
  if (tabEl) tabEl.classList.add('active');
  const cap = tab.charAt(0).toUpperCase() + tab.slice(1);
  const content = document.getElementById('panelTab' + cap);
  if (content) content.classList.add('active');
  scheduleFitVncFrame();
}

function fitVncFrame() {
  if (!vncFrame || !rpVnc || !vncContainer) return;
  const areaW = vncContainer.clientWidth;
  const areaH = vncContainer.clientHeight;
  if (!areaW || !areaH) return;

  const scale = Math.min(areaW / vncBaseSize.w, areaH / vncBaseSize.h);
  const frameW = Math.max(1, Math.floor(vncBaseSize.w * scale));
  const frameH = Math.max(1, Math.floor(vncBaseSize.h * scale));
  vncFrame.style.width = frameW + 'px';
  vncFrame.style.height = frameH + 'px';

  rpVnc.style.width = vncBaseSize.w + 'px';
  rpVnc.style.height = vncBaseSize.h + 'px';
  rpVnc.style.transform = 'scale(' + scale.toFixed(4) + ')';
}
function scheduleFitVncFrame() {
  if (vncFitRaf) cancelAnimationFrame(vncFitRaf);
  vncFitRaf = requestAnimationFrame(() => {
    vncFitRaf = null;
    fitVncFrame();
  });
}

function logBrowserAction(action, detail) {
  if (actEmptyEl) actEmptyEl.style.display = 'none';
  const list = actionList || document.getElementById('actionList');
  const e = document.createElement('div'); e.className = 'action-entry';
  let dh = '';
  if (detail) dh = ' → <span class="val">' + esc(String(detail)) + '</span>';
  e.innerHTML = '<span class="act">' + action + '</span>' + dh;
  list.appendChild(e); list.scrollTop = list.scrollHeight;
  if (action === 'navigate' && detail) {
    if (rpUrl) rpUrl.textContent = String(detail);
  }
}

function addScreenshotThumb(src) {
  allScreenshots.push(src);
  if (ssEmptyEl) ssEmptyEl.style.display = 'none';
  const grid = ssGrid || document.getElementById('ssGrid');
  const img = document.createElement('img'); img.src = src;
  img.title = '截图 #' + allScreenshots.length;
  img.onclick = () => { openLightbox(src); };
  grid.appendChild(img);
}

// === Lightbox ===
function openLightbox(src) {
  if (lbImg) lbImg.src = src;
  if (lightbox) lightbox.classList.add('open');
}
function closeLightbox() {
  if (lightbox) lightbox.classList.remove('open');
  scheduleFitVncFrame();
}

// Click background to close lightbox
if (lightbox) {
  lightbox.addEventListener('click', function (e) {
    if (e.target === this) closeLightbox();
  });
}
function downloadLightbox() { if (lbImg) downloadImage(lbImg.src); }
function downloadImage(src) {
  const a = document.createElement('a'); a.href = src;
  a.download = 'screenshot-' + Date.now() + '.png';
  document.body.appendChild(a); a.click(); document.body.removeChild(a);
}

// === Agent Timeline ===
function ensureTimeline() {
  if (timeline) return;
  hideEmpty();
  timeline = document.createElement('div'); timeline.className = 'timeline';
  timeline.innerHTML = `
    <div class="timeline-header" onclick="this.parentElement.classList.toggle('collapsed')">
      <span class="t-indicator"></span>
      <span class="t-header-text">Agent 工作流</span>
      <span class="chevron">▼</span>
    </div>
    <div class="timeline-body" id="timelineBody"></div>`;
  inner.appendChild(timeline);
  timelineSteps = []; currentTimelineStep = null;
}

function addTimelineStep(phase, label, icon) {
  ensureTimeline();
  if (currentTimelineStep !== null && timelineSteps[currentTimelineStep]) {
    completeTimelineStepDOM(currentTimelineStep);
  }
  const body = document.getElementById('timelineBody');
  const idx = timelineSteps.length;
  const step = { phase, label, icon, status: 'active', detail: '', el: null, start: Date.now() };
  timelineSteps.push(step);
  currentTimelineStep = idx;

  const cls = { analyzing: 'a', executing: 'e', observing: 'o', responding: 'r' }[phase] || 'a';
  const div = document.createElement('div'); div.className = 't-step';
  div.innerHTML = `
    <div class="t-step-ind">
      <div class="t-step-icon ${cls}">${icon}</div>
      <div class="t-step-line"></div>
    </div>
    <div class="t-step-body">
      <div class="t-step-label">${label}</div>
      <div class="t-step-detail" id="tsd-${idx}"></div>
      <div class="t-step-time"></div>
    </div>
    <div class="t-step-status active">进行中</div>`;
  body.appendChild(div);
  step.el = div;
  scrollBottom();
  return idx;
}

function appendTimelineDetail(idx, text) {
  if (idx === null || idx >= timelineSteps.length) return;
  const step = timelineSteps[idx];
  step.detail += text;
  const el = document.getElementById('tsd-' + idx);
  if (el) {
    let display = step.detail;
    if (display.length > 400) display = display.slice(-400);
    el.textContent = display;
    el.scrollTop = el.scrollHeight;
  }
}

function completeTimelineStepDOM(idx) {
  if (idx === null || idx >= timelineSteps.length) return;
  const step = timelineSteps[idx];
  if (step.status === 'done') return;
  step.status = 'done';
  const elapsed = ((Date.now() - step.start) / 1000).toFixed(1);
  if (step.el) {
    const s = step.el.querySelector('.t-step-status');
    if (s) { s.textContent = '✓ ' + elapsed + 's'; s.className = 't-step-status done'; }
    const t = step.el.querySelector('.t-step-time');
    if (t) t.textContent = elapsed + 's';
  }
}

function finishTimeline(stopped) {
  if (currentTimelineStep !== null && timelineSteps[currentTimelineStep]) {
    completeTimelineStepDOM(currentTimelineStep);
    currentTimelineStep = null;
  }
  timelineSteps.forEach((step, i) => {
    if (step.status !== 'done') completeTimelineStepDOM(i);
  });
  if (timeline) {
    const dot = timeline.querySelector('.t-indicator');
    if (stopped) {
      dot.classList.add('stopped');
      const hdr = timeline.querySelector('.t-header-text');
      if (hdr) hdr.textContent = 'Agent 工作流 · 已停止';
    } else {
      dot.classList.add('done');
      const hdr = timeline.querySelector('.t-header-text');
      if (hdr) hdr.textContent = 'Agent 工作流 · 已完成';
    }
    setTimeout(() => { if (timeline) timeline.classList.add('collapsed'); }, 4000);
  }
}

// === Messages ===
function addUserBubble(text) {
  hideEmpty(); msgCount++; updateStats();
  const row = document.createElement('div'); row.className = 'msg-row user';
  row.innerHTML = '<div class="msg-meta">你 · ' + ts() + '</div><div class="msg-content"></div>';
  row.querySelector('.msg-content').textContent = text;
  inner.appendChild(row); scrollBottom();
  if (msgCount === 1 && topbarTitle) topbarTitle.textContent =
    text.length > 30 ? text.slice(0, 30) + '...' : text;
}

function addAssistantBubble() {
  hideEmpty(); msgCount++; updateStats();
  const row = document.createElement('div'); row.className = 'msg-row assistant';
  row.innerHTML = '<div class="msg-meta">AI · ' + ts() + '</div><div class="msg-content"></div>';
  inner.appendChild(row);
  return row.querySelector('.msg-content');
}

function addImageBubble(src) {
  hideEmpty(); addScreenshotThumb(src);

  // Container constrained to text width
  const wrap = document.createElement('div'); wrap.className = 'img-bubble';

  const img = document.createElement('img'); img.src = src; img.loading = 'lazy';
  img.alt = '截图'; img.title = '点击放大查看';
  img.onclick = () => openLightbox(src);

  // Caption bar with hint + download button
  const cap = document.createElement('div'); cap.className = 'img-caption';
  cap.innerHTML = '<span class="img-hint">点击图片放大查看</span>'
    + '<button onclick="event.stopPropagation();downloadImage(\'' + src + '\')">下载</button>';

  wrap.appendChild(img); wrap.appendChild(cap);
  inner.appendChild(wrap); scrollBottom();
}

let toolCardEl = null;
function addToolCard(tool, args) {
  hideEmpty();
  const card = document.createElement('div'); card.className = 'tool-card'; card.id = 'tc-' + tool;
  const aStr = args ? JSON.stringify(args).replace(/[{}"]/g, '').replace(/,/g, ', ').substring(0, 80) : '';
  card.innerHTML = `
    <span class="tc-icon">🔧</span>
    <div class="tc-info">
      <div class="tc-name">${tool}</div>
      ${aStr ? '<div class="tc-args">' + esc(aStr) + '</div>' : ''}
    </div>
    <span class="tc-status running">执行中</span>`;
  inner.appendChild(card); toolCardEl = card; scrollBottom();
}
function completeToolCard(tool, ok) {
  const card = document.getElementById('tc-' + tool);
  if (!card) return;
  const s = card.querySelector('.tc-status');
  if (s) { s.textContent = ok ? '✓' : '✗'; s.className = 'tc-status ' + (ok ? 'ok' : 'err'); }
  if (ok) card.classList.add('done-card');
  toolCount++; updateStats();
  setTimeout(() => { if (card.parentNode) card.remove(); }, 5000);
}

// === Markdown ===
function renderText(text) {
  let html = text
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\n/g, '<br>');
  html = html.replace(/```(\w*)\n?([\s\S]*?)```/g, '<pre><code>$2</code></pre>');
  return html;
}

// === Stop ===
async function stopExecution() {
  if (!sessionId) return;
  try {
    await fetch('/api/cancel?session_id=' + encodeURIComponent(sessionId), { method: 'POST' });
  } catch (e) { console.warn('Cancel request failed:', e); }
  if (abortController) {
    abortController.abort();
    abortController = null;
  }
}

// === Clear ===
function clearChat() {
  inner.querySelectorAll('.msg-row,.tool-card,.timeline,.img-bubble').forEach(e => e.remove());
  if (emptyState) emptyState.style.display = '';
  msgCount = 0; toolCount = 0; allScreenshots = [];
  timeline = null; timelineSteps = []; currentTimelineStep = null;
  if (ssGrid) ssGrid.innerHTML = ''; else document.getElementById('ssGrid').innerHTML = '';
  if (ssEmptyEl) ssEmptyEl.style.display = ''; else document.getElementById('ssEmpty').style.display = '';
  if (actionList) actionList.innerHTML = ''; else document.getElementById('actionList').innerHTML = '';
  if (actEmptyEl) actEmptyEl.style.display = ''; else document.getElementById('actEmpty').style.display = '';
  if (rpUrl) rpUrl.textContent = '等待导航...'; else document.getElementById('rpUrl').textContent = '等待导航...';
  closeRightPanel(); updateStats(); sessionId = '';
  const u = new URL(location); u.searchParams.delete('session_id');
  history.replaceState(null, '', u);
  if (sbSessionId) sbSessionId.textContent = '(新会话)';
  if (topbarTitle) topbarTitle.textContent = '新会话';
  setRunning(false);
}

function sendHint(t) { input.value = t; send(); }

// === Send ===
input.addEventListener('input', () => {
  input.style.height = 'auto';
  input.style.height = Math.min(input.scrollHeight, 160) + 'px';
});

async function send() {
  const text = input.value.trim();
  if (!text || sendBtn.disabled) return;

  addUserBubble(text);
  input.value = ''; input.style.height = 'auto';
  setRunning(true);

  const bubble = addAssistantBubble();
  bubble.innerHTML = '<div class="typing-dots"><span></span><span></span><span></span></div>';

  let fullText = '', hasError = false;
  timeline = null; timelineSteps = []; currentTimelineStep = null;
  let thinkingStepIdx = null;

  abortController = new AbortController();

  try {
    const resp = await fetch('/api/chat?session_id=' + encodeURIComponent(sessionId), {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text }),
      signal: abortController.signal,
    });
    if (!resp.ok) {
      if (resp.status === 499 || resp.type === 'aborted') throw new Error('已取消');
      throw new Error('服务器返回 ' + resp.status);
    }

    const newSid = resp.headers.get('X-Session-Id');
    if (newSid && !sessionId) {
      sessionId = newSid;
      const u = new URL(location); u.searchParams.set('session_id', sessionId);
      history.replaceState(null, '', u);
      if (sbSessionId) sbSessionId.textContent = sessionId;
    }

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let stopped = false;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n'); buffer = lines.pop() || '';

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        const payload = line.slice(6); if (!payload) continue;
        try {
          const ev = JSON.parse(payload);
          switch (ev.type) {

            case 'phase':
              if (ev.phase === 'analyzing') {
                thinkingStepIdx = addTimelineStep('analyzing', ev.label || '分析需求', '💭');
              } else if (ev.phase === 'executing') {
                addTimelineStep('executing', ev.label || '调用工具', '🔧');
                thinkingStepIdx = null;
              } else if (ev.phase === 'observing') {
                addTimelineStep('observing', ev.label || '分析结果', '👁');
                thinkingStepIdx = null;
              } else if (ev.phase === 'responding') {
                addTimelineStep('responding', '生成回复', '💬');
                thinkingStepIdx = null;
              }
              break;

            case 'thinking':
              if (thinkingStepIdx !== null) appendTimelineDetail(thinkingStepIdx, ev.content);
              break;

            case 'thinking_end':
              if (thinkingStepIdx !== null) { completeTimelineStepDOM(thinkingStepIdx); }
              break;

            case 'text':
              fullText += ev.content;
              bubble.innerHTML = renderText(fullText);
              scrollBottom();
              break;

            case 'image':
              addImageBubble(ev.src);
              break;

            case 'browser_action':
              openRightPanel();
              logBrowserAction(ev.action, ev.url || ev.selector || ev.text || ev.direction || '');
              break;

            case 'tool_start':
              addToolCard(ev.tool, ev.args);
              break;

            case 'tool_end':
              completeToolCard(ev.tool, true);
              break;

            case 'error':
              hasError = true; fullText = 'ERROR';
              stopped = ev.message.includes('取消');
              finishTimeline(stopped);
              bubble.innerHTML = '<div class="msg-error">⚠ ' + ev.message + '</div>';
              break;

            case 'done':
              break;
          }
        } catch (e) { console.warn('SSE:', e, payload); }
      }
    }
  } catch (err) {
    if (err.name === 'AbortError') {
      hasError = true; fullText = 'ERROR';
      finishTimeline(true);
      bubble.innerHTML = '<div class="msg-error">⚠ 执行已取消</div>';
    } else {
      hasError = true; fullText = 'ERROR';
      finishTimeline(false);
      bubble.innerHTML = '<div class="msg-error">⚠ 请求失败: ' + err.message + '</div>';
    }
  } finally {
    setRunning(false);
    finishTimeline(hasError);
    if (!fullText.trim()) {
      bubble.innerHTML = '<div class="msg-error">⚠ 未收到回复，请检查 API 密钥配置（.env 中的 LLM_PROVIDER 和 API_KEY）</div>';
    }
    input.focus();
  }
}

input.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
});
document.addEventListener('keydown', e => {
  if (e.ctrlKey && e.key === 'b') { e.preventDefault(); toggleSidebar(); }
  if (e.key === 'Escape') {
    if (document.fullscreenElement) return;
    closeLightbox(); closeSidebar(); closeRightPanel();
  }
});

document.addEventListener('fullscreenchange', () => {
  const isFullscreen = !!document.fullscreenElement;
  if (rightPanel) {
    rightPanel.classList.toggle('max', isFullscreen);
  }
  document.body.classList.toggle('panel-max', isFullscreen);
  if (panelSplitter) panelSplitter.style.display = isFullscreen ? 'none' : (rightPanel && rightPanel.classList.contains('open') ? 'block' : 'none');
  if (panelSizeHint) {
    const value = isFullscreen ? '100%' : Math.round((rightPanel.offsetWidth / window.innerWidth) * 100) + '%';
    showPanelSizeHint(value, !isFullscreen);
  }
  scheduleFitVncFrame();
});

// ======================================================================
// RESIZABLE PANELS
// ======================================================================

// --- Sidebar resize ---
(function initSidebarResize() {
  if (!sidebarResizeHandle || !sidebar) return;
  let startX = 0, startW = 0, dragging = false;

  sidebarResizeHandle.addEventListener('mousedown', (e) => {
    e.preventDefault();
    dragging = true;
    startX = e.clientX;
    startW = sidebar.offsetWidth;
    sidebarResizeHandle.classList.add('active');
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  });

  document.addEventListener('mousemove', (e) => {
    if (!dragging) return;
    const delta = e.clientX - startX;
    let newW = startW + delta;
    newW = Math.max(180, Math.min(420, newW));
    sidebar.style.width = newW + 'px';
  });

  document.addEventListener('mouseup', () => {
    if (!dragging) return;
    dragging = false;
    sidebarResizeHandle.classList.remove('active');
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
  });
})();

// --- Center splitter resize ---
(function initPanelSplitter() {
  if (!panelSplitter || !rightPanel) return;
  let dragging = false;
  let startX = 0;
  let startW = 0;

  const openIfNeeded = () => {
    if (!rightPanel.classList.contains('open')) {
      openRightPanel();
    }
  };

  panelSplitter.addEventListener('mousedown', (e) => {
    e.preventDefault();
    openIfNeeded();
    dragging = true;
    startX = e.clientX;
    startW = rightPanel.offsetWidth || parseInt(getComputedStyle(document.body).getPropertyValue('--panel-w'), 10) || 720;
    panelDragState = { type: 'splitter' };
    panelSplitter.classList.add('active');
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  });

  document.addEventListener('mousemove', (e) => {
    if (!dragging) return;
    const delta = startX - e.clientX;
    const next = startW + delta;
    syncPanelWidth(next);
  });

  document.addEventListener('mouseup', () => {
    if (!dragging) return;
    dragging = false;
    panelDragState = null;
    panelSplitter.classList.remove('active');
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
    scheduleFitVncFrame();
  });
})();

if (vncContainer && 'ResizeObserver' in window) {
  const vncResizeObserver = new ResizeObserver(() => scheduleFitVncFrame());
  vncResizeObserver.observe(vncContainer);
  if (rightPanel) vncResizeObserver.observe(rightPanel);
}

window.addEventListener('resize', () => {
  if (rightPanel.classList.contains('open') && !rightPanel.classList.contains('max') && !panelDragState && !panelWidthManual) {
    updatePanelWidth();
  }
  scheduleFitVncFrame();
});

// --- VNC height resize ---
(function initVncResize() {
  if (!vncResizeHandle || !vncContainer || !rightPanel) return;
  let startY = 0, startH = 0, dragging = false;

  // Show handle when right panel is open
  const observer = new MutationObserver(() => {
    vncResizeHandle.style.display = rightPanel.classList.contains('open') ? 'block' : 'none';
  });
  observer.observe(rightPanel, { attributes: true, attributeFilter: ['class'] });

  vncResizeHandle.addEventListener('mousedown', (e) => {
    e.preventDefault();
    dragging = true;
    startY = e.clientY;
    startH = vncContainer.offsetHeight;
    vncResizeHandle.classList.add('active');
    document.body.style.cursor = 'row-resize';
    document.body.style.userSelect = 'none';
  });

  document.addEventListener('mousemove', (e) => {
    if (!dragging) return;
    const delta = e.clientY - startY;
    let newH = startH + delta;
    newH = Math.max(120, Math.min(600, newH));
    vncContainer.style.height = newH + 'px';
    scheduleFitVncFrame();
  });

  document.addEventListener('mouseup', () => {
    if (!dragging) return;
    dragging = false;
    vncResizeHandle.classList.remove('active');
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
    scheduleFitVncFrame();
  });
})();

// --- Touch support for mobile ---
(function initTouchResize() {
  if (!sidebarResizeHandle || !sidebar) return;

  sidebarResizeHandle.addEventListener('touchstart', (e) => {
    const touch = e.touches[0];
    sidebarResizeHandle._touchStartX = touch.clientX;
    sidebarResizeHandle._touchStartW = sidebar.offsetWidth;
  });

  sidebarResizeHandle.addEventListener('touchmove', (e) => {
    if (sidebarResizeHandle._touchStartX === undefined) return;
    const touch = e.touches[0];
    const delta = touch.clientX - sidebarResizeHandle._touchStartX;
    let newW = sidebarResizeHandle._touchStartW + delta;
    newW = Math.max(180, Math.min(420, newW));
    sidebar.style.width = newW + 'px';
  });

  sidebarResizeHandle.addEventListener('touchend', () => {
    sidebarResizeHandle._touchStartX = undefined;
  });
})();
