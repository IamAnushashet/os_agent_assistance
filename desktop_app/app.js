/**
 * NEXUS OS AGENT — Desktop Controller & Real-Time Deck Engine
 * Powers live telemetry SVG dials, multi-agent matrix tabs,
 * automated PPTX & PDF document studio, browser credentials login, and phone remote.
 */

const API_BASE = window.location.origin.startsWith('http') ? window.location.origin : 'http://127.0.0.1:8000';

let activeTaskId = null;
let pollTimer = null;
const activePollTimers = new Map();
let telemetryTimer = null;
let remoteSyncTimer = null;
let isEmergencyStopped = false;
let knownTaskIds = new Set();
let sessionInitTime = Date.now();

function escapeHtml(str) {
  if (str === null || str === undefined) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function guessLanguage(code) {
  const sample = (code || '').slice(0, 600).toLowerCase();
  if (sample.includes('#include') || sample.includes('std::') || sample.includes('cout <<')) return 'cpp';
  if (sample.includes('import ') || sample.includes('def ') || sample.includes('elif ') || sample.includes('print(')) return 'python';
  if (sample.includes('function ') || sample.includes('const ') || sample.includes('console.log') || sample.includes('let ')) return 'javascript';
  if (sample.includes('<html>') || sample.includes('<!doctype') || sample.includes('</div>')) return 'html';
  if (sample.includes('select ') || sample.includes('create table') || sample.includes('insert into')) return 'sql';
  if (sample.trim().startsWith('{') || sample.trim().startsWith('[')) return 'json';
  if (sample.includes('curl ') || sample.includes('apt-get') || sample.includes('pip install') || sample.includes('npm install')) return 'bash';
  if (sample.includes('public class ') || sample.includes('system.out.println')) return 'java';
  return 'code';
}

function isCodeLikeText(text) {
  if (!text || text.length < 25) return false;
  if (text.includes('```')) return false;

  const lines = text.split('\n').map(l => l.trim()).filter(l => l.length > 0);
  if (lines.length < 3) return false;

  let codeSignalCount = 0;
  const codePatterns = [
    /^#include\s*[<"]/i,
    /^(import|from)\s+[\w\.]+/i,
    /^(def|class)\s+\w+/i,
    /^(const|let|var)\s+\w+\s*=/i,
    /^function\s+\w+\s*\(/i,
    /^(public|private|protected)\s+(class|static|void|int|string)/i,
    /^(int|void|float|double|bool|char|auto)\s+\w+\s*\(.*?\)/i,
    /^(if|for|while)\s*\(.*?\)\s*\{/i,
    /^using\s+namespace\s+/i,
    /;\s*$/,
    /\{\s*$/,
    /^\/\//,
    /^#\s+(?!#)/
  ];

  for (const line of lines) {
    if (codePatterns.some(p => p.test(line))) {
      codeSignalCount++;
    }
  }

  return (codeSignalCount / lines.length) >= 0.35;
}

function highlightSyntax(code, lang) {
  if (!code) return '';
  const langLower = (lang || '').toLowerCase();

  const pythonKeywords = new Set([
    'and', 'as', 'assert', 'async', 'await', 'break', 'class', 'continue',
    'def', 'del', 'elif', 'else', 'except', 'finally', 'for', 'from',
    'global', 'if', 'import', 'in', 'is', 'lambda', 'nonlocal', 'not',
    'or', 'pass', 'raise', 'return', 'try', 'while', 'with', 'yield',
    'True', 'False', 'None'
  ]);
  const pythonBuiltins = new Set([
    'print', 'input', 'int', 'float', 'str', 'bool', 'list', 'dict', 'set',
    'tuple', 'len', 'range', 'enumerate', 'zip', 'open', 'type', 'sum',
    'min', 'max', 'abs', 'round', 'sorted', 'map', 'filter', 'all', 'any',
    'isinstance', 'super', 'dir', 'id', 'help', 'exit'
  ]);

  const cppKeywords = new Set([
    'auto', 'bool', 'break', 'case', 'catch', 'char', 'class', 'const',
    'constexpr', 'continue', 'default', 'delete', 'do', 'double', 'else',
    'enum', 'explicit', 'export', 'extern', 'false', 'float', 'for', 'friend',
    'goto', 'if', 'inline', 'int', 'long', 'mutable', 'namespace', 'new',
    'noexcept', 'nullptr', 'operator', 'private', 'protected', 'public',
    'register', 'return', 'short', 'signed', 'sizeof', 'static', 'struct',
    'switch', 'template', 'this', 'throw', 'true', 'try', 'typedef', 'typeid',
    'typename', 'union', 'unsigned', 'using', 'virtual', 'void', 'volatile',
    'wchar_t', 'while'
  ]);
  const cppBuiltins = new Set([
    'std', 'cout', 'cin', 'cerr', 'endl', 'string', 'vector', 'map', 'set',
    'pair', 'make_pair', 'push_back', 'pop_back', 'size', 'length', 'empty',
    'clear', 'begin', 'end', 'to_string', 'stoi', 'stod', 'tolower', 'toupper',
    'isalnum', 'isalpha', 'isdigit', 'reverse', 'sort', 'min', 'max', 'printf', 'scanf'
  ]);

  const jsKeywords = new Set([
    'async', 'await', 'break', 'case', 'catch', 'class', 'const', 'continue',
    'debugger', 'default', 'delete', 'do', 'else', 'export', 'extends',
    'finally', 'for', 'function', 'if', 'import', 'in', 'instanceof', 'new',
    'return', 'super', 'switch', 'this', 'throw', 'try', 'typeof', 'var',
    'void', 'while', 'with', 'yield', 'let', 'static', 'true', 'false',
    'null', 'undefined', 'NaN'
  ]);
  const jsBuiltins = new Set([
    'console', 'log', 'warn', 'error', 'info', 'document', 'window', 'fetch',
    'JSON', 'parse', 'stringify', 'Math', 'floor', 'ceil', 'round', 'random',
    'parseInt', 'parseFloat', 'setTimeout', 'setInterval', 'clearTimeout',
    'Array', 'Object', 'String', 'Number', 'Boolean', 'Promise', 'Map', 'Set'
  ]);

  const javaKeywords = new Set([
    'abstract', 'assert', 'boolean', 'break', 'byte', 'case', 'catch', 'char',
    'class', 'const', 'continue', 'default', 'do', 'double', 'else', 'enum',
    'extends', 'final', 'finally', 'float', 'for', 'goto', 'if', 'implements',
    'import', 'instanceof', 'int', 'interface', 'long', 'native', 'new',
    'package', 'private', 'protected', 'public', 'return', 'short', 'static',
    'strictfp', 'super', 'switch', 'synchronized', 'this', 'throw', 'throws',
    'transient', 'try', 'void', 'volatile', 'while', 'true', 'false', 'null'
  ]);
  const javaBuiltins = new Set([
    'System', 'out', 'println', 'print', 'Scanner', 'String', 'Math', 'Integer',
    'Double', 'Boolean', 'List', 'ArrayList', 'Map', 'HashMap', 'Set', 'HashSet',
    'Arrays', 'Collections', 'Override'
  ]);

  let keywords = pythonKeywords;
  let builtins = pythonBuiltins;
  const isPy = ['python', 'py'].includes(langLower);
  const isCpp = ['cpp', 'c++', 'c', 'h', 'hpp', 'cs'].includes(langLower);
  const isJs = ['js', 'javascript', 'ts', 'typescript', 'jsx', 'tsx'].includes(langLower);
  const isJava = ['java'].includes(langLower);

  if (isCpp) {
    keywords = cppKeywords;
    builtins = cppBuiltins;
  } else if (isJs) {
    keywords = jsKeywords;
    builtins = jsBuiltins;
  } else if (isJava) {
    keywords = javaKeywords;
    builtins = javaBuiltins;
  }

  const commentPattern = isPy
    ? '(#[^\\r\\n]*)'
    : '(\\/\\/[^\\r\\n]*|\\/\\*[\\s\\S]*?\\*\\/|#[^\\r\\n]*)';

  const tokenRegex = new RegExp(
    '(".*?"|\'.*?\'|`[\\s\\S]*?`)' +
    '|' + commentPattern +
    '|(\\b\\d+(?:\\.\\d+)?\\b)' +
    '|([a-zA-Z_$][a-zA-Z0-9_$]*)' +
    '|([!=+\\-*\\/%&|^~<>:]+)' +
    '|(\\s+)' +
    '|([^\\s\\w])',
    'g'
  );

  let html = '';
  let match;

  while ((match = tokenRegex.exec(code)) !== null) {
    const [full, str, comment, num, word, op, ws, punct] = match;

    if (str) {
      html += `<span class="tok-string">${escapeHtml(str)}</span>`;
    } else if (comment) {
      if (isCpp && comment.trim().startsWith('#include')) {
        const incMatch = comment.match(/(#include)\s*(<[^>]+>|"[^"]+")?/);
        if (incMatch) {
          html += `<span class="tok-keyword">${escapeHtml(incMatch[1])}</span>`;
          if (incMatch[2]) {
            html += ` <span class="tok-string">${escapeHtml(incMatch[2])}</span>`;
          }
        } else {
          html += `<span class="tok-keyword">${escapeHtml(comment)}</span>`;
        }
      } else {
        html += `<span class="tok-comment">${escapeHtml(comment)}</span>`;
      }
    } else if (num) {
      html += `<span class="tok-number">${escapeHtml(num)}</span>`;
    } else if (word) {
      if (keywords.has(word)) {
        html += `<span class="tok-keyword">${escapeHtml(word)}</span>`;
      } else if (builtins.has(word)) {
        html += `<span class="tok-builtin">${escapeHtml(word)}</span>`;
      } else {
        html += `<span class="tok-ident">${escapeHtml(word)}</span>`;
      }
    } else if (op) {
      html += `<span class="tok-operator">${escapeHtml(op)}</span>`;
    } else if (ws) {
      html += ws;
    } else if (punct) {
      html += escapeHtml(punct);
    }
  }

  return html || escapeHtml(code);
}

function renderMarkdown(text) {
  if (text === null || text === undefined) return '';
  let str = String(text);

  // If the entire text is raw code without markdown backticks, automatically wrap it in a terminal code fence
  if (isCodeLikeText(str)) {
    const detectedLang = guessLanguage(str);
    str = '```' + detectedLang + '\n' + str + '\n```';
  }

  // 1. Extract fenced code blocks first to protect contents from HTML escaping & formatting
  const codeBlocks = [];
  let processed = str.replace(/```([a-zA-Z0-9_\-\+]*)\r?\n?([\s\S]*?)```/g, (match, lang, code) => {
    const placeholder = `@@@NEXUS_CODEBLOCK_${codeBlocks.length}@@@`;
    codeBlocks.push({
      lang: lang ? lang.trim() : guessLanguage(code),
      code: code
    });
    return placeholder;
  });

  // 2. Escape HTML on text to prevent XSS and tag-eating (<iostream>, <vector>, etc.)
  processed = escapeHtml(processed);

  // 3. Markdown Headings
  processed = processed.replace(/^### (.*$)/gim, '<h4 class="md-h4">$1</h4>');
  processed = processed.replace(/^## (.*$)/gim, '<h3 class="md-h3">$1</h3>');
  processed = processed.replace(/^# (.*$)/gim, '<h2 class="md-h2">$1</h2>');

  // 4. Bold & Italic
  processed = processed.replace(/\*\*\*(.*?)\*\*\*/g, '<strong><em>$1</em></strong>');
  processed = processed.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
  processed = processed.replace(/\*(.*?)\*/g, '<em>$1</em>');

  // 5. Inline code
  processed = processed.replace(/`([^`]+)`/g, '<code class="inline-code">$1</code>');

  // 6. Numbered and Bullet lists
  processed = processed.replace(/^\s*[-*]\s+(.*$)/gim, '<li class="md-bullet">$1</li>');
  processed = processed.replace(/^\s*(\d+)\.\s+(.*$)/gim, '<li class="md-num" value="$1">$2</li>');

  // Wrap list items
  processed = processed.replace(/(<li class="md-bullet">[\s\S]*?<\/li>(?:\s*<li class="md-bullet">[\s\S]*?<\/li>)*)/g, '<ul class="md-list">$1</ul>');
  processed = processed.replace(/(<li class="md-num"[^>]*>[\s\S]*?<\/li>(?:\s*<li class="md-num"[^>]*>[\s\S]*?<\/li>)*)/g, '<ol class="md-list">$1</ol>');

  // 7. Line breaks and paragraph separation
  processed = processed.replace(/\r?\n\r?\n/g, '<div style="margin-bottom:8px;"></div>');
  processed = processed.replace(/\r?\n/g, '<br>');

  // Try to find any mentioned file name in text
  const fileMatch = str.match(/(?:Saved locally to|file|named|script)\s+[`"']?([a-zA-Z0-9_\-\.]+\.[a-zA-Z0-9]+)[`"']?/i);
  const detectedFilename = fileMatch ? fileMatch[1] : '';

  // 8. Re-inject Code Blocks into authentic Terminal UI Window Design (matching Image 4)
  codeBlocks.forEach((cb, idx) => {
    const trimmedCode = cb.code.replace(/^\n+|\n+$/g, '');
    const langLower = (cb.lang || 'code').toLowerCase();
    const highlightedCode = highlightSyntax(trimmedCode, langLower);

    let displayLang = cb.lang ? cb.lang : 'Terminal';
    let defaultFile = detectedFilename || 'snippet.txt';

    if (langLower === 'cpp' || langLower === 'c++') {
      displayLang = 'C++';
      if (!detectedFilename) defaultFile = 'main.cpp';
    } else if (langLower === 'py' || langLower === 'python') {
      displayLang = 'Python';
      if (!detectedFilename) defaultFile = 'script.py';
    } else if (langLower === 'js' || langLower === 'javascript') {
      displayLang = 'JavaScript';
      if (!detectedFilename) defaultFile = 'app.js';
    } else if (langLower === 'ts' || langLower === 'typescript') {
      displayLang = 'TypeScript';
      if (!detectedFilename) defaultFile = 'index.ts';
    } else if (langLower === 'sh' || langLower === 'bash' || langLower === 'zsh') {
      displayLang = 'Terminal';
      if (!detectedFilename) defaultFile = 'command.sh';
    } else if (langLower === 'json') {
      displayLang = 'JSON';
      if (!detectedFilename) defaultFile = 'data.json';
    } else if (langLower === 'sql') {
      displayLang = 'SQL';
      if (!detectedFilename) defaultFile = 'query.sql';
    } else if (langLower === 'html') {
      displayLang = 'HTML';
      if (!detectedFilename) defaultFile = 'index.html';
    } else if (langLower === 'css') {
      displayLang = 'CSS';
      if (!detectedFilename) defaultFile = 'style.css';
    } else if (langLower === 'java') {
      displayLang = 'Java';
      if (!detectedFilename) defaultFile = 'Main.java';
    } else if (langLower === 'c') {
      displayLang = 'C';
      if (!detectedFilename) defaultFile = 'main.c';
    }

    const terminalHtml = `
      <div class="terminal-window" data-lang="${escapeHtml(langLower)}" data-filename="${escapeHtml(defaultFile)}">
        <div class="terminal-header">
          <div class="terminal-header-left">
            <div class="terminal-code-icon">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
                <polyline points="16 18 22 12 16 6"></polyline>
                <polyline points="8 6 2 12 8 18"></polyline>
              </svg>
            </div>
            <span class="terminal-lang-title">${escapeHtml(displayLang)}</span>
          </div>
          <div class="terminal-header-right">
            <button class="btn-terminal-action btn-popout" onclick="openTerminalSnippet(this)" title="Open in Windows editor / Export file">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path>
                <polyline points="15 3 21 3 21 9"></polyline>
                <line x1="10" y1="14" x2="21" y2="3"></line>
              </svg>
            </button>
            <button class="btn-terminal-action btn-copy" onclick="copyTerminalCode(this)" title="Copy code to clipboard">
              <svg class="copy-svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
              </svg>
            </button>
            <button class="btn-terminal-run" onclick="runTerminalCode(this)" title="Execute this script on Windows machine">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
                <polygon points="6 4 19 12 6 20 6 4"></polygon>
              </svg>
              <span>Run</span>
            </button>
          </div>
        </div>
        <div class="terminal-body">
          <pre class="terminal-pre"><code class="language-${escapeHtml(langLower)}">${highlightedCode}</code></pre>
        </div>
      </div>
    `;
    processed = processed.replace(`@@@NEXUS_CODEBLOCK_${idx}@@@`, terminalHtml);
  });

  return `<div class="markdown-body">${processed}</div>`;
}

function copyTerminalCode(btn) {
  const terminalWindow = btn.closest('.terminal-window') || btn.closest('.code-block-container');
  if (!terminalWindow) return;
  const codeEl = terminalWindow.querySelector('code');
  if (!codeEl) return;

  const rawText = codeEl.innerText;
  const originalHtml = btn.innerHTML;

  const onSuccess = () => {
    btn.classList.add('copied');
    btn.innerHTML = `
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#10b981" stroke-width="2.5">
        <polyline points="20 6 9 17 4 12"></polyline>
      </svg>
    `;
    setTimeout(() => {
      btn.classList.remove('copied');
      btn.innerHTML = originalHtml;
    }, 2000);
  };

  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(rawText).then(onSuccess).catch(() => {
      fallbackCopyText(rawText, onSuccess);
    });
  } else {
    fallbackCopyText(rawText, onSuccess);
  }
}

async function runTerminalCode(btn) {
  const terminalWindow = btn.closest('.terminal-window');
  if (!terminalWindow) return;
  const codeEl = terminalWindow.querySelector('code');
  if (!codeEl) return;
  const rawCode = codeEl.innerText.trim();
  const lang = terminalWindow.getAttribute('data-lang') || 'code';
  const filename = terminalWindow.getAttribute('data-filename') || '';

  const originalHtml = btn.innerHTML;
  btn.classList.add('running');
  btn.innerHTML = `<span style="display:inline-block;animation:spin 1s linear infinite;">⏳</span> Running...`;

  try {
    let commandPrompt = "";
    if (filename && filename !== 'snippet.txt' && !filename.startsWith('snippet.')) {
      commandPrompt = `Compile and run '${filename}' in Windows terminal and show output`;
    } else if (lang === 'cpp' || lang === 'c++' || lang === 'c') {
      commandPrompt = `Compile and run this C++ code in Windows terminal and show the execution output:\n\`\`\`cpp\n${rawCode}\n\`\`\``;
    } else if (lang === 'python' || lang === 'py') {
      commandPrompt = `Run this Python code in Windows terminal and show the execution output:\n\`\`\`python\n${rawCode}\n\`\`\``;
    } else if (lang === 'bash' || lang === 'sh' || lang === 'cmd' || lang === 'bat') {
      commandPrompt = `Run this command in Windows terminal and display the output:\n\`\`\`cmd\n${rawCode}\n\`\`\``;
    } else {
      commandPrompt = `Execute this ${lang} program on Windows and show the execution output:\n\`\`\`${lang}\n${rawCode}\n\`\`\``;
    }

    if (typeof submitPrompt === 'function') {
      await submitPrompt(commandPrompt);
    }
  } catch (err) {
    console.error("Failed to run code:", err);
  } finally {
    setTimeout(() => {
      btn.classList.remove('running');
      btn.innerHTML = originalHtml;
    }, 2000);
  }
}

async function openTerminalSnippet(btn) {
  const terminalWindow = btn.closest('.terminal-window');
  if (!terminalWindow) return;
  const codeEl = terminalWindow.querySelector('code');
  if (!codeEl) return;
  const rawCode = codeEl.innerText.trim();
  const filename = terminalWindow.getAttribute('data-filename') || '';

  if (filename && filename !== 'snippet.txt' && !filename.startsWith('snippet.')) {
    if (typeof submitPrompt === 'function') {
      await submitPrompt(`Open '${filename}' in Windows default application`);
    }
  } else {
    const lang = terminalWindow.getAttribute('data-lang') || 'txt';
    const ext = lang === 'cpp' ? 'cpp' : (lang === 'python' ? 'py' : (lang === 'javascript' ? 'js' : lang));
    const blob = new Blob([rawCode], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `code_export.${ext}`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }
}

function fallbackCopyText(text, callback) {
  const textarea = document.createElement('textarea');
  textarea.value = text;
  textarea.style.position = 'fixed';
  textarea.style.opacity = '0';
  document.body.appendChild(textarea);
  textarea.select();
  try {
    document.execCommand('copy');
    if (callback) callback();
  } catch (e) {}
  document.body.removeChild(textarea);
}

window.copyTerminalCode = copyTerminalCode;
window.copyCodeSnippet = copyTerminalCode;
window.runTerminalCode = runTerminalCode;
window.openTerminalSnippet = openTerminalSnippet;
window.renderMarkdown = renderMarkdown;

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

// File Attachment DOM (ChatGPT style)
const attachedFileBar = document.getElementById('attached-file-bar');
const attachedFileIcon = document.getElementById('attached-file-icon');
const attachedFileName = document.getElementById('attached-file-name');
const attachedFileSize = document.getElementById('attached-file-size');
const btnRemoveAttachment = document.getElementById('btn-remove-attachment');
const btnAttach = document.getElementById('btn-attach');
const fileInputAttach = document.getElementById('file-input-attach');

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

// Universal Document Converter DOM
const convertDropZone = document.getElementById('convert-drop-zone');
const fileInputConvert = document.getElementById('file-input-convert');
const convertSelectedFile = document.getElementById('convert-selected-file');
const inputConvertPath = document.getElementById('input-convert-path');
const btnExecuteConvert = document.getElementById('btn-execute-convert');
const convertResultBox = document.getElementById('convert-result-box');
const formatPills = document.querySelectorAll('.btn-fmt-pill');

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
const selectMonitor = document.getElementById('select-monitor');

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

// Attachment and Converter Global State
let currentAttachedFile = null; // { filename, path, size_bytes }
let selectedTargetFormat = 'docx';

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

  // Pre-seed knownTaskIds with past inactive tasks so we don't duplicate on reload
  try {
    const initTasksRes = await fetch(`${API_BASE}/api/tasks?limit=20`);
    if (initTasksRes.ok) {
      const initData = await initTasksRes.json();
      (initData.tasks || []).forEach(t => {
        if (t.status !== 'RUNNING' && t.status !== 'AWAITING_APPROVAL') {
          knownTaskIds.add(t.id);
        }
      });
    }
  } catch (e) {}

  // Polling intervals
  telemetryTimer = setInterval(updateTelemetry, 3000);
  remoteSyncTimer = setInterval(syncRemoteTasks, 1500);
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

// =========================================================================
// FLOATING HUD ALWAYS-ON-TOP & MULTI-SCREEN CONTROLLER
// =========================================================================
function makeElementDraggable(element, handle) {
  if (!element || !handle) return;
  let posX = 0, posY = 0, initialMouseX = 0, initialMouseY = 0;
  handle.style.cursor = 'grab';
  handle.onmousedown = function(e) {
    e = e || window.event;
    e.preventDefault();
    handle.style.cursor = 'grabbing';
    initialMouseX = e.clientX;
    initialMouseY = e.clientY;
    document.onmouseup = function() {
      handle.style.cursor = 'grab';
      document.onmouseup = null;
      document.onmousemove = null;
    };
    document.onmousemove = function(e) {
      e = e || window.event;
      e.preventDefault();
      posX = initialMouseX - e.clientX;
      posY = initialMouseY - e.clientY;
      initialMouseX = e.clientX;
      initialMouseY = e.clientY;
      element.style.top = (element.offsetTop - posY) + 'px';
      element.style.left = (element.offsetLeft - posX) + 'px';
      element.style.transform = 'none';
    };
  };
}

function openFloatingHudWindow() {
  // If Document Picture-in-Picture is supported (Chrome 116+, Edge 116+)
  // it provides a REAL native Always-On-Top floating window across all screens!
  if ('documentPictureInPicture' in window) {
    window.documentPictureInPicture.requestWindow({
      width: 580,
      height: 125
    }).then(pipWin => {
      [...document.styleSheets].forEach(s => {
        try {
          const st = document.createElement('style');
          st.textContent = [...s.cssRules].map(r => r.cssText).join('');
          pipWin.document.head.appendChild(st);
        } catch (e) {}
      });
      const link = document.createElement('link');
      link.rel = 'stylesheet';
      link.href = 'https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@500;700&display=swap';
      pipWin.document.head.appendChild(link);

      const hudClone = floatingHudBar.cloneNode(true);
      hudClone.classList.remove('hidden');
      hudClone.style.position = 'static';
      hudClone.style.transform = 'none';
      hudClone.style.boxShadow = 'none';
      hudClone.style.width = '100%';
      pipWin.document.body.style.margin = '0';
      pipWin.document.body.style.background = '#090d16';
      pipWin.document.body.style.display = 'flex';
      pipWin.document.body.style.alignItems = 'center';
      pipWin.document.body.style.justifyContent = 'center';
      pipWin.document.body.style.height = '100vh';
      pipWin.document.body.appendChild(hudClone);

      const pInput = hudClone.querySelector('#hud-input');
      const pSend = hudClone.querySelector('#hud-btn-send');
      const pClose = hudClone.querySelector('#hud-btn-close');

      if (pInput) {
        pInput.focus();
        pInput.addEventListener('keydown', (e) => {
          if (e.key === 'Enter') {
            e.preventDefault();
            const text = pInput.value.trim();
            if (text) {
              pInput.value = '';
              submitPrompt(text);
              showToast(`HUD Executing: "${text}"`, 'info');
            }
          }
        });
      }
      if (pSend && pInput) {
        pSend.addEventListener('click', () => {
          const text = pInput.value.trim();
          if (text) {
            pInput.value = '';
            submitPrompt(text);
            showToast(`HUD Executing: "${text}"`, 'info');
          }
        });
      }
      if (pClose) {
        pClose.addEventListener('click', () => pipWin.close());
      }
    }).catch(err => {
      console.warn('Document PiP fallback:', err);
      openHudPopupWindow();
    });
  } else {
    openHudPopupWindow();
  }
}

function openHudPopupWindow() {
  const left = Math.max(50, (window.screen.width - 600) / 2);
  const popWin = window.open(
    '/desktop/hud.html',
    'NexusFloatingHUD',
    `width=600,height=135,left=${left},top=60,resizable=yes,scrollbars=no,status=no,toolbar=no`
  );
  if (!popWin || popWin.closed || typeof popWin.closed === 'undefined') {
    floatingHudBar.classList.remove('hidden');
    showToast('Floating HUD opened in-page (Allow popups for Always-on-Top multi-screen HUD)', 'info');
  } else {
    showToast('Floating HUD launched. Drag to any monitor or pin Always-on-Top.', 'success');
  }
}

async function loadMonitors() {
  if (!selectMonitor) return;
  try {
    const res = await fetch(`${API_BASE}/api/monitors`);
    if (!res.ok) return;
    const data = await res.json();
    const monitors = data.monitors || [];
    if (monitors.length > 0) {
      selectMonitor.innerHTML = '<option value="active">Active Foreground Screen</option>';
      monitors.forEach(m => {
        const opt = document.createElement('option');
        opt.value = m.index;
        opt.textContent = `${m.label} (${m.width}x${m.height})`;
        selectMonitor.appendChild(opt);
      });
    }
  } catch (e) {
    console.debug('loadMonitors note:', e);
  }
}

// 3. CONSOLE & PROMPT EXECUTION
// =========================================================================
async function submitPrompt(text) {
  const rawInput = (text || promptInput.value || hudInput.value).trim();
  if (!rawInput && !currentAttachedFile) return;

  // Compose full instruction incorporating any attached file (ChatGPT style)
  let fullPrompt = rawInput;
  let displayPrompt = rawInput;
  if (currentAttachedFile) {
    fullPrompt = `[Attached file: ${currentAttachedFile.path}]\n${rawInput || "Convert this file or summarize its contents"}`;
    displayPrompt = `📎 ${currentAttachedFile.filename}\n${rawInput || "Convert this file or summarize its contents"}`;
    clearAttachedFile();
  }

  welcomeCard.style.display = 'none';
  appendUserMessage(displayPrompt);
  promptInput.value = '';
  hudInput.value = '';

  const permMode = selectPermissionMode.value;
  const taskCard = createTaskCard(rawInput || (currentAttachedFile ? currentAttachedFile.filename : "Mission"));
  messageThread.appendChild(taskCard);
  chatViewport.scrollTop = chatViewport.scrollHeight;

  try {
    const res = await fetch(`${API_BASE}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        messages: [{ role: "user", content: fullPrompt }],
        permission_mode: permMode
      })
    });
    const data = await res.json();
    activeTaskId = data.task_id;
    taskCard.id = `task-card-${activeTaskId}`;
    knownTaskIds.add(activeTaskId);
    pollTaskStatus(activeTaskId, taskCard);
    loadRecentTasks();
  } catch (e) {
    taskCard.querySelector('.task-status').innerText = "Network Error";
    taskCard.querySelector('.task-status').className = "task-status failed";
  }
}

function appendUserMessage(text, isRemote = false) {
  const msg = document.createElement('div');
  msg.className = 'message-user';
  if (isRemote) {
    msg.innerHTML = `
      <div style="font-size:10.5px; color:#38bdf8; font-weight:700; margin-bottom:4px; display:flex; align-items:center; gap:5px; text-transform:uppercase; letter-spacing:0.5px;">
        <span>📱</span>
        <span>Phone Remote Command</span>
      </div>
      <div>${text}</div>
    `;
  } else {
    msg.innerText = text;
  }
  messageThread.appendChild(msg);
}

async function syncRemoteTasks() {
  try {
    const res = await fetch(`${API_BASE}/api/tasks?limit=5`);
    if (!res.ok) return;
    const data = await res.json();
    const tasks = data.tasks || [];
    if (tasks.length === 0) return;

    for (const t of tasks) {
      if (knownTaskIds.has(t.id)) continue;

      let taskTime = 0;
      if (t.created_at) {
        taskTime = new Date(t.created_at.replace(' ', 'T') + 'Z').getTime();
      }
      const isNewSessionTask = taskTime >= (sessionInitTime - 5000);
      const isRunning = ['RUNNING', 'AWAITING_APPROVAL', 'QUEUED'].includes(t.status);

      if (isRunning || isNewSessionTask) {
        if (document.getElementById(`task-card-${t.id}`)) {
          knownTaskIds.add(t.id);
          continue;
        }
        knownTaskIds.add(t.id);
        activeTaskId = t.id;

        // Auto-switch to Console view so desktop user immediately sees the activity
        const consoleTab = document.querySelector('[data-tab="tab-console"]');
        if (consoleTab && !consoleTab.classList.contains('active')) {
          consoleTab.click();
        }
        welcomeCard.style.display = 'none';

        // Render user prompt with Phone Remote indicator
        appendUserMessage(t.user_prompt, true);

        // Mount live task card
        const card = createTaskCard(t.user_prompt);
        card.id = `task-card-${t.id}`;
        card.querySelector('.task-id-badge').innerText = `TASK // ${t.id}`;
        messageThread.appendChild(card);
        chatViewport.scrollTop = chatViewport.scrollHeight;

        // Start polling this task until finished
        pollTaskStatus(t.id, card);
        loadRecentTasks();
        break;
      }
    }
  } catch (e) {}
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
  // Cancel previous polling for THIS specific task if already running
  if (activePollTimers.has(taskId)) {
    clearInterval(activePollTimers.get(taskId));
    activePollTimers.delete(taskId);
  }

  const timer = setInterval(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/tasks/${taskId}`);
      if (res.status === 404) {
        clearInterval(timer);
        activePollTimers.delete(taskId);
        return;
      }
      if (!res.ok) return;
      const task = await res.json();

      const liveCard = document.getElementById(`task-card-${taskId}`) || card;
      const idBadge = liveCard.querySelector('.task-id-badge');
      if (idBadge) idBadge.innerText = `TASK // ${task.id}`;
      const statusBadge = liveCard.querySelector('.task-status');
      if (statusBadge && task.status) {
        statusBadge.innerText = task.status;
        statusBadge.className = `task-status ${task.status.toLowerCase()}`;
      }

      // Update Steps
      const stepsContainer = liveCard.querySelector('.steps-container');
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
              <span class="step-agent-pill">${escapeHtml(s.agent)}</span>
              <span><b>Step ${s.step_number}:</b> ${escapeHtml(s.title)}</span>
            </div>
            <span class="step-status-tag ${isDone ? 'completed' : (isCurrent ? 'running' : '')}">
              ${isDone ? '✓ Verified' : (isCurrent ? '⚡ In Progress' : 'Pending')}
            </span>
          `;
          stepsContainer.appendChild(sItem);
        });
      } else if (task.status === 'COMPLETED') {
        stepsContainer.innerHTML = `
          <div class="step-item">
            <div class="step-left">
              <span class="step-agent-pill">Nexus Orchestrator</span>
              <span>Conversational response generated</span>
            </div>
            <span class="step-status-tag completed">✓ Verified</span>
          </div>
        `;
      }

      // Check for approval requirements
      const existingAppBox = card.querySelector('.approval-box');
      if (task.status === 'AWAITING_APPROVAL' && task.pending_approval) {
        renderApprovalPrompt(card, task.pending_approval);
      } else if (existingAppBox && task.status !== 'AWAITING_APPROVAL') {
        existingAppBox.remove();
      }

      // Finished States
      if (['COMPLETED', 'FAILED', 'CANCELLED'].includes(task.status)) {
        clearInterval(timer);
        activePollTimers.delete(taskId);

        // Ensure approval box is cleaned up if lingering
        const lingeringAppBox = liveCard.querySelector('.approval-box');
        if (lingeringAppBox) lingeringAppBox.remove();

        const summaryBox = liveCard.querySelector('.task-summary-box');
        if (summaryBox) {
          summaryBox.classList.remove('hidden');

          const report = task.completion_report || {};
          const summaryText = task.error_message 
            ? `<b style="color:var(--accent-crimson)">Failed:</b> ${escapeHtml(task.error_message)}`
            : (report.summary || plan.conversational_response || "Task executed and verified on your Windows desktop.");

          let formattedHtml = summaryText;
          try {
            formattedHtml = task.error_message ? summaryText : renderMarkdown(summaryText);
          } catch (mErr) {
            console.warn('renderMarkdown error:', mErr);
            formattedHtml = escapeHtml(summaryText).replace(/\n/g, '<br>');
          }

          const plainForSpeech = (typeof summaryText === 'string') 
            ? summaryText.replace(/<[^>]*>/g, '').replace(/[`*#]/g, '')
            : 'Mission complete';

          summaryBox.innerHTML = `
            <div class="summary-content">${formattedHtml}</div>
            <button class="btn-mini-new" style="margin-top:10px;" onclick="playTts(\`${encodeURIComponent(plainForSpeech)}\`)">🔊 Listen Voice</button>
          `;
        }

        // Check if any document (.pptx or .pdf) was created!
        try {
          checkForCreatedDocument(card, task);
          loadDocuments();
        } catch (docErr) {
          console.warn('checkForCreatedDocument note:', docErr);
        }

        if (typeof chatViewport !== 'undefined' && chatViewport) {
          chatViewport.scrollTop = chatViewport.scrollHeight;
        }
      }
    } catch (e) {
      console.error('pollTaskStatus error:', e);
    }
  }, 750);

  activePollTimers.set(taskId, timer);
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
        const taskId = task ? (task.id || task.task_id) : null;
        if (taskId && typeof taskId === 'string' && taskId.trim().length > 0) {
          const matched = data.documents.find(d => d.task_id && d.task_id === taskId);
          if (matched) {
            targetDoc = matched;
          }
        }
        if (!targetDoc) {
          const summaryStr = (report.summary || '').toLowerCase();
          const promptStr = (task.user_prompt || '').toLowerCase();
          const foundInSummary = data.documents.find(d => {
            if (!d.filename || typeof d.filename !== 'string' || d.filename.length < 5) return false;
            const fnLower = d.filename.toLowerCase();
            const stemLower = fnLower.replace(/\.[^/.]+$/, "");
            return (summaryStr.length > 0 && (summaryStr.includes(fnLower) || summaryStr.includes(stemLower))) ||
                   (promptStr.length > 0 && (promptStr.includes(fnLower) || promptStr.includes(stemLower)));
          });
          if (foundInSummary) {
            targetDoc = foundInSummary;
          }
        }
      }
    } catch (e) {}
  }

  // If no document was created by this task, ensure shelf card is hidden and cleared
  if (!targetDoc) {
    const docCard = card.querySelector('.created-doc-card');
    if (docCard) {
      docCard.classList.add('hidden');
      docCard.innerHTML = '';
    }
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
    appBox.style = "background:rgba(245, 158, 11, 0.08); border:1px solid rgba(245, 158, 11, 0.35); padding:14px; border-radius:8px; margin-top:12px; transition: all 0.3s ease;";
    card.appendChild(appBox);
  }

  const apprId = approval.id || approval.approval_id;
  // If user already clicked an authorization decision on this card, preserve resolving UI
  if (appBox.dataset.apprId === apprId && appBox.dataset.status === 'resolving') {
    return;
  }
  appBox.dataset.apprId = apprId;

  const tool = approval.tool || approval.tool_name || "System Operation";
  const title = approval.title || approval.reason || `Execute ${tool}`;
  const risk = approval.risk_level || "MEDIUM";

  appBox.innerHTML = `
    <div style="font-size:12px; font-weight:700; color:#fbbf24; margin-bottom:6px; display:flex; align-items:center; gap:6px;">
      <span>⚠️</span>
      <span>ACTION REQUIRES AUTHORIZATION</span>
    </div>
    <div style="font-size:12.5px; color:#f8fafc; font-weight:600; margin-bottom:4px;">${escapeHtml(title)}</div>
    <div style="font-size:11px; color:#94a3b8; margin-bottom:12px;">Tool: <code style="color:#cbd5e1;">${escapeHtml(tool)}</code> &bull; Risk Level: <span style="color:#f59e0b; font-weight:600;">${escapeHtml(risk)}</span></div>
    <div class="approval-btn-group" style="display:flex; gap:8px; flex-wrap:wrap;">
      <button class="btn-accent-action" onclick="resolveApproval('${apprId}', 'allow_once', this)">Allow Once</button>
      <button class="btn-secondary-action" onclick="resolveApproval('${apprId}', 'allow_session', this)">Allow for Session</button>
      <button class="btn-emergency" onclick="resolveApproval('${apprId}', 'deny', this)">Deny</button>
    </div>
  `;
}

