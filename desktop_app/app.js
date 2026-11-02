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
const inputPdfTitle = document.getElementById('input-pdf-title');
const btnCreatePdf = document.getElementById('btn-create-pdf');
const btnRefreshDocs = document.getElementById('btn-refresh-docs');
const docsGallery = document.getElementById('docs-gallery');

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

function checkForCreatedDocument(card, task) {
  const prompt = (task.user_prompt || '').toLowerCase();
  const summary = JSON.stringify(task.completion_report || {}).toLowerCase();

  let foundDoc = null;
  if (prompt.includes('powerpoint') || prompt.includes('presentation') || prompt.includes('pptx') || summary.includes('.pptx')) {
    foundDoc = { type: 'PPTX', icon: '📊', name: 'Presentation.pptx' };
  } else if (prompt.includes('pdf') || prompt.includes('report') || summary.includes('.pdf')) {
    foundDoc = { type: 'PDF', icon: '📑', name: 'Executive_Report.pdf' };
  }

  if (foundDoc) {
    const docCard = card.querySelector('.created-doc-card');
    docCard.classList.remove('hidden');
    docCard.innerHTML = `
      <div class="doc-info">
        <span class="doc-icon-badge">${foundDoc.icon}</span>
        <div class="doc-text">
          <h5>Generated ${foundDoc.type} Document Ready</h5>
          <span>Rich multi-page content saved to project workspace</span>
        </div>
      </div>
      <button class="btn-open-doc" onclick="switchTabToDocuments()">📂 View in Document Studio</button>
    `;
  }
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
    <div style="display:flex; gap:8px;">
      <button class="btn-accent-action" onclick="resolveApproval('${apprId}', 'allow_once')">Allow</button>
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
      docsGallery.innerHTML = '<div class="empty-notice" style="grid-column:span 2;">No generated documents yet. Use the buttons above to generate your first PowerPoint presentation or PDF report.</div>';
      return;
    }

    docsGallery.innerHTML = '';
    data.documents.forEach(doc => {
      const isPpt = (doc.file_type || doc.type || '').toUpperCase() === 'PPTX' || (doc.name || doc.filename || '').endsWith('.pptx');
      const name = doc.filename || doc.name;
      const sizeKb = Math.round((doc.size_bytes || 0) / 1024);
      const docId = doc.id;
      const docPath = doc.file_path || doc.path;

      const card = document.createElement('div');
      card.className = 'doc-shelf-card';
      card.id = `doc-card-${docId}`;
      card.innerHTML = `
        <div class="doc-shelf-left">
          <span style="font-size:24px;">${isPpt ? '📊' : '📑'}</span>
          <div class="doc-shelf-meta">
            <h5 title="${name}">${name}</h5>
            <span>${isPpt ? 'PPTX' : 'PDF'} • ${sizeKb} KB</span>
          </div>
        </div>
        <div class="doc-shelf-actions">
          <button class="btn-shelf-action" onclick="openGeneratedDoc(\`${encodeURIComponent(docPath)}\`)" title="Open in default app">
            ▶ Open
          </button>
          <button class="btn-shelf-action" onclick="revealGeneratedDoc('${docId}', \`${encodeURIComponent(docPath)}\`)" title="Show in Windows File Explorer">
            📂 Reveal
          </button>
          <button class="btn-shelf-del" onclick="deleteGeneratedDoc('${docId}', '${name.replace(/'/g, "\\'")}')" title="Delete file">
            🗑️
          </button>
        </div>
      `;
      docsGallery.appendChild(card);
    });
  } catch (e) {}
}

async function openGeneratedDoc(encodedPath) {
  try {
    const path = decodeURIComponent(encodedPath);
    await fetch(`${API_BASE}/api/documents/open`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path })
    });
  } catch (e) {
    alert("Failed to open document: " + e.message);
  }
}

async function revealGeneratedDoc(docId, encodedPath) {
  try {
    const path = decodeURIComponent(encodedPath);
    await fetch(`${API_BASE}/api/documents/reveal`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ doc_id: docId, path })
    });
  } catch (e) {
    alert("Failed to reveal document: " + e.message);
  }
}

async function deleteGeneratedDoc(docId, name) {
  if (!confirm(`Delete "${name}"?\nThis removes the file from disk permanently.`)) {
    return;
  }
  try {
    const res = await fetch(`${API_BASE}/api/documents/${docId}`, {
      method: "DELETE"
    });
    const data = await res.json();
    if (data.success) {
      await loadDocuments();
    } else {
      alert("Failed to delete document: " + (data.error || "Unknown error"));
    }
  } catch (e) {
    alert("Error deleting document: " + e.message);
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
  } else {
    await fetch(`${API_BASE}/api/emergency-stop`, { method: "POST" });
    setEmergencyStoppedUI(true);
  }
}

async function loadRecentTasks() {
  try {
    const res = await fetch(`${API_BASE}/api/tasks?limit=30`);
    const data = await res.json();
    historyList.innerHTML = '';
    
    if (!data.tasks || data.tasks.length === 0) {
      historyList.innerHTML = '<div style="font-size:10px; color:var(--text-muted); padding:8px 4px; text-align:center;">No past missions yet.</div>';
      return;
    }

    data.tasks.forEach(t => {
      const item = document.createElement('div');
      item.className = `history-item ${activeTaskId === t.id ? 'active' : ''}`;
      item.id = `history-item-${t.id}`;

      const titleSpan = document.createElement('span');
      titleSpan.className = 'history-item-title';
      titleSpan.innerText = t.user_prompt;
      titleSpan.title = t.user_prompt;
      titleSpan.onclick = () => {
        activeTaskId = t.id;
        document.querySelectorAll('.history-item').forEach(el => el.classList.remove('active'));
        item.classList.add('active');
        renderPastTask(t);
      };

      const delBtn = document.createElement('button');
      delBtn.className = 'history-item-del';
      delBtn.innerHTML = '✕';
      delBtn.title = 'Delete this chat session';
      delBtn.onclick = (e) => {
        e.stopPropagation();
        deleteSingleTask(t.id);
      };

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
  btnOpenBrowser.addEventListener('click', () => {
    submitPrompt("Open my existing browser window");
  });

  // Document Studio
  btnCreatePptx.addEventListener('click', createPptxDirect);
  btnCreatePdf.addEventListener('click', createPdfDirect);
  btnRefreshDocs.addEventListener('click', loadDocuments);

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
