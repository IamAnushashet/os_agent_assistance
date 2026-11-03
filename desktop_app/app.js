/**
 * NEXUS OS AGENT — Desktop Controller & Real-Time Deck Engine
 * Powers live telemetry SVG dials, multi-agent matrix tabs,
 * automated PPTX & PDF document studio, browser credentials login, and phone remote.
 */

const API_BASE = window.location.origin.startsWith('http') ? window.location.origin : 'http://127.0.0.1:8000';

let activeTaskId = null;
let pollTimer = null;
let telemetryTimer = null;
let isEmergencyStopped = false;

// DOM Elements — Command Deck
const valCpu = document.getElementById('val-cpu');
const valRam = document.getElementById('val-ram');
const valDisk = document.getElementById('val-disk');
const gaugeCpu = document.getElementById('gauge-cpu');
const gaugeRam = document.getElementById('gauge-ram');
const gaugeDisk = document.getElementById('gauge-disk');

const displayModel = document.getElementById('display-model');
const btnToggleHud = document.getElementById('btn-toggle-hud');
const btnConnectPhone = document.getElementById('btn-connect-phone');
const btnEmergencyStop = document.getElementById('btn-emergency-stop');
const btnOpenSettings = document.getElementById('btn-open-settings');

// Tabs
const matrixTabs = document.querySelectorAll('.matrix-tab');
const tabPanes = document.querySelectorAll('.tab-pane');
const browserTabCount = document.getElementById('browser-tab-count');

// Console DOM
const chatViewport = document.getElementById('chat-viewport');
const messageThread = document.getElementById('message-thread');
const welcomeCard = document.getElementById('welcome-card');
const promptInput = document.getElementById('prompt-input');
const btnSend = document.getElementById('btn-send');
const btnMic = document.getElementById('btn-mic');
const selectPermissionMode = document.getElementById('select-permission-mode');
const historyList = document.getElementById('history-list');
const lanDisplay = document.getElementById('lan-display');
const btnNewTask = document.getElementById('btn-new-task');
const btnClearTasks = document.getElementById('btn-clear-tasks');

// Browser Deck DOM
const btnRefreshTabs = document.getElementById('btn-refresh-tabs');
const tabsListContainer = document.getElementById('tabs-list-container');
const loginUrl = document.getElementById('login-url');
const loginUsername = document.getElementById('login-username');
const loginPassword = document.getElementById('login-password');
const btnExecLogin = document.getElementById('btn-exec-login');
const btnOpenBrowser = document.getElementById('btn-open-browser');
const loginResultBox = document.getElementById('login-result-box');

// Document Studio DOM
const inputPptxTopic = document.getElementById('input-pptx-topic');
const btnCreatePptx = document.getElementById('btn-create-pptx');
const inputDocxTopic = document.getElementById('input-docx-topic');
const btnCreateDocx = document.getElementById('btn-create-docx');
const inputXlsxTopic = document.getElementById('input-xlsx-topic');
const btnCreateXlsx = document.getElementById('btn-create-xlsx');
const inputPdfTitle = document.getElementById('input-pdf-title');
const btnCreatePdf = document.getElementById('btn-create-pdf');
const btnRefreshDocs = document.getElementById('btn-refresh-docs');
const btnClearAllDocs = document.getElementById('btn-clear-all-docs');
const docsGallery = document.getElementById('docs-gallery');

// Audit & Logs DOM
const btnRefreshLogs = document.getElementById('btn-refresh-logs');
const btnClearLogs = document.getElementById('btn-clear-logs');
const logsContainer = document.getElementById('logs-container');
const logCountBadge = document.getElementById('log-count-badge');
const auditLogStats = document.getElementById('audit-log-stats');

// System Deck DOM
const sysCpuVal = document.getElementById('sys-cpu-val');
const sysRamVal = document.getElementById('sys-ram-val');
const sysRamGb = document.getElementById('sys-ram-gb');
const sysDiskVal = document.getElementById('sys-disk-val');
const sysDiskGb = document.getElementById('sys-disk-gb');
const btnRefreshTelemetry = document.getElementById('btn-refresh-telemetry');

// Vision Deck DOM
const btnCaptureVision = document.getElementById('btn-capture-vision');
const visionScreenImg = document.getElementById('vision-screen-img');
const visionTextOutput = document.getElementById('vision-text-output');
const btnRefreshPreview = document.getElementById('btn-refresh-preview');

// Floating HUD DOM
const floatingHudBar = document.getElementById('floating-hud-bar');
const hudInput = document.getElementById('hud-input');
const hudBtnSend = document.getElementById('hud-btn-send');
const hudBtnMic = document.getElementById('hud-btn-mic');
const hudBtnClose = document.getElementById('hud-btn-close');

// Modals DOM
const phoneModal = document.getElementById('phone-modal');
const btnClosePhone = document.getElementById('btn-close-phone');
const btnDonePhone = document.getElementById('btn-done-phone');
const pairingQrImg = document.getElementById('pairing-qr-img');
const lanUrlInput = document.getElementById('lan-url-input');
const btnCopyUrl = document.getElementById('btn-copy-url');
const displayPairingPin = document.getElementById('display-pairing-pin');
const btnOpenRemoteTab = document.getElementById('btn-open-remote-tab');

const settingsModal = document.getElementById('settings-modal');
const btnCloseSettings = document.getElementById('btn-close-settings');
const btnSaveSettings = document.getElementById('btn-save-settings');
const selectProvider = document.getElementById('select-provider');
const inputGeminiKey = document.getElementById('input-gemini-key');
const inputGroqKey = document.getElementById('input-groq-key');
const inputPin = document.getElementById('input-pin');
const selectVoice = document.getElementById('select-voice');

// =========================================================================
// 1. INITIALIZATION & TELEMETRY
// =========================================================================
async function init() {
  setupEventListeners();
  setupTabs();
  
  await fetchStatusAndNetwork();
  await updateTelemetry();
  await loadRecentTasks();
  await loadDocuments();
  await loadBrowserTabs();
  await loadAuditLogs();

  // Polling intervals
  telemetryTimer = setInterval(updateTelemetry, 3000);
}