async function resolveApproval(approvalId, decision, btnEl) {
  const appBox = document.querySelector(`.approval-box[data-appr-id="${approvalId}"]`) ||
                 (btnEl ? btnEl.closest('.approval-box') : document.querySelector('.approval-box'));

  const actionText = decision === 'allow_once' ? 'Allow Once' : decision === 'allow_session' ? 'Allow for Session' : 'Deny';
  const isAllow = decision !== 'deny';
  const badgeColor = isAllow ? '#10b981' : '#ef4444';
  const badgeIcon = isAllow ? '✓' : '✕';

  if (appBox) {
    appBox.dataset.status = 'resolving';
    // Immediately disable buttons to prevent duplicate triggers
    const buttons = appBox.querySelectorAll('button');
    buttons.forEach(b => {
      b.disabled = true;
      b.style.pointerEvents = 'none';
      b.style.opacity = '0.5';
    });

    const btnGroup = appBox.querySelector('.approval-btn-group');
    if (btnGroup) {
      btnGroup.innerHTML = `
        <div style="display:flex; align-items:center; gap:8px; padding:7px 12px; background:rgba(0,0,0,0.3); border-radius:6px; border:1px solid ${badgeColor};">
          <span style="font-size:13px; font-weight:bold; color:${badgeColor};">${badgeIcon}</span>
          <span style="font-size:12px; color:${badgeColor}; font-weight:600;">
            ${isAllow ? 'Authorized' : 'Rejected'}: Submitting "${actionText}"...
          </span>
        </div>
      `;
    }
  }

  try {
    const res = await fetch(`${API_BASE}/api/approvals/${approvalId}/decision`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decision })
    });

    if (res.ok) {
      // Fade out and remove smoothly once acknowledged
      if (appBox) {
        setTimeout(() => {
          appBox.style.transition = 'all 0.3s ease-out';
          appBox.style.opacity = '0';
          appBox.style.transform = 'translateY(-6px)';
          setTimeout(() => {
            if (appBox && appBox.parentNode) {
              appBox.remove();
            }
          }, 300);
        }, 400);
      }
    }
  } catch (e) {
    if (appBox) {
      appBox.dataset.status = 'error';
      appBox.innerHTML += `<div style="font-size:11px; color:#ef4444; margin-top:8px;">⚠️ Network error: Could not reach assistant server.</div>`;
    }
  }
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
    const filename = docPath ? docPath.split(/[\\/]/).pop() : "";
    const res = await fetch(`${API_BASE}/api/documents/open`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ doc_id: docId || "", path: docPath || "", filename: filename || "" })
    });
    const data = await res.json();
    if (res.ok && data.success) {
      showToast(`🚀 Opened in Windows: ${data.message || 'File launched'}`);
    } else {
      const errDetail = Array.isArray(data.detail) ? (data.detail[0]?.msg || JSON.stringify(data.detail)) : (typeof data.detail === 'string' ? data.detail : (data.error || "File not found on disk."));
      alert("Could not open file: " + errDetail);
      await loadDocuments();
    }
  } catch (e) {
    alert("Failed to open document: " + e.message);
  }
}

