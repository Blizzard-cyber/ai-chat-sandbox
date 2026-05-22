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
const sbSessionId = document.getElementById('sbSessionId');
const topbarModel = document.getElementById('topbarModel');
const topbarTitle = document.getElementById('topbarTitle');
const inputFooter = document.getElementById('inputFooter');
const sidebar = document.getElementById('sidebar');
const sidebarOverlay = document.getElementById('sidebarOverlay');
const sidebarResizeHandle = document.getElementById('sidebarResizeHandle');
const rpVnc = document.getElementById('rpVnc');
const rpVscode = document.getElementById('rpVscode');
const rpUrl = document.getElementById('rpUrl');
const ssGrid = document.getElementById('ssGrid');
const actionList = document.getElementById('actionList');
const actEmptyEl = document.getElementById('actEmpty');
const ssEmptyEl = document.getElementById('ssEmpty');
const vncContainer = document.getElementById('vncContainer');
const vscodeContainer = document.getElementById('vscodeContainer');
const vncFrame = document.getElementById('vncFrame');
const vncResizeHandle = document.getElementById('vncResizeHandle');
const rpDrawer = document.getElementById('rpDrawer');
const panelSplitter = document.getElementById('panelSplitter');
const lightbox = document.getElementById('lightbox');
const lbImg = document.getElementById('lbImg');