async function fetchStatusAndNetwork() {
  try {
    const res = await fetch(`${API_BASE}/api/status`);
    const data = await res.json();
    if (data.llm) {
      displayModel.innerHTML = `<span class="pulse-dot online"></span><span>⚡ ${data.llm.chat_model}</span>`;
    }
    if (data.emergency_stopped) {
      setEmergencyStoppedUI(true);
    }

    const netRes = await fetch(`${API_BASE}/api/network-info`);
    const netData = await netRes.json();
    lanDisplay.innerText = `LAN: ${netData.ip}:${netData.port} • PIN: ${netData.pairing_pin}`;
    lanUrlInput.value = netData.remote_url;
    displayPairingPin.innerText = netData.pairing_pin;
    
    // QR Code for LAN phone pairing
    pairingQrImg.src = `https://api.qrserver.com/v1/create-qr-code/?size=180x180&data=${encodeURIComponent(netData.remote_url)}`;
  } catch (e) {
    lanDisplay.innerText = "Connecting to agent core...";
  }
}

async function updateTelemetry() {
  try {
    const res = await fetch(`${API_BASE}/api/telemetry`);
    const data = await res.json();
    if (!data.success) return;

    // CPU Gauge
    const cpu = Math.round(data.cpu_percent || 0);
    valCpu.innerText = `${cpu}%`;
    gaugeCpu.setAttribute('stroke-dasharray', `${cpu}, 100`);
    if (sysCpuVal) sysCpuVal.innerText = `${cpu}%`;

    // RAM Gauge
    const ram = Math.round(data.ram_percent || 0);
    valRam.innerText = `${ram}%`;
    gaugeRam.setAttribute('stroke-dasharray', `${ram}, 100`);
    if (sysRamVal) sysRamVal.innerText = `${ram}%`;
    if (sysRamGb) sysRamGb.innerText = `${data.ram_used_gb} / ${data.ram_total_gb} GB`;

    // Disk Gauge
    const disk = Math.round(data.disk_percent || 0);
    valDisk.innerText = `${disk}%`;
    gaugeDisk.setAttribute('stroke-dasharray', `${disk}, 100`);
    if (sysDiskVal) sysDiskVal.innerText = `${disk}%`;
    if (sysDiskGb) sysDiskGb.innerText = `${data.disk_used_gb} GB used of ${data.disk_total_gb} GB`;
  } catch (e) {}
}

// =========================================================================
// 2. TAB NAVIGATION
// =========================================================================
function setupTabs() {
  matrixTabs.forEach(btn => {
    btn.addEventListener('click', () => {
      const targetId = btn.getAttribute('data-tab');
      matrixTabs.forEach(b => b.classList.remove('active'));
      tabPanes.forEach(p => p.classList.remove('active'));

      btn.classList.add('active');
      const pane = document.getElementById(targetId);
      if (pane) pane.classList.add('active');

      if (targetId === 'tab-browser') loadBrowserTabs();
      if (targetId === 'tab-documents') loadDocuments();
      if (targetId === 'tab-vision') refreshVisionPreview();
      if (targetId === 'tab-logs') loadAuditLogs();
    });
  });
}

// =========================================================================
// 3. CONSOLE & PROMPT EXECUTION
// =========================================================================
async function submitPrompt(text) {
  const prompt = (text || promptInput.value || hudInput.value).trim();
  if (!prompt) return;

  welcomeCard.style.display = 'none';
  appendUserMessage(prompt);
  promptInput.value = '';
  hudInput.value = '';

  const permMode = selectPermissionMode.value;
  const taskCard = createTaskCard(prompt);
  messageThread.appendChild(taskCard);
  chatViewport.scrollTop = chatViewport.scrollHeight;

  try {
    const res = await fetch(`${API_BASE}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        messages: [{ role: "user", content: prompt }],
        permission_mode: permMode
      })
    });
    const data = await res.json();
    activeTaskId = data.task_id;
    pollTaskStatus(activeTaskId, taskCard);
    loadRecentTasks();
  } catch (e) {
    taskCard.querySelector('.task-status').innerText = "Network Error";
    taskCard.querySelector('.task-status').className = "task-status failed";
  }
}

function appendUserMessage(text) {
  const msg = document.createElement('div');
  msg.className = 'message-user';
  msg.innerText = text;
  messageThread.appendChild(msg);
}

function createTaskCard(prompt) {
  const card = document.createElement('div');
  card.className = 'task-card';
  card.innerHTML = `
    <div class="task-header">
      <span class="task-id-badge">TASK // INITIALIZING...</span>
      <span class="task-status running">RUNNING</span>
    </div>
    <div class="steps-container">
      <div class="step-item">
        <div class="step-left">
          <span class="step-agent-pill">Nexus Orchestrator</span>
          <span>Formulating semantic plan and validating permissions...</span>
        </div>
        <span class="step-status-tag running">Thinking...</span>
      </div>
    </div>
    <div class="task-summary-box hidden"></div>
    <div class="created-doc-card hidden"></div>
  `;
  return card;
}

function pollTaskStatus(taskId, card) {
  if (pollTimer) clearInterval(pollTimer);

  pollTimer = setInterval(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/tasks/${taskId}`);
      if (res.status === 404) {
        clearInterval(pollTimer);
        pollTimer = null;
        return;
      }
      if (!res.ok) return;
      const task = await res.json();

      card.querySelector('.task-id-badge').innerText = `TASK // ${task.id}`;
      const statusBadge = card.querySelector('.task-status');
      statusBadge.innerText = task.status;
      statusBadge.className = `task-status ${task.status.toLowerCase()}`;

      // Update Steps
      const stepsContainer = card.querySelector('.steps-container');
      const plan = task.plan || {};
      const steps = plan.steps || [];

      if (steps.length > 0) {
        stepsContainer.innerHTML = '';
        steps.forEach((s, idx) => {
          const isDone = task.status === 'COMPLETED' || idx < (task.current_step_index || 0);
          const isCurrent = task.status === 'RUNNING' && idx === (task.current_step_index || 0);
          
          const sItem = document.createElement('div');
          sItem.className = 'step-item';
          sItem.innerHTML = `
            <div class="step-left">
              <span class="step-agent-pill">${s.agent}</span>
              <span><b>Step ${s.step_number}:</b> ${s.title}</span>
            </div>
            <span class="step-status-tag ${isDone ? 'completed' : (isCurrent ? 'running' : '')}">
              ${isDone ? '✓ Verified' : (isCurrent ? '⚡ In Progress' : 'Pending')}
            </span>
          `;
          stepsContainer.appendChild(sItem);
        });
      }

      // Check for approval requirements
      if (task.status === 'AWAITING_APPROVAL' && task.pending_approval) {
        renderApprovalPrompt(card, task.pending_approval);
      }

      // Finished States
      if (['COMPLETED', 'FAILED', 'CANCELLED'].includes(task.status)) {
        clearInterval(pollTimer);
        pollTimer = null;

        const summaryBox = card.querySelector('.task-summary-box');
        summaryBox.classList.remove('hidden');

        const report = task.completion_report || {};
        const summaryText = task.error_message 
          ? `<b style="color:var(--accent-crimson)">Failed:</b> ${task.error_message}`
          : (report.summary || plan.conversational_response || "Task executed and verified on your Windows desktop.");

        summaryBox.innerHTML = `
          <div>${summaryText}</div>
          <button class="btn-mini-new" style="margin-top:8px;" onclick="playTts(\`${encodeURIComponent(summaryText.replace(/<[^>]*>/g, ''))}\`)">🔊 Listen Voice</button>
        `;

        // Check if any document (.pptx or .pdf) was created!
        checkForCreatedDocument(card, task);
        loadDocuments();
      }
    } catch (e) {}
  }, 750);
}