async function revealGeneratedDoc(docId, docPath) {
  try {
    const filename = docPath ? docPath.split(/[\\/]/).pop() : "";
    const res = await fetch(`${API_BASE}/api/documents/reveal`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ doc_id: docId || "", path: docPath || "", filename: filename || "" })
    });
    const data = await res.json();
    if (res.ok && data.success) {
      const fileName = data.path ? data.path.split(/[\\/]/).pop() : 'Document';
      showToast(`📁 Highlighted in File Explorer: ${fileName}`);
    } else {
      const errDetail = Array.isArray(data.detail) ? (data.detail[0]?.msg || JSON.stringify(data.detail)) : (typeof data.detail === 'string' ? data.detail : (data.error || "File not found."));
      alert("Could not reveal file: " + errDetail);
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
// 5A-1. CHAT FILE ATTACHMENT & CONVERTER CONTROLS (ChatGPT Style)
// =========================================================================
function getFileIcon(filename) {
  const ext = (filename.split('.').pop() || '').toLowerCase();
  if (ext === 'pdf') return '📑';
  if (ext === 'docx' || ext === 'doc') return '📝';
  if (ext === 'xlsx' || ext === 'xls') return '📈';
  if (ext === 'pptx' || ext === 'ppt') return '📊';
  if (['png', 'jpg', 'jpeg', 'webp', 'gif'].includes(ext)) return '🖼️';
  if (['csv', 'txt', 'md', 'json'].includes(ext)) return '📄';
  return '📎';
}

async function uploadFileForAttachment(file) {
  if (!file) return;
  try {
    if (attachedFileBar) {
      attachedFileIcon.innerText = '⏳';
      attachedFileName.innerText = `Uploading ${file.name}...`;
      attachedFileSize.innerText = `${Math.round(file.size / 1024)} KB`;
      attachedFileBar.classList.remove('hidden');
    }
    const formData = new FormData();
    formData.append('file', file);
    const res = await fetch(`${API_BASE}/api/files/upload`, {
      method: 'POST',
      body: formData
    });
    if (!res.ok) {
      const err = await res.json();
      alert(`Upload failed: ${err.detail || 'Unknown error'}`);
      clearAttachedFile();
      return;
    }
    const data = await res.json();
    currentAttachedFile = {
      filename: data.filename,
      path: data.path,
      size_bytes: data.size_bytes
    };
    if (attachedFileBar) {
      attachedFileIcon.innerText = getFileIcon(data.filename);
      attachedFileName.innerText = data.filename;
      attachedFileSize.innerText = `${Math.round(data.size_bytes / 1024)} KB`;
      attachedFileBar.classList.remove('hidden');
    }
    showToast(`📎 Attached: ${data.filename}`);
  } catch (e) {
    alert(`File upload error: ${e.message}`);
    clearAttachedFile();
  }
}

function clearAttachedFile() {
  currentAttachedFile = null;
  if (fileInputAttach) fileInputAttach.value = '';
  if (attachedFileBar) attachedFileBar.classList.add('hidden');
}

function setupChatAttachmentEvents() {
  if (btnAttach && fileInputAttach) {
    btnAttach.addEventListener('click', () => fileInputAttach.click());
    fileInputAttach.addEventListener('change', async () => {
      const f = fileInputAttach.files[0];
      if (f) await uploadFileForAttachment(f);
    });
  }

  if (btnRemoveAttachment) {
    btnRemoveAttachment.addEventListener('click', clearAttachedFile);
  }

  // Drag and drop onto prompt container / chat viewport
  const dropTargets = [document.querySelector('.input-glass-box'), chatViewport];
  dropTargets.forEach(target => {
    if (!target) return;
    ['dragenter', 'dragover'].forEach(eventName => {
      target.addEventListener(eventName, (e) => {
        e.preventDefault();
        e.stopPropagation();
        if (target.classList.contains('input-glass-box')) {
          target.style.borderColor = '#38bdf8';
          target.style.boxShadow = '0 0 16px rgba(56, 189, 248, 0.35)';
        }
      }, false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
      target.addEventListener(eventName, (e) => {
        e.preventDefault();
        e.stopPropagation();
        if (target.classList.contains('input-glass-box')) {
          target.style.borderColor = '';
          target.style.boxShadow = '';
        }
      }, false);
    });

    target.addEventListener('drop', async (e) => {
      const dt = e.dataTransfer;
      if (dt.files && dt.files.length > 0) {
        await uploadFileForAttachment(dt.files[0]);
      }
    });
  });
}

function setupConverterControls() {
  // Format Pills
  if (formatPills && formatPills.length > 0) {
    formatPills.forEach(pill => {
      pill.addEventListener('click', () => {
        formatPills.forEach(p => p.classList.remove('active'));
        pill.classList.add('active');
        selectedTargetFormat = pill.getAttribute('data-fmt') || 'docx';
      });
    });
  }

  // Drop Zone
  if (convertDropZone && fileInputConvert) {
    convertDropZone.addEventListener('click', (e) => {
      if (e.target !== fileInputConvert) {
        fileInputConvert.click();
      }
    });

    fileInputConvert.addEventListener('change', async () => {
      const f = fileInputConvert.files[0];
      if (f) await handleConverterUpload(f);
    });

    ['dragenter', 'dragover'].forEach(eventName => {
      convertDropZone.addEventListener(eventName, (e) => {
        e.preventDefault();
        e.stopPropagation();
        convertDropZone.style.borderColor = '#38bdf8';
        convertDropZone.style.background = 'rgba(56, 189, 248, 0.1)';
      }, false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
      convertDropZone.addEventListener(eventName, (e) => {
        e.preventDefault();
        e.stopPropagation();
        convertDropZone.style.borderColor = 'rgba(56, 189, 248, 0.35)';
        convertDropZone.style.background = 'rgba(30, 41, 59, 0.3)';
      }, false);
    });

    convertDropZone.addEventListener('drop', async (e) => {
      const dt = e.dataTransfer;
      const f = dt.files[0];
      if (f) await handleConverterUpload(f);
    });
  }

  if (btnExecuteConvert) {
    btnExecuteConvert.addEventListener('click', executeDocumentConversion);
  }
}

async function handleConverterUpload(file) {
  try {
    if (convertSelectedFile) convertSelectedFile.innerText = `Uploading ${file.name}...`;
    const formData = new FormData();
    formData.append('file', file);
    const res = await fetch(`${API_BASE}/api/files/upload`, {
      method: 'POST',
      body: formData
    });
    if (!res.ok) {
      const err = await res.json();
      if (convertSelectedFile) convertSelectedFile.innerText = `Upload failed: ${err.detail || 'Error'}`;
      return;
    }
    const data = await res.json();
    if (inputConvertPath) inputConvertPath.value = data.path;
    if (convertSelectedFile) {
      convertSelectedFile.innerText = `Ready: ${data.filename} (${Math.round(data.size_bytes / 1024)} KB)`;
    }
  } catch (e) {
    if (convertSelectedFile) convertSelectedFile.innerText = `Upload error: ${e.message}`;
  }
}

async function executeDocumentConversion() {
  const sourcePath = (inputConvertPath ? inputConvertPath.value : '').trim();
  if (!sourcePath) {
    showConvertResult('Please upload a file or enter a local folder / file path to convert.', false);
    return;
  }

  if (btnExecuteConvert) {
    btnExecuteConvert.disabled = true;
    btnExecuteConvert.innerHTML = '<span>⏳</span><span>Converting...</span>';
  }
  showConvertResult('Processing document conversion with native engines...', true, true);

  try {
    const res = await fetch(`${API_BASE}/api/files/convert`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        source_path: sourcePath,
        target_format: selectedTargetFormat
      })
    });
    const data = await res.json();
    if (data.success) {
      const msg = data.is_batch
        ? `Batch conversion complete: Converted ${data.converted_count} file(s) to ${selectedTargetFormat.toUpperCase()}.`
        : `Successfully converted to ${selectedTargetFormat.toUpperCase()}: ${data.filename || 'Deliverable ready'}.`;
      showConvertResult(msg, true);
      await loadDocuments();
      showToast(`⚡ Conversion complete: ${selectedTargetFormat.toUpperCase()}`);
    } else {
      showConvertResult(`Conversion failed: ${data.error || 'Unknown error'}`, false);
    }
  } catch (e) {
    showConvertResult(`Conversion error: ${e.message}`, false);
  } finally {
    if (btnExecuteConvert) {
      btnExecuteConvert.disabled = false;
      btnExecuteConvert.innerHTML = '<span>⚡</span><span>Convert Document(s)</span>';
    }
  }
}