let sessionId = new URLSearchParams(location.search).get('session_id') || '';
let msgCount = 0, toolCount = 0, allScreenshots = [];
let currentFlowCard = null, currentIteration = 0, currentPhaseStep = null, reasoningText = '';
let abortController = null;  // For cancellation
let panelHintTimer = null;
let vncBaseSize = { w: 1280, h: 720 };
let panelDragState = null;
let panelWidthManual = false;
let vncFitRaf = null;
let sandboxBaseUrl = '';

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
    const sbf = document.getElementById('sbFooterModel');
    if (sbf) sbf.textContent = (c.provider === 'openai' ? 'OpenAI 兼容' : c.provider) + ' · ' + c.model;
    if (topbarModel) topbarModel.textContent = c.model;
    if (sbSessionId) sbSessionId.textContent = sessionId || '(新会话)';
    if (inputFooter) {
      inputFooter.textContent =
        (c.provider === 'openai' ? 'OpenAI 兼容' : c.provider) + ' · ' +
        c.model + (c.sandbox_enabled ? ' · 沙箱就绪' : '');
    }

    if (c.sandbox_enabled && c.sandbox_url) {
      const base = c.sandbox_url.replace(/\/$/, '');
      sandboxBaseUrl = base;
      const vncUrl = base + '/vnc/index.html?autoconnect=true';
      if (rpVnc) {
                setVncStatus('正在连接沙箱桌面...', true);
        rpVnc.src = vncUrl;
        rpVnc.addEventListener('load', () => {
          setTimeout(() => setVncStatus('已加载沙箱桌面', false), 600);
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
  setVncStatus('正在刷新沙箱桌面...', true);
  // reload iframe
  rpVnc.src = rpVnc.src;
  scheduleFitVncFrame();
}
function switchSandboxView(view) {
  document.querySelectorAll('.rp-view-btn').forEach(b => b.classList.toggle('active', b.dataset.view === view));
  if (vncContainer) vncContainer.style.display = view === 'vnc' ? 'flex' : 'none';
  if (vscodeContainer) vscodeContainer.style.display = view === 'vscode' ? 'flex' : 'none';
  if (rpUrl) rpUrl.style.display = view === 'vnc' ? 'block' : 'none';
  if (view === 'vscode') {
    if (rpVscode && !rpVscode.src && sandboxBaseUrl) {
      rpVscode.src = sandboxBaseUrl + '/code-server/';
    }
    scheduleFitVncFrame();
  }
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

// === Flow Card Functions ===
function createFlowCard(iteration) {
  hideEmpty();
  const card = document.createElement('div');
  card.className = 'flow-card';
  card.dataset.round = iteration;
  card.innerHTML = `
    <div class="fc-header" onclick="toggleCard(this.parentElement)">
      <span class="fc-title"><span class="fc-round-num">${iteration}</span> 第 ${iteration} 轮 <span class="fc-chevron">▼</span></span>
      <span class="fc-status active">进行中</span>
    </div>
    <div class="fc-steps"></div>
    <div class="fc-results"></div>`;
  inner.appendChild(card);
  currentFlowCard = card;
  currentPhaseStep = null;
  scrollBottom();
}

function toggleCard(card) {
  card.classList.toggle('collapsed');
}

function addFlowStep(phase, label) {
  if (!currentFlowCard) return null;
  // Auto-complete previous step
  if (currentPhaseStep) {
    const st = currentPhaseStep.querySelector('.fc-step-status');
    const dot = currentPhaseStep.querySelector('.fc-step-dot');
    if (st && st.classList.contains('active')) {
      st.textContent = '✓'; st.className = 'fc-step-status done';
    }
    if (dot) dot.classList.add('done');
  }
  const stepsEl = currentFlowCard.querySelector('.fc-steps');
  const step = document.createElement('div');
  step.className = 'fc-step';
  step.dataset.phase = phase;
  step.innerHTML = `
    <div class="fc-step-ind">
      <div class="fc-step-dot ${phase}"></div>
      <div class="fc-step-line"></div>
    </div>
    <div class="fc-step-body">
      <div class="fc-step-label ${phase}">${label}</div>
      <div class="fc-step-detail"></div>
    </div>
    <div class="fc-step-status active">⏳</div>`;
  stepsEl.appendChild(step);
  currentPhaseStep = step;
  scrollBottom();
  return step;
}

function setStepDetail(phase, text) {
  if (!currentFlowCard) return;
  const step = currentFlowCard.querySelector(`.fc-step[data-phase="${phase}"]`);
  if (!step) return;
  const detail = step.querySelector('.fc-step-detail');
  if (detail) detail.textContent = text;
}

function completeAllSteps() {
  if (!currentFlowCard) return;
  currentFlowCard.querySelectorAll('.fc-step-status.active').forEach(s => {
    s.textContent = '✓'; s.className = 'fc-step-status done';
  });
  currentFlowCard.querySelectorAll('.fc-step-dot:not(.done)').forEach(d => d.classList.add('done'));
  currentPhaseStep = null;
}

function addResultToCard(type, data) {
  if (!currentFlowCard) return;
  const results = currentFlowCard.querySelector('.fc-results');
  const card = document.createElement('div');
  card.className = 'rc-card success';
  if (type === 'image') {
    addScreenshotThumb(data.src);
    card.innerHTML = `
      <div class="rc-header"><span class="rc-left">📸 截图结果</span><span class="rc-right"></span></div>
      <div class="rc-body"><img src="${data.src}" alt="截图" onerror="this.style.display='none'" onclick="openLightbox(this.src)"></div>`;
  } else if (type === 'error') {
    card.className = 'rc-card fail';
    card.innerHTML = `
      <div class="rc-header"><span class="rc-left">⚠ 执行出错</span><span class="rc-right"></span></div>
      <div class="rc-body"><div class="rc-log" style="color:var(--error)">${esc(data)}</div></div>`;
  } else if (type === 'log') {
    card.innerHTML = `
      <div class="rc-header"><span class="rc-left">📋 执行输出</span><span class="rc-right"></span></div>
      <div class="rc-body"><div class="rc-log">${esc(data)}</div></div>`;
  } else if (type === 'download') {
    card.innerHTML = `
      <div class="rc-header"><span class="rc-left">📥 文件下载</span><span class="rc-right"></span></div>
      <div class="rc-body"><a href="${esc(data.src)}" target="_blank" class="dl-link" download="${esc(data.name)}">⬇️ ${esc(data.name)}</a></div>`;
  }
  results.appendChild(card);
  scrollBottom();
}

function setFlowText(text) {
  if (!currentFlowCard) return;
  let el = currentFlowCard.querySelector('.fc-text');
  if (!el) {
    el = document.createElement('div');
    el.className = 'fc-text';
    currentFlowCard.appendChild(el);
  }
  el.innerHTML = renderText(text);
  scrollBottom();
}

function navigateToRound(iteration) {
  const card = document.querySelector(`.flow-card[data-round="${iteration}"]`);
  if (!card) return;
  card.classList.remove('collapsed');
  card.scrollIntoView({ behavior: 'smooth', block: 'start' });
  if (window.innerWidth <= 900) closeSidebar();
}

function addSidebarRound(userMsg, iteration, status) {
  const list = document.getElementById('roundList');
  const empty = document.getElementById('roundEmpty');
  if (empty) empty.style.display = 'none';
  // Update existing or create new
  let item = list.querySelector(`.round-nav-item[data-round="${iteration}"]`);
  if (!item) {
    item = document.createElement('div');
    item.className = 'round-nav-item';
    item.dataset.round = iteration;
    item.addEventListener('click', () => navigateToRound(iteration));
    list.appendChild(item);
  }
  const badgeCls = status === 'done' ? 'done' : (status === 'fail' ? 'fail' : 'running');
  const badgeTxt = status === 'done' ? '✓' : (status === 'fail' ? '✗' : '○');
  const shortMsg = userMsg.length > 36 ? userMsg.slice(0, 36) + '…' : userMsg;
  item.innerHTML = `
    <div class="rni-top">
      <span class="rni-badge ${badgeCls}">${badgeTxt}</span>
      <span class="rni-text">${esc(shortMsg)}</span>
    </div>
    <div class="rni-meta">
      <span>第 ${iteration} 轮</span>
      <span>${status === 'done' ? '已完成' : status === 'fail' ? '已失败' : '进行中'}</span>
    </div>`;
}

function showFinalResult(text, screenshots, usage, elapsed) {
  if (!text && screenshots.length === 0) return;
  const div = document.createElement('div');
  div.className = 'final-result';

  const total = usage ? (usage.total_tokens || (usage.prompt_tokens || 0) + (usage.completion_tokens || 0)) : 0;
  const tokenStr = total >= 1000 ? (total / 1000).toFixed(1) + 'k' : String(total);

  let html = '<div class="fr-header">' +
    '<span class="fr-status">✓ 任务完成</span>' +
    '<span class="fr-summary"><span>' + elapsed + 's</span><span>' + screenshots.length + ' 张截图</span><span>~' + tokenStr + ' tokens</span></span>' +
    '</div><div class="fr-body">';

  // Text first
  if (text) {
    html += '<div class="fr-text">' + renderText(text) + '</div>';
  }

  // Screenshots below text, shown as clickable thumbnails
  if (screenshots.length > 0) {
    const unique = screenshots.filter((s, i) => screenshots.indexOf(s) === i);
    html += '<div class="fr-gallery">' +
      '<div class="fr-gallery-label">📸 截图 ' + unique.length + ' 张</div>' +
      '<div class="fr-gallery-grid" id="frGallery' + Date.now() + '"></div></div>';
  }

  html += '</div>';
  div.innerHTML = html;

  // Attach gallery click handlers (safe, no inline on* attributes)
  if (screenshots.length > 0) {
    const grid = div.querySelector('.fr-gallery-grid');
    if (grid) {
      const unique = screenshots.filter((s, i) => screenshots.indexOf(s) === i);
      unique.forEach((src) => {
        const item = document.createElement('div');
        item.className = 'fr-gallery-item';
        item.addEventListener('click', () => openLightbox(src));
        const img = document.createElement('img');
        img.src = src;
        img.alt = '截图';
        img.onerror = () => { item.style.display = 'none'; };
        const num = document.createElement('span');
        num.className = 'fr-gallery-num';
        item.appendChild(img);
        item.appendChild(num);
        grid.appendChild(item);
      });
    }
  }

  inner.appendChild(div);
  scrollBottom();
}

// === Messages ===
function addUserBubble(text) {
  hideEmpty(); msgCount++; updateStats();
  const row = document.createElement('div'); row.className = 'msg-row user';
  row.innerHTML = `
    <div class="msg-shell">
      <div class="msg-avatar user">我</div>
      <div class="msg-card">
        <div class="msg-head">
          <span class="msg-title">你</span>
          <span class="msg-time">${ts()}</span>
        </div>
        <div class="msg-content"></div>
        <div class="msg-footer"><span class="token-pill subtle">已发送</span></div>
      </div>
    </div>`;
  row.querySelector('.msg-content').textContent = text;
  inner.appendChild(row); scrollBottom();
  if (msgCount === 1 && topbarTitle) topbarTitle.textContent =
    text.length > 30 ? text.slice(0, 30) + '...' : text;
}

function addNoticeBubble(msg) {
  const el = document.createElement('div'); el.className = 'notice-bubble';
  el.textContent = '📌 ' + msg;
  inner.appendChild(el); scrollBottom();
}

// === Markdown ===
function renderText(text) {
  // Escape HTML first, then apply markdown
  let html = esc(text)
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
async function clearChat() {
  // Delete server-side session + screenshots
  if (sessionId) {
    try {
      await fetch('/api/session?session_id=' + encodeURIComponent(sessionId), { method: 'DELETE' });
    } catch (e) { /* ignore */ }
  }
  inner.querySelectorAll('.msg-row,.flow-card,.final-result,.notice-bubble').forEach(e => e.remove());
  if (emptyState) emptyState.style.display = '';
  msgCount = 0; toolCount = 0; allScreenshots = [];
  currentFlowCard = null; currentIteration = 0; currentPhaseStep = null; reasoningText = '';
  if (ssGrid) ssGrid.innerHTML = ''; else document.getElementById('ssGrid').innerHTML = '';
  if (ssEmptyEl) ssEmptyEl.style.display = ''; else document.getElementById('ssEmpty').style.display = '';
  if (actionList) actionList.innerHTML = ''; else document.getElementById('actionList').innerHTML = '';
  if (actEmptyEl) actEmptyEl.style.display = ''; else document.getElementById('actEmpty').style.display = '';
  const rl = document.getElementById('roundList');
  if (rl) { rl.querySelectorAll('.round-nav-item').forEach(e => e.remove()); }
  const re = document.getElementById('roundEmpty');
  if (re) re.style.display = '';
  const sft = document.getElementById('sbFooterTokens');
  if (sft) sft.textContent = '0 tokens';
  if (rpUrl) rpUrl.textContent = '等待操作...'; else document.getElementById('rpUrl').textContent = '等待操作...';
  closeRightPanel(); updateStats(); sessionId = '';
  const u = new URL(location); u.searchParams.delete('session_id');
  history.replaceState(null, '', u);
  if (sbSessionId) sbSessionId.textContent = '(新会话)';
  if (topbarTitle) topbarTitle.textContent = '新会话';
  setRunning(false);
}

function sendHint(t) { input.value = t; send(); }

// === Upload ===
document.getElementById('fileInput').addEventListener('change', async function(e) {
  const file = e.target.files[0];
  if (!file) return;
  if (!sessionId) {
    addNoticeBubble('请先发送一条消息建立会话后再上传文件');
    return;
  }
  const formData = new FormData();
  formData.append('session_id', sessionId);
  formData.append('file', file);
  try {
    addNoticeBubble(`正在上传 ${file.name}...`);
    const resp = await fetch('/api/upload', { method: 'POST', body: formData });
    if (!resp.ok) throw new Error(await resp.text());
    const result = await resp.json();
    addNoticeBubble(`✅ 文件 ${result.filename} 已上传到沙箱（${(result.size / 1024).toFixed(1)}KB）`);
  } catch (err) {
    addNoticeBubble(`❌ 上传失败: ${err.message}`);
  }
  this.value = '';
});

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

  // Reset flow card state
  currentFlowCard = null; currentIteration = 0; currentPhaseStep = null;
  reasoningText = '';
  let fullText = '', hasError = false, usageData = null;
  const startTime = Date.now();
  const execScreenshots = [];

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

            case 'phase': {
              const phase = ev.phase;
              const iteration = ev.iteration;
              // New iteration → new flow card
              if (iteration && iteration !== currentIteration) {
                if (currentFlowCard) {
                  completeAllSteps();
                  addSidebarRound(text, currentIteration, 'done');
                }
                currentIteration = iteration;
                createFlowCard(iteration);
              }
              const labels = { 'analyzing': '分析', 'executing': '执行', 'observing': '观察', 'responding': '回复' };
              addFlowStep(phase, labels[phase] || phase);
              if (ev.label) {
                setStepDetail(phase, ev.label.replace(/第 \d+ 轮[:：]?\s*/, ''));
              }
              break;
            }

            case 'thinking':
              reasoningText += ev.content;
              // Show latest reasoning snippet in analyze step detail
              if (currentFlowCard) {
                const st = currentFlowCard.querySelector('.fc-step[data-phase="analyze"] .fc-step-detail');
                if (st) {
                  let txt = reasoningText;
                  if (txt.length > 200) txt = '…' + txt.slice(-200);
                  st.textContent = txt;
                }
              }
              break;

            case 'thinking_end':
              if (reasoningText && currentFlowCard) {
                const rBlock = document.createElement('details');
                rBlock.className = 'fc-reasoning';
                rBlock.innerHTML = '<summary>🧠 思考过程</summary><div class="fc-reasoning-content">' + esc(reasoningText) + '</div>';
                const steps = currentFlowCard.querySelector('.fc-steps');
                if (steps) steps.after(rBlock);
                reasoningText = '';
              }
              // Complete analyze step
              if (currentPhaseStep && currentPhaseStep.dataset.phase === 'analyze') {
                const st = currentPhaseStep.querySelector('.fc-step-status');
                const dot = currentPhaseStep.querySelector('.fc-step-dot');
                if (st && st.classList.contains('active')) { st.textContent = '✓'; st.className = 'fc-step-status done'; }
                if (dot) dot.classList.add('done');
                currentPhaseStep = null;
              }
              break;

            case 'text':
              fullText += ev.content;
              setFlowText(fullText);
              break;

            case 'image':
              if (!execScreenshots.includes(ev.src)) {
                execScreenshots.push(ev.src);
                addResultToCard('image', { src: ev.src });
              }
              break;

            case 'file':
              addResultToCard('download', { src: ev.src, name: ev.name || 'download' });
              break;

            case 'browser_action':
              if (ev.action === 'open_vscode') {
                openRightPanel();
                switchSandboxView('vscode');
                break;
              }
              openRightPanel();
              logBrowserAction(ev.action, ev.detail || ev.url || ev.selector || ev.text || ev.direction || '');
              break;

            case 'tool_start':
              setStepDetail('execute', ev.tool + '(' + (ev.args ? JSON.stringify(ev.args).substring(0, 100) : '') + ')');
              break;

            case 'tool_end':
              toolCount++; updateStats();
              break;

            case 'usage':
              usageData = ev;
              {
                const sft = document.getElementById('sbFooterTokens');
                if (sft) {
                  const total = (ev.total_tokens || (ev.prompt_tokens || 0) + (ev.completion_tokens || 0));
                  sft.textContent = '~' + (total >= 1000 ? (total / 1000).toFixed(1) + 'k' : total) + ' tokens';
                }
              }
              break;

            case 'notice':
              addNoticeBubble(ev.message);
              break;

            case 'error':
              hasError = true;
              addResultToCard('error', ev.message);
              if (currentFlowCard) {
                const se = currentFlowCard.querySelector('.fc-status');
                if (se) { se.textContent = '已失败'; se.className = 'fc-status fail'; }
              }
              break;

            case 'done':
              break;
          }
        } catch (e) { console.warn('SSE:', e, payload); }
      }
    }
  } catch (err) {
    hasError = true;
    if (!currentFlowCard) createFlowCard(1);
    const msg = err.name === 'AbortError' ? '执行已取消' : '请求失败: ' + err.message;
    addResultToCard('error', msg);
    if (currentFlowCard) {
      const se = currentFlowCard.querySelector('.fc-status');
      if (se) { se.textContent = '已失败'; se.className = 'fc-status fail'; }
    }
  } finally {
    setRunning(false);
    if (currentFlowCard) {
      completeAllSteps();
      if (!hasError && !fullText.trim() && !currentFlowCard.querySelector('.fc-text')) {
        addResultToCard('error', '未收到回复，请检查 API 密钥配置（.env 中的 LLM_PROVIDER 和 API_KEY）');
        hasError = true;
      }
      // Collapse all process cards and show final result
      document.querySelectorAll('.flow-card').forEach(c => c.classList.add('collapsed'));
      if (!hasError && (fullText.trim() || execScreenshots.length > 0)) {
        const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
        showFinalResult(fullText, execScreenshots, usageData, elapsed);
      }
      addSidebarRound(text, currentIteration, hasError ? 'fail' : 'done');
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