async function checkForCreatedDocument(card, task) {
  // 1. Try to get the EXACT document created by this specific task
  let targetDoc = null;
  const report = task.completion_report || {};

  if (report.created_document && report.created_document.filename) {
    targetDoc = report.created_document;
  } else if (report.actions && Array.isArray(report.actions)) {
    for (const a of report.actions) {
      const res = a.result || {};
      if (res.filename && (res.file_path || res.path || res.doc_id)) {
        targetDoc = {
          id: res.doc_id || '',
          filename: res.filename,
          file_path: res.file_path || res.path,
          file_type: res.file_type || (res.filename.split('.').pop().toUpperCase())
        };
        break;
      }
    }
  }

  // 2. Fallback: Search DB for document matching task_id or mentioned in completion summary
  if (!targetDoc) {
    try {
      const res = await fetch(`${API_BASE}/api/documents`);
      const data = await res.json();
      if (data.documents && data.documents.length > 0) {
        const matched = data.documents.find(d => d.task_id === task.id);
        if (matched) {
          targetDoc = matched;
        } else {
          const summaryStr = (report.summary || '').toLowerCase();
          const foundInSummary = data.documents.find(d => d.filename && summaryStr.includes(d.filename.toLowerCase()));
          if (foundInSummary) {
            targetDoc = foundInSummary;
          }
        }
      }
    } catch (e) {}
  }

  // If no document was created by this task, do not display shelf
  if (!targetDoc) {
    return;
  }

  const docCard = card.querySelector('.created-doc-card');
  if (!docCard) return;
  docCard.classList.remove('hidden');

  const docName = targetDoc.filename || 'Generated Deliverable';
  const docId = targetDoc.id || targetDoc.doc_id || '';
  const docPath = targetDoc.file_path || targetDoc.path || '';
  const ext = (docName.split('.').pop() || '').toLowerCase();

  let icon = '📄';
  if (ext === 'pptx' || ext === 'ppt') icon = '📊';
  else if (ext === 'pdf') icon = '📑';
  else if (ext === 'xlsx' || ext === 'xls') icon = '📈';
  else if (ext === 'docx' || ext === 'doc') icon = '📝';

  docCard.innerHTML = `
    <div class="doc-info" style="display:flex; align-items:center; gap:10px; overflow:hidden; flex:1; min-width:0;">
      <span class="doc-icon-badge" style="font-size:22px; flex-shrink:0;">${icon}</span>
      <div class="doc-text" style="overflow:hidden; min-width:0;">
        <h5 style="white-space:nowrap; overflow:hidden; text-overflow:ellipsis; font-size:12px; font-weight:600; color:var(--text-main);" title="${docName}">${docName}</h5>
        <span style="font-size:10px; color:var(--text-muted); font-family:var(--font-mono);">Saved to generated_documents/</span>
      </div>
    </div>
    <div style="display:flex; gap:6px; flex-shrink:0; align-items:center;">
      <button class="btn-shelf-action" id="card-btn-view-${task.id}" title="Open document in new browser tab">↗ Open in Tab</button>
      <button class="btn-shelf-action" id="card-btn-open-${task.id}" title="Launch in Windows desktop application">💻 Desktop App</button>
      <button class="btn-shelf-action" id="card-btn-reveal-${task.id}" title="Show in Windows File Explorer folder">📂 Reveal</button>
      <button class="btn-open-doc" onclick="switchTabToDocuments()" title="View in Document Studio">🗂️ Studio</button>
    </div>
  `;

  const bView = docCard.querySelector(`#card-btn-view-${task.id}`);
  const bOpen = docCard.querySelector(`#card-btn-open-${task.id}`);
  const bReveal = docCard.querySelector(`#card-btn-reveal-${task.id}`);
  if (bView) bView.onclick = () => openDocInNewTab(docId, docPath);
  if (bOpen) bOpen.onclick = () => openGeneratedDoc(docId, docPath);
  if (bReveal) bReveal.onclick = () => revealGeneratedDoc(docId, docPath);
}

function renderApprovalPrompt(card, approval) {
  let appBox = card.querySelector('.approval-box');
  if (!appBox) {
    appBox = document.createElement('div');
    appBox.className = 'approval-box';
    appBox.style = "background:rgba(245, 158, 11, 0.08); border:1px solid rgba(245, 158, 11, 0.35); padding:14px; border-radius:8px; margin-top:12px;";
    card.appendChild(appBox);
  }

  const tool = approval.tool || approval.tool_name || "System Operation";
  const title = approval.title || approval.reason || `Execute ${tool}`;
  const risk = approval.risk_level || "MEDIUM";
  const apprId = approval.id || approval.approval_id;

  appBox.innerHTML = `
    <div style="font-size:12px; font-weight:700; color:#fbbf24; margin-bottom:6px; display:flex; align-items:center; gap:6px;">
      <span>⚠️</span>
      <span>ACTION REQUIRES AUTHORIZATION</span>
    </div>
    <div style="font-size:12.5px; color:#f8fafc; font-weight:600; margin-bottom:4px;">${title}</div>
    <div style="font-size:11px; color:#94a3b8; margin-bottom:12px;">Tool: <code style="color:#cbd5e1;">${tool}</code> &bull; Risk Level: <span style="color:#f59e0b; font-weight:600;">${risk}</span></div>
    <div style="display:flex; gap:8px; flex-wrap:wrap;">
      <button class="btn-accent-action" onclick="resolveApproval('${apprId}', 'allow_once')">Allow Once</button>
      <button class="btn-secondary-action" onclick="resolveApproval('${apprId}', 'allow_session')">Allow for Session</button>
      <button class="btn-emergency" onclick="resolveApproval('${apprId}', 'deny')">Deny</button>
    </div>
  `;
}