function showConvertResult(msg, success, isPending = false) {
  if (!convertResultBox) return;
  convertResultBox.classList.remove('hidden');
  const bg = isPending ? 'rgba(56, 189, 248, 0.1)' : (success ? 'rgba(16, 185, 129, 0.12)' : 'rgba(239, 68, 68, 0.12)');
  const border = isPending ? '#38bdf8' : (success ? '#10b981' : '#ef4444');
  const color = isPending ? '#38bdf8' : (success ? '#34d399' : '#f87171');
  const icon = isPending ? '⏳' : (success ? '✅' : '❌');
  convertResultBox.style = `background:${bg}; border:1px solid ${border}; border-radius:6px; padding:10px 14px; font-size:12px; color:${color}; margin-top:12px;`;
  convertResultBox.innerHTML = `<span>${icon}</span> <span style="margin-left:6px;">${msg}</span>`;
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

let liveScreenMirrorTimer = null;
function toggleLiveScreenMirror() {
  const btn = document.getElementById('btn-stream-preview');
  if (liveScreenMirrorTimer) {
    clearInterval(liveScreenMirrorTimer);
    liveScreenMirrorTimer = null;
    if (btn) {
      btn.innerText = '🔴 Live Mirror';
      btn.style.background = '';
    }
    showToast('Live Screen Mirror stopped', 'info');
  } else {
    refreshVisionPreview();
    liveScreenMirrorTimer = setInterval(refreshVisionPreview, 180);
    if (btn) {
      btn.innerText = '🟢 Streaming (5 FPS)';
      btn.style.background = 'rgba(16, 185, 129, 0.25)';
    }
    showToast('Live Screen Mirror active (5 FPS)', 'success');
  }
}

function refreshVisionPreview() {
  if (visionScreenImg) {
    const selMon = (selectMonitor && selectMonitor.value) ? selectMonitor.value : 'active';
    visionScreenImg.src = `${API_BASE}/api/screenshot?monitor=${selMon}&t=${Date.now()}`;
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

async function renderPastTask(task) {
  document.querySelector('[data-tab="tab-console"]').click();
  welcomeCard.style.display = 'none';
  messageThread.innerHTML = '';
  appendUserMessage(task.user_prompt);

  // Fetch full task details to guarantee complete completion_report and actions
  let fullTask = task;
  try {
    const res = await fetch(`${API_BASE}/api/tasks/${task.id}`);
    if (res.ok) {
      fullTask = await res.json();
    }
  } catch (e) {}

  const card = createTaskCard(fullTask.user_prompt);
  card.querySelector('.task-id-badge').innerText = `TASK // ${fullTask.id}`;
  const statusBadge = card.querySelector('.task-status');
  statusBadge.innerText = fullTask.status;
  statusBadge.className = `task-status ${fullTask.status.toLowerCase()}`;

  // Populate steps container accurately for past task!
  const stepsContainer = card.querySelector('.steps-container');
  const plan = fullTask.plan || {};
  const steps = plan.steps || [];

  if (steps.length > 0) {
    stepsContainer.innerHTML = '';
    steps.forEach(s => {
      const isDone = fullTask.status === 'COMPLETED';
      const sItem = document.createElement('div');
      sItem.className = 'step-item';
      sItem.innerHTML = `
        <div class="step-left">
          <span class="step-agent-pill">${escapeHtml(s.agent)}</span>
          <span><b>Step ${s.step_number}:</b> ${escapeHtml(s.title)}</span>
        </div>
        <span class="step-status-tag ${isDone ? 'completed' : ''}">
          ${isDone ? '✓ Verified' : 'Executed'}
        </span>
      `;
      stepsContainer.appendChild(sItem);
    });
  } else if (fullTask.status === 'COMPLETED') {
    stepsContainer.innerHTML = `
      <div class="step-item">
        <div class="step-left">
          <span class="step-agent-pill">Nexus Orchestrator</span>
          <span>Conversational response generated</span>
        </div>
        <span class="step-status-tag completed">✓ Verified</span>
      </div>
    `;
  }

  // Ensure approval prompt does not linger on historical completed tasks
  const lingeringAppBox = card.querySelector('.approval-box');
  if (lingeringAppBox) lingeringAppBox.remove();

  const summaryBox = card.querySelector('.task-summary-box');
  summaryBox.classList.remove('hidden');
  const report = fullTask.completion_report || {};
  const summaryText = report.summary || fullTask.error_message || (plan.conversational_response || 'Completed.');
  const formattedHtml = fullTask.error_message 
    ? `<b style="color:var(--accent-crimson)">Failed:</b> ${escapeHtml(fullTask.error_message)}` 
    : renderMarkdown(summaryText);

  summaryBox.innerHTML = `
    <div class="summary-content">${formattedHtml}</div>
    <button class="btn-mini-new" style="margin-top:10px;" onclick="playTts(\`${encodeURIComponent(summaryText.replace(/<[^>]*>/g, ''))}\`)">🔊 Listen Voice</button>
  `;

  await checkForCreatedDocument(card, fullTask);
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
  btnToggleHud.addEventListener('click', openFloatingHudWindow);
  if (selectMonitor) {
    selectMonitor.addEventListener('change', refreshVisionPreview);
    loadMonitors();
  }

  const btnStreamPreview = document.getElementById('btn-stream-preview');
  if (btnStreamPreview) {
    btnStreamPreview.addEventListener('click', toggleLiveScreenMirror);
  }
  makeElementDraggable(floatingHudBar, floatingHudBar.querySelector('.hud-handle'));
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

  // Setup Attachment and Converter Controls
  setupChatAttachmentEvents();
  setupConverterControls();

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

    recognizer.onerror = (evt) => {
      btnMic.classList.remove('active');
      isListening = false;
      const err = evt && evt.error ? evt.error : 'unknown';
      if (err === 'not-allowed') {
        showToast('Microphone access denied. Please enable microphone permissions in Windows Settings.', 'error');
      } else if (err === 'no-speech') {
        showToast('No speech detected. Please speak into your microphone.', 'info');
      } else {
        showToast(`Speech recognition error (${err}).`, 'warning');
      }
    };
  }
}

window.addEventListener('DOMContentLoaded', init);