async function resolveApproval(approvalId, decision) {
  try {
    await fetch(`${API_BASE}/api/approvals/${approvalId}/decision`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decision })
    });
  } catch (e) {}
}

async function playTts(encodedText) {
  try {
    const text = decodeURIComponent(encodedText);
    const res = await fetch(`${API_BASE}/api/speech/tts`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text })
    });
    const blob = await res.blob();
    const audio = new Audio(URL.createObjectURL(blob));
    audio.play();
  } catch (e) {}
}

function switchTabToDocuments() {
  const docTab = document.querySelector('[data-tab="tab-documents"]');
  if (docTab) docTab.click();
}

// =========================================================================
// 4. BROWSER AGENT & CREDENTIAL LOGIN
// =========================================================================
async function loadBrowserTabs() {
  try {
    tabsListContainer.innerHTML = '<div class="empty-notice">Scanning running browser session via UI Automation...</div>';
    const res = await fetch(`${API_BASE}/api/browser/tabs`);
    const data = await res.json();

    if (!data.success || !data.tabs || data.tabs.length === 0) {
      tabsListContainer.innerHTML = `
        <div class="empty-notice" style="color:#fca5a5;">
          ${data.error || 'No Chrome, Edge, or Brave browser windows found currently running. Open your browser and refresh.'}
        </div>
      `;
      browserTabCount.innerText = "0 Tabs";
      return;
    }

    browserTabCount.innerText = `${data.total_tabs} Tabs (${data.browser_type})`;
    tabsListContainer.innerHTML = '';

    data.tabs.forEach(t => {
      const entry = document.createElement('div');
      entry.className = `tab-entry ${t.is_active ? 'active-tab' : ''}`;
      entry.innerHTML = `
        <div style="display:flex; align-items:center; gap:8px; overflow:hidden;">
          <span>🌐</span>
          <span style="white-space:nowrap; overflow:hidden; text-overflow:ellipsis; max-width:500px;">${t.title}</span>
        </div>
        <span style="font-size:10px; color:var(--text-muted); font-family:var(--font-mono);">${t.is_active ? 'ACTIVE' : ''}</span>
      `;
      tabsListContainer.appendChild(entry);
    });
  } catch (e) {
    tabsListContainer.innerHTML = '<div class="empty-notice">Failed to query browser tabs.</div>';
  }
}

async function executeBrowserLogin() {
  const url = loginUrl.value.trim();
  const username = loginUsername.value.trim();
  const password = loginPassword.value;

  if (!username && !url) {
    alert("Please enter a portal URL or username.");
    return;
  }

  btnExecLogin.disabled = true;
  btnExecLogin.innerText = "Submitting to Browser...";
  loginResultBox.className = "result-notice hidden";

  try {
    const res = await fetch(`${API_BASE}/api/browser/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        url: url || null,
        username: username || null,
        password: password || null,
        submit: true
      })
    });
    const data = await res.json();
    loginResultBox.classList.remove('hidden');

    if (data.success) {
      loginResultBox.className = "result-notice success";
      loginResultBox.innerHTML = `<b>Success:</b> ${data.message}`;
    } else {
      loginResultBox.className = "result-notice error";
      loginResultBox.innerHTML = `<b>Error:</b> ${data.error || 'Failed to submit login.'}`;
    }
  } catch (e) {
    loginResultBox.className = "result-notice error";
    loginResultBox.innerHTML = `<b>Network Error:</b> Could not reach browser controller.`;
    loginResultBox.classList.remove('hidden');
  } finally {
    btnExecLogin.disabled = false;
    btnExecLogin.innerText = "🚀 Submit Credentials to Browser";
    loadBrowserTabs();
  }
}

// =========================================================================
// 5. DOCUMENT STUDIO (PPTX & PDF)
// =========================================================================
async function loadDocuments() {
  try {
    const res = await fetch(`${API_BASE}/api/documents`);
    const data = await res.json();

    if (!data.success || !data.documents || data.documents.length === 0) {
      docsGallery.innerHTML = '<div class="empty-notice" style="text-align:center; padding:18px;">No generated documents yet. Use the creators above to generate PowerPoint presentations or PDF reports.</div>';
      return;
    }

    docsGallery.innerHTML = '';
    data.documents.forEach(doc => {
      const ft = (doc.file_type || '').toUpperCase();
      const fname = (doc.filename || doc.name || '').toLowerCase();
      let icon = '📑';
      let typeLabel = 'Executive Report (.pdf)';

      if (ft === 'PPTX' || fname.endsWith('.pptx')) {
        icon = '📊';
        typeLabel = 'PowerPoint Presentation (.pptx)';
      } else if (ft === 'DOCX' || fname.endsWith('.docx')) {
        icon = '📝';
        typeLabel = 'Word Document (.docx)';
      } else if (ft === 'XLSX' || fname.endsWith('.xlsx')) {
        icon = '📈';
        typeLabel = 'Excel Spreadsheet (.xlsx)';
      }

      const name = doc.filename || doc.name || 'Untitled Document';
      const sizeKb = Math.round((doc.size_bytes || 0) / 1024);
      const docId = doc.id;

      const card = document.createElement('div');
      card.className = 'doc-shelf-card';
      card.id = `doc-card-${docId}`;

      const leftDiv = document.createElement('div');
      leftDiv.className = 'doc-shelf-left';
      leftDiv.innerHTML = `
        <span style="font-size:24px; flex-shrink:0;">${icon}</span>
        <div class="doc-shelf-meta">
          <h5 title="${name}">${name}</h5>
          <span>${typeLabel} • ${sizeKb} KB</span>
        </div>
      `;

      const actionsDiv = document.createElement('div');
      actionsDiv.className = 'doc-shelf-actions';

      const docPath = doc.file_path || doc.path;

      const btnView = document.createElement('button');
      btnView.className = 'btn-shelf-action';
      btnView.innerHTML = '↗ Open in Tab';
      btnView.title = 'Open document in a new browser tab';
      btnView.onclick = () => openDocInNewTab(docId, docPath);

      const btnOpen = document.createElement('button');
      btnOpen.className = 'btn-shelf-action';
      btnOpen.innerHTML = '💻 Desktop App';
      btnOpen.title = 'Open in default Windows desktop application';
      btnOpen.onclick = () => openGeneratedDoc(docId, docPath);

      const btnReveal = document.createElement('button');
      btnReveal.className = 'btn-shelf-action';
      btnReveal.innerHTML = '📂 Reveal';
      btnReveal.title = 'Show in Windows File Explorer folder';
      btnReveal.onclick = () => revealGeneratedDoc(docId, docPath);

      const btnDelete = document.createElement('button');
      btnDelete.className = 'btn-shelf-del';
      btnDelete.innerHTML = '🗑️';
      btnDelete.title = 'Delete file permanently';
      btnDelete.onclick = () => deleteGeneratedDoc(docId, name);

      actionsDiv.appendChild(btnView);
      actionsDiv.appendChild(btnOpen);
      actionsDiv.appendChild(btnReveal);
      actionsDiv.appendChild(btnDelete);

      card.appendChild(leftDiv);
      card.appendChild(actionsDiv);
      docsGallery.appendChild(card);
    });
  } catch (e) {
    docsGallery.innerHTML = '<div class="empty-notice">Could not load documents from server.</div>';
  }
}

function openDocInNewTab(docId, docPath) {
  let url = `${API_BASE}/api/documents/view/${docId || ''}`;
  if (!docId && docPath) {
    url = `${API_BASE}/api/documents/view?path=${encodeURIComponent(docPath)}`;
  }
  window.open(url, '_blank');
}

async function openGeneratedDoc(docId, docPath) {
  try {
    const filename = docPath ? docPath.split(/[\\/]/).pop() : null;
    const res = await fetch(`${API_BASE}/api/documents/open`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ doc_id: docId || null, path: docPath || null, filename })
    });
    const data = await res.json();
    if (res.ok && data.success) {
      showToast(`🚀 Opened in Windows: ${data.message || 'File launched'}`);
    } else {
      alert("Could not open file: " + (data.detail || data.error || "File not found on disk."));
      await loadDocuments();
    }
  } catch (e) {
    alert("Failed to open document: " + e.message);
  }
}

async function revealGeneratedDoc(docId, docPath) {
  try {
    const filename = docPath ? docPath.split(/[\\/]/).pop() : null;
    const res = await fetch(`${API_BASE}/api/documents/reveal`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ doc_id: docId || null, path: docPath || null, filename })
    });
    const data = await res.json();
    if (res.ok && data.success) {
      const fileName = data.path ? data.path.split(/[\\/]/).pop() : 'Document';
      showToast(`📁 Highlighted in File Explorer: ${fileName}`);
    } else {
      alert("Could not reveal file: " + (data.detail || data.error || "File not found."));
      await loadDocuments();
    }
  } catch (e) {
    alert("Failed to reveal document: " + e.message);
  }
}

async function deleteGeneratedDoc(docId, name) {
  if (!confirm(`Permanently delete "${name}" from disk?`)) {
    return;
  }
  try {
    const res = await fetch(`${API_BASE}/api/documents/${docId}`, {
      method: "DELETE"
    });
    const data = await res.json();
    if (!res.ok || !data.success) {
      alert("Could not delete file: " + (data.detail || data.error || "File is currently in use or not found."));
    }
    await loadDocuments();
  } catch (e) {
    alert("Error deleting document: " + e.message);
  }
}

async function clearAllDocuments() {
  if (!confirm("Are you sure you want to delete ALL generated presentations and PDF reports? This permanently removes all files from disk.")) {
    return;
  }
  try {
    const res = await fetch(`${API_BASE}/api/documents`, {
      method: "DELETE"
    });
    const data = await res.json();
    if (!res.ok || !data.success) {
      alert("Could not clear all files: " + (data.detail || data.error || "Unknown error."));
    } else {
      if (data.locked_files && data.locked_files.length > 0) {
        alert(`Cleared ${data.deleted_count} file(s). Note: ${data.locked_files.join(', ')} could not be deleted because they are currently open in another program.`);
      }
    }
    await loadDocuments();
  } catch (e) {
    alert("Error clearing documents: " + e.message);
  }
}

async function createPptxDirect() {
  const topic = inputPptxTopic.value.trim() || "PES University Overview";
  btnCreatePptx.disabled = true;
  btnCreatePptx.innerText = "Generating Deck...";
  try {
    const res = await fetch(`${API_BASE}/api/documents/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ doc_type: "pptx", topic: topic })
    });
    const data = await res.json();
    if (data.success) {
      await loadDocuments();
      alert(`PowerPoint Presentation created successfully!\n\nFile: ${data.filename}\nSlides: ${data.slides_count} slides\n\nYou can click 'Open in App' to view it in PowerPoint.`);
    } else {
      alert(`Failed to create presentation: ${data.error || 'Unknown error'}`);
    }
  } catch (e) {
    submitPrompt(`Create a PowerPoint presentation on ${topic}`);
    document.querySelector('[data-tab="tab-console"]').click();
  } finally {
    btnCreatePptx.disabled = false;
    btnCreatePptx.innerText = "📊 Create PPTX";
  }
}

async function createPdfDirect() {
  const title = inputPdfTitle.value.trim() || "Artificial Intelligence Comprehensive Report";
  btnCreatePdf.disabled = true;
  btnCreatePdf.innerText = "Generating Report...";
  try {
    const res = await fetch(`${API_BASE}/api/documents/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ doc_type: "pdf", topic: title })
    });
    const data = await res.json();
    if (data.success) {
      await loadDocuments();
      alert(`Executive PDF Report created successfully!\n\nFile: ${data.filename}\n\nYou can click 'Open in App' to view it in your PDF reader.`);
    } else {
      alert(`Failed to create PDF: ${data.error || 'Unknown error'}`);
    }
  } catch (e) {
    submitPrompt(`Generate an executive PDF report on ${title}`);
    document.querySelector('[data-tab="tab-console"]').click();
  } finally {
    btnCreatePdf.disabled = false;
    btnCreatePdf.innerText = "📑 Create PDF";
  }
}

async function createDocxDirect() {
  const topic = (inputDocxTopic ? inputDocxTopic.value.trim() : '') || "Enterprise Architecture Report";
  if (btnCreateDocx) {
    btnCreateDocx.disabled = true;
    btnCreateDocx.innerText = "Generating Word Doc...";
  }
  try {
    const res = await fetch(`${API_BASE}/api/documents/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ doc_type: "docx", topic: topic })
    });
    const data = await res.json();
    if (data.success) {
      await loadDocuments();
      alert(`Word Document (.docx) created successfully!\n\nFile: ${data.filename}\nSections: ${data.sections_count || 4}\n\nYou can click 'Open' to view it in Microsoft Word.`);
    } else {
      alert(`Failed to create Word document: ${data.error || 'Unknown error'}`);
    }
  } catch (e) {
    submitPrompt(`Create a Word document on ${topic}`);
    document.querySelector('[data-tab="tab-console"]').click();
  } finally {
    if (btnCreateDocx) {
      btnCreateDocx.disabled = false;
      btnCreateDocx.innerText = "📝 Create DOCX";
    }
  }
}

async function createXlsxDirect() {
  const topic = (inputXlsxTopic ? inputXlsxTopic.value.trim() : '') || "Q4 Financial Model";
  if (btnCreateXlsx) {
    btnCreateXlsx.disabled = true;
    btnCreateXlsx.innerText = "Generating Excel...";
  }
  try {
    const res = await fetch(`${API_BASE}/api/documents/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ doc_type: "xlsx", topic: topic })
    });
    const data = await res.json();
    if (data.success) {
      await loadDocuments();
      alert(`Excel Spreadsheet (.xlsx) created successfully!\n\nFile: ${data.filename}\nSheets: ${data.sheets_count || 3} tabs\n\nYou can click 'Open' to view it in Microsoft Excel.`);
    } else {
      alert(`Failed to create Excel spreadsheet: ${data.error || 'Unknown error'}`);
    }
  } catch (e) {
    submitPrompt(`Create an Excel spreadsheet on ${topic}`);
    document.querySelector('[data-tab="tab-console"]').click();
  } finally {
    if (btnCreateXlsx) {
      btnCreateXlsx.disabled = false;
      btnCreateXlsx.innerText = "📈 Create XLSX";
    }
  }
}

// =========================================================================
// 5B. AUDIT & LOGS VIEWER
// =========================================================================
async function loadAuditLogs() {
  if (!logsContainer) return;
  try {
    const res = await fetch(`${API_BASE}/api/logs/audit?limit=100`);
    const data = await res.json();
    const logs = data.audit_logs || [];
    if (auditLogStats) auditLogStats.innerText = `${logs.length} entries recorded`;
    if (logCountBadge) logCountBadge.innerText = `${logs.length}`;

    if (logs.length === 0) {
      logsContainer.innerHTML = '<div class="empty-notice" style="text-align:center; padding:20px;">No audit logs recorded yet. Agent actions and security events will appear here in real time.</div>';
      return;
    }

    logsContainer.innerHTML = '';
    logs.forEach(l => {
      const card = document.createElement('div');
      card.className = 'log-card';
      const ev = (l.event_name || 'EVENT').toLowerCase();
      let tagClass = 'task_created';
      if (ev.includes('completed')) tagClass = 'action_completed';
      else if (ev.includes('failed')) tagClass = 'action_failed';
      else if (ev.includes('executing')) tagClass = 'action_executing';
      else if (ev.includes('approval')) tagClass = 'approval_required';
      else if (ev.includes('stop')) tagClass = 'emergency_stop';

      const timeStr = l.timestamp ? new Date(l.timestamp).toLocaleTimeString() : '';
      const detailsJson = JSON.stringify(l.details || {}, null, 2);

      card.innerHTML = `
        <div class="log-card-header">
          <div style="display:flex; align-items:center; gap:8px;">
            <span class="log-event-tag ${tagClass}">${l.event_name || 'LOG'}</span>
            <span style="font-size:11px; font-weight:600; color:#f1f5f9;">${l.task_id ? 'Task: ' + l.task_id : 'System Event'}</span>
          </div>
          <span class="log-time">${timeStr}</span>
        </div>
        <pre class="log-details-pre">${escapeHtml(detailsJson)}</pre>
      `;
      logsContainer.appendChild(card);
    });
  } catch (e) {
    logsContainer.innerHTML = '<div class="empty-notice">Could not load audit logs.</div>';
  }
}

async function clearAuditLogs() {
  if (!confirm("Wipe all persistent security & execution logs from SQLite?")) return;
  try {
    const res = await fetch(`${API_BASE}/api/logs/audit`, { method: "DELETE" });
    const data = await res.json();
    await loadAuditLogs();
  } catch (e) {
    alert("Failed to clear logs: " + e.message);
  }
}

// =========================================================================
// 6. VISION INSPECTOR
// =========================================================================
async function captureAndAnalyzeVision() {
  btnCaptureVision.disabled = true;
  btnCaptureVision.innerText = "Capturing & Reasoning...";
  visionTextOutput.innerText = "Capturing high-resolution desktop screen and dispatching multimodal Vision Agent...";

  refreshVisionPreview();

  try {
    const res = await fetch(`${API_BASE}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        messages: [{ role: "user", content: "Analyze my current desktop screen. Identify open applications, visible windows, text, and explain any errors." }],
        permission_mode: "balanced",
        wait_for_completion: true
      })
    });
    const data = await res.json();
    const report = data.completion_report || {};
    visionTextOutput.innerHTML = `<b>Multimodal Analysis:</b><br><br>${(report.summary || 'Screen analysis complete.').replace(/\n/g, '<br>')}`;
  } catch (e) {
    visionTextOutput.innerText = "Error running Vision analysis: " + e.message;
  } finally {
    btnCaptureVision.disabled = false;
    btnCaptureVision.innerText = "📸 Capture & Analyze Screen";
  }
}

function refreshVisionPreview() {
  if (visionScreenImg) {
    visionScreenImg.src = `${API_BASE}/api/screenshot?t=${Date.now()}`;
  }
}

function showToast(message, type = 'info') {
  let toastContainer = document.getElementById('toast-container');
  if (!toastContainer) {
    toastContainer = document.createElement('div');
    toastContainer.id = 'toast-container';
    toastContainer.style = "position:fixed; bottom:24px; right:24px; z-index:99999; display:flex; flex-direction:column; gap:8px; pointer-events:none;";
    document.body.appendChild(toastContainer);
  }
  const toast = document.createElement('div');
  toast.className = 'toast-bubble';
  toast.style = "background:#1e293b; color:#f8fafc; border:1px solid #38bdf8; padding:10px 16px; border-radius:8px; font-size:12.5px; font-weight:500; box-shadow:0 8px 24px rgba(0,0,0,0.5); opacity:0; transform:translateY(10px); transition:all 0.25s cubic-bezier(0.16,1,0.3,1); pointer-events:auto;";
  toast.innerText = message;
  toastContainer.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = '1';
    toast.style.transform = 'translateY(0)';
  }, 10);
  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateY(10px)';
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

function appendSystemEventCard(message, type = 'info') {
  const card = document.createElement('div');
  card.className = 'task-card system-event-card';
  const color = type === 'danger' ? '#ef4444' : type === 'success' ? '#10b981' : '#38bdf8';
  card.style = `border-left: 3px solid ${color}; background: rgba(15, 23, 42, 0.6); padding: 12px 16px; margin: 8px 0; border-radius: 8px; font-size: 13px; font-weight: 600; color: #f8fafc;`;
  card.innerHTML = `<div>${message}</div>`;
  messageThread.appendChild(card);
  chatViewport.scrollTop = chatViewport.scrollHeight;
}

// =========================================================================
// 7. EMERGENCY STOP & EVENT LISTENERS
// =========================================================================
function setEmergencyStoppedUI(stopped) {
  isEmergencyStopped = stopped;
  if (stopped) {
    btnEmergencyStop.innerText = "⚠️ RESUME AGENT";
    btnEmergencyStop.style.background = "var(--accent-amber)";
    btnEmergencyStop.style.color = "#060813";
  } else {
    btnEmergencyStop.innerText = "🛑 EMERGENCY STOP";
    btnEmergencyStop.style.background = "rgba(239, 68, 68, 0.15)";
    btnEmergencyStop.style.color = "#fca5a5";
  }
}

async function toggleEmergencyStop() {
  if (isEmergencyStopped) {
    await fetch(`${API_BASE}/api/emergency-stop/clear`, { method: "POST" });
    setEmergencyStoppedUI(false);
    appendSystemEventCard("🟩 Emergency Stop cleared. Agent operations resumed.", "success");
    showToast("Agent operations resumed");
  } else {
    await fetch(`${API_BASE}/api/emergency-stop`, { method: "POST" });
    setEmergencyStoppedUI(true);
    appendSystemEventCard("🔴 EMERGENCY STOP ACTIVATED: All agent actions halted. Approvals cancelled.", "danger");
    showToast("EMERGENCY STOP ACTIVATED", "danger");
  }
}

async function loadRecentTasks() {
  try {
    const res = await fetch(`${API_BASE}/api/tasks?limit=30`);
    const data = await res.json();
    historyList.innerHTML = '';
    
    if (!data.tasks || data.tasks.length === 0) {
      historyList.innerHTML = '<div style="font-size:11px; color:var(--text-muted); padding:10px 4px; text-align:center;">No past missions yet.</div>';
      return;
    }

    data.tasks.forEach(t => {
      const item = document.createElement('div');
      item.className = `history-item ${activeTaskId === t.id ? 'active' : ''}`;
      item.id = `history-item-${t.id}`;

      // Smart icon selection based on task prompt
      const promptLower = (t.user_prompt || '').toLowerCase();
      let icon = '💬';
      if (promptLower.includes('ppt') || promptLower.includes('powerpoint') || promptLower.includes('slide')) {
        icon = '📊';
      } else if (promptLower.includes('pdf') || promptLower.includes('report') || promptLower.includes('word') || promptLower.includes('doc')) {
        icon = '📄';
      } else if (promptLower.includes('excel') || promptLower.includes('sheet') || promptLower.includes('csv')) {
        icon = '📈';
      } else if (promptLower.includes('browser') || promptLower.includes('chrome') || promptLower.includes('edge') || promptLower.includes('web') || promptLower.includes('search')) {
        icon = '🌐';
      } else if (promptLower.includes('screen') || promptLower.includes('look') || promptLower.includes('see') || promptLower.includes('ocr')) {
        icon = '👁️';
      } else if (promptLower.includes('system') || promptLower.includes('process') || promptLower.includes('ram') || promptLower.includes('cpu')) {
        icon = '⚙️';
      }

      const iconSpan = document.createElement('span');
      iconSpan.className = 'history-item-icon';
      iconSpan.innerText = icon;

      const titleSpan = document.createElement('span');
      titleSpan.className = 'history-item-title';
      titleSpan.innerText = t.user_prompt;
      titleSpan.title = t.user_prompt;

      const delBtn = document.createElement('button');
      delBtn.className = 'history-item-del';
      delBtn.innerHTML = '✕';
      delBtn.title = 'Delete this chat session';
      delBtn.onclick = (e) => {
        e.stopPropagation();
        deleteSingleTask(t.id);
      };

      item.onclick = () => {
        activeTaskId = t.id;
        document.querySelectorAll('.history-item').forEach(el => el.classList.remove('active'));
        item.classList.add('active');
        renderPastTask(t);
      };

      item.appendChild(iconSpan);
      item.appendChild(titleSpan);
      item.appendChild(delBtn);
      historyList.appendChild(item);
    });
  } catch (e) {}
}

async function deleteSingleTask(taskId) {
  try {
    const res = await fetch(`${API_BASE}/api/tasks/${taskId}`, {
      method: "DELETE"
    });
    const data = await res.json();
    if (data.success) {
      if (activeTaskId === taskId) {
        activeTaskId = null;
        messageThread.innerHTML = '';
        welcomeCard.style.display = 'block';
      }
      await loadRecentTasks();
    }
  } catch (e) {
    alert("Failed to delete mission: " + e.message);
  }
}

async function clearAllTasks() {
  if (!confirm("Are you sure you want to clear all mission history? This action cannot be undone.")) {
    return;
  }
  try {
    const res = await fetch(`${API_BASE}/api/tasks`, {
      method: "DELETE"
    });
    const data = await res.json();
    if (data.success) {
      activeTaskId = null;
      messageThread.innerHTML = '';
      welcomeCard.style.display = 'block';
      await loadRecentTasks();
    }
  } catch (e) {
    alert("Failed to clear history: " + e.message);
  }
}

function renderPastTask(task) {
  document.querySelector('[data-tab="tab-console"]').click();
  welcomeCard.style.display = 'none';
  messageThread.innerHTML = '';
  appendUserMessage(task.user_prompt);

  const card = createTaskCard(task.user_prompt);
  card.querySelector('.task-id-badge').innerText = `TASK // ${task.id}`;
  const statusBadge = card.querySelector('.task-status');
  statusBadge.innerText = task.status;
  statusBadge.className = `task-status ${task.status.toLowerCase()}`;

  const summaryBox = card.querySelector('.task-summary-box');
  summaryBox.classList.remove('hidden');
  const report = task.completion_report || {};
  summaryBox.innerHTML = `<div>${report.summary || task.error_message || 'Completed.'}</div>`;

  checkForCreatedDocument(card, task);
  messageThread.appendChild(card);
}

function setupEventListeners() {
  btnSend.addEventListener('click', () => submitPrompt());
  promptInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      submitPrompt();
    }
  });

  // HUD
  btnToggleHud.addEventListener('click', () => floatingHudBar.classList.toggle('hidden'));
  hudBtnClose.addEventListener('click', () => floatingHudBar.classList.add('hidden'));
  hudBtnSend.addEventListener('click', () => submitPrompt(hudInput.value));
  hudInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      submitPrompt(hudInput.value);
    }
  });

  // Emergency Stop
  btnEmergencyStop.addEventListener('click', toggleEmergencyStop);

  // Bento quick triggers
  document.querySelectorAll('.bento-card').forEach(card => {
    card.addEventListener('click', () => {
      const cmd = card.getAttribute('data-cmd');
      submitPrompt(cmd);
    });
  });

  // Browser Agent
  btnRefreshTabs.addEventListener('click', loadBrowserTabs);
  btnExecLogin.addEventListener('click', executeBrowserLogin);
  btnOpenBrowser.addEventListener('click', async () => {
    btnOpenBrowser.disabled = true;
    btnOpenBrowser.innerText = "Opening Tab...";
    try {
      await fetch(`${API_BASE}/api/browser/open`, { method: "POST" });
      await loadBrowserTabs();
    } catch (e) {
      submitPrompt("Open my existing browser in a new tab");
    } finally {
      btnOpenBrowser.disabled = false;
      btnOpenBrowser.innerText = "🌐 Focus / Open New Tab";
    }
  });

  // Document Studio
  if (btnCreatePptx) btnCreatePptx.addEventListener('click', createPptxDirect);
  if (btnCreateDocx) btnCreateDocx.addEventListener('click', createDocxDirect);
  if (btnCreateXlsx) btnCreateXlsx.addEventListener('click', createXlsxDirect);
  if (btnCreatePdf) btnCreatePdf.addEventListener('click', createPdfDirect);
  if (btnRefreshDocs) btnRefreshDocs.addEventListener('click', loadDocuments);
  if (btnClearAllDocs) btnClearAllDocs.addEventListener('click', clearAllDocuments);

  // Audit Logs
  if (btnRefreshLogs) btnRefreshLogs.addEventListener('click', loadAuditLogs);
  if (btnClearLogs) btnClearLogs.addEventListener('click', clearAuditLogs);

  // Vision
  btnCaptureVision.addEventListener('click', captureAndAnalyzeVision);
  btnRefreshPreview.addEventListener('click', refreshVisionPreview);

  // System Apps
  document.querySelectorAll('.app-chip').forEach(btn => {
    btn.addEventListener('click', () => {
      const app = btn.getAttribute('data-app');
      submitPrompt(`Launch application ${app}`);
      document.querySelector('[data-tab="tab-console"]').click();
    });
  });

  // Phone Modal
  btnConnectPhone.addEventListener('click', () => phoneModal.classList.remove('hidden'));
  btnClosePhone.addEventListener('click', () => phoneModal.classList.add('hidden'));
  btnDonePhone.addEventListener('click', () => phoneModal.classList.add('hidden'));
  btnCopyUrl.addEventListener('click', () => {
    navigator.clipboard.writeText(lanUrlInput.value);
    btnCopyUrl.innerText = "Copied!";
    setTimeout(() => btnCopyUrl.innerText = "Copy", 1500);
  });

  // Settings Modal
  btnOpenSettings.addEventListener('click', () => settingsModal.classList.remove('hidden'));
  btnCloseSettings.addEventListener('click', () => settingsModal.classList.add('hidden'));
  btnSaveSettings.addEventListener('click', async () => {
    await fetch(`${API_BASE}/api/settings`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        llm_provider: selectProvider.value,
        gemini_api_key: inputGeminiKey.value,
        groq_api_key: inputGroqKey.value,
        remote_pairing_pin: inputPin.value,
        default_voice: selectVoice.value
      })
    });
    settingsModal.classList.add('hidden');
    fetchStatusAndNetwork();
  });

  btnNewTask.addEventListener('click', () => {
    document.querySelector('[data-tab="tab-console"]').click();
    messageThread.innerHTML = '';
    welcomeCard.style.display = 'block';
  });

  if (btnClearTasks) {
    btnClearTasks.addEventListener('click', clearAllTasks);
  }

  // Speech Web Speech API fallback
  if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
    const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
    const recognizer = new SpeechRec();
    recognizer.continuous = false;
    recognizer.interimResults = false;

    let isListening = false;
    const toggleMic = () => {
      if (isListening) {
        recognizer.stop();
        btnMic.classList.remove('active');
        isListening = false;
      } else {
        recognizer.start();
        btnMic.classList.add('active');
        isListening = true;
      }
    };

    btnMic.addEventListener('click', toggleMic);
    hudBtnMic.addEventListener('click', toggleMic);

    recognizer.onresult = (evt) => {
      const transcript = evt.results[0][0].transcript;
      promptInput.value = transcript;
      hudInput.value = transcript;
      btnMic.classList.remove('active');
      isListening = false;
      submitPrompt(transcript);
    };

    recognizer.onerror = () => {
      btnMic.classList.remove('active');
      isListening = false;
    };
  }
}

window.addEventListener('DOMContentLoaded', init);
