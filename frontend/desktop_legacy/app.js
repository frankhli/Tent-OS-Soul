/**
 * Tent OS Soul Intercom — 前端核心逻辑
 */

const WS_URL = `ws://${location.host}/ws`;
const API_BASE = `/api/v1`;
const USER_ID = localStorage.getItem('tent_user_id') || 'web_user';
if (!localStorage.getItem('tent_user_id')) {
  localStorage.setItem('tent_user_id', USER_ID);
}

let ws = null;
let sessionId = null;
let isMicOn = false;
let isCamOn = false;
let mediaRecorder = null;
let recordedChunks = [];

// ========== 初始化 ==========
document.addEventListener('DOMContentLoaded', () => {
  connectWebSocket();
  loadSoulCompleteness();
  drawSoulOrb(0);
});

// ========== WebSocket ==========
function connectWebSocket() {
  ws = new WebSocket(WS_URL);
  
  ws.onopen = () => {
    console.log('[WS] 已连接');
  };
  
  ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    handleWsMessage(msg);
  };
  
  ws.onclose = () => {
    console.log('[WS] 断开，5秒后重连...');
    setTimeout(connectWebSocket, 5000);
  };
  
  ws.onerror = (err) => {
    console.error('[WS] 错误:', err);
  };
}

function handleWsMessage(msg) {
  const type = msg.type;
  const payload = msg.payload || {};
  
  switch (type) {
    case 'chat.completed':
      appendAiMessage(payload.content || '', payload.reasoning || '');
      break;
    case 'chat.stream_chunk':
      appendStreamChunk(payload);
      break;
    case 'chat.message_accepted':
      sessionId = payload.session_id;
      break;
    case 'ai.emotion':
      updateAvatarEmotion(payload.emotion);
      break;
    case 'task.completed':
      appendSystemMessage('✅ 任务已完成');
      break;
    case 'task.failed':
      appendSystemMessage('❌ 任务失败: ' + (payload.error || '未知错误'));
      break;
    case 'approval.request':
      appendApprovalRequest(payload);
      break;
    case 'system.health':
      // 忽略健康状态
      break;
    default:
      console.log('[WS]', type, payload);
  }
}

// ========== 聊天 ==========
function sendMessage() {
  const input = document.getElementById('chat-input');
  const text = input.value.trim();
  if (!text) return;
  
  appendUserMessage(text);
  input.value = '';
  input.style.height = 'auto';
  
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({
      type: 'chat.message',
      payload: {
        session_id: sessionId || `ws_${Date.now().toString(36)}`,
        user_id: USER_ID,
        content: text,
      }
    }));
  }
}

let currentStreamEl = null;

function appendUserMessage(text) {
  const container = document.getElementById('chat-history');
  const div = document.createElement('div');
  div.className = 'flex justify-end';
  div.innerHTML = `<div class="chat-bubble-user p-3 max-w-xl text-sm text-slate-800">${escapeHtml(text)}</div>`;
  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
}

function appendAiMessage(text, reasoning) {
  const container = document.getElementById('chat-history');
  const div = document.createElement('div');
  div.className = 'flex justify-start';
  let html = `<div class="chat-bubble-ai p-3 max-w-xl text-sm text-slate-800">`;
  if (reasoning) {
    html += `<div class="text-xs text-slate-400 mb-1 italic">思考: ${escapeHtml(reasoning.substring(0, 100))}...</div>`;
  }
  html += `${formatMessage(text)}</div>`;
  div.innerHTML = html;
  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
  currentStreamEl = null;
  
  // 每次AI回复后更新灵魂完成度
  setTimeout(loadSoulCompleteness, 1000);
}

function appendStreamChunk(payload) {
  if (!currentStreamEl) {
    const container = document.getElementById('chat-history');
    const div = document.createElement('div');
    div.className = 'flex justify-start';
    div.innerHTML = `<div class="chat-bubble-ai p-3 max-w-xl text-sm text-slate-800"><span class="stream-content"></span><span class="animate-pulse">▌</span></div>`;
    container.appendChild(div);
    container.scrollTop = container.scrollHeight;
    currentStreamEl = div.querySelector('.stream-content');
  }
  currentStreamEl.textContent += payload.content || payload.chunk || '';
  const container = document.getElementById('chat-history');
  container.scrollTop = container.scrollHeight;
}

function appendSystemMessage(text) {
  const container = document.getElementById('chat-history');
  const div = document.createElement('div');
  div.className = 'flex justify-center';
  div.innerHTML = `<span class="text-xs text-slate-400 bg-slate-100 px-3 py-1 rounded-full">${escapeHtml(text)}</span>`;
  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
}

function appendApprovalRequest(payload) {
  const container = document.getElementById('chat-history');
  const div = document.createElement('div');
  div.className = 'flex justify-center';
  div.innerHTML = `
    <div class="bg-amber-50 border border-amber-200 rounded-xl p-4 max-w-lg">
      <p class="text-sm font-medium text-amber-800 mb-2">⚠️ 需要你的审批</p>
      <p class="text-xs text-amber-700 mb-3">${escapeHtml(JSON.stringify(payload.plan || {})).substring(0, 200)}</p>
      <div class="flex gap-2">
        <button onclick="sendApproval('${payload.session_id}', true)" class="px-4 py-1.5 bg-green-600 text-white text-xs rounded-lg hover:bg-green-700">批准</button>
        <button onclick="sendApproval('${payload.session_id}', false)" class="px-4 py-1.5 bg-red-600 text-white text-xs rounded-lg hover:bg-red-700">拒绝</button>
      </div>
    </div>
  `;
  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
}

function sendApproval(sid, approved) {
  fetch(`${API_BASE}/approval/${sid}`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({approved})
  });
}

// ========== 灵魂完成度 ==========
async function loadSoulCompleteness() {
  try {
    const res = await fetch(`${API_BASE}/soul/completeness/${USER_ID}`);
    const data = await res.json();
    if (data.overall !== undefined) {
      updateProgress('thought', data.thought);
      updateProgress('voice', data.voice);
      updateProgress('appearance', data.appearance);
      document.getElementById('soul-overall').textContent = Math.round(data.overall * 100) + '%';
      document.getElementById('soul-overall-bar').style.width = (data.overall * 100) + '%';
      drawSoulOrb(data.overall);
      
      const statusEl = document.getElementById('avatar-status');
      if (data.overall < 0.2) statusEl.textContent = '数据采集中...';
      else if (data.overall < 0.5) statusEl.textContent = '轮廓渐显';
      else if (data.overall < 0.8) statusEl.textContent = '形象清晰化中';
      else statusEl.textContent = '数字灵魂已成型';
    }
  } catch (e) {
    console.log('[Soul] 完成度加载失败:', e);
  }
}

function updateProgress(type, value) {
  const pct = Math.round(value * 100);
  document.getElementById(`${type}-pct`).textContent = pct + '%';
  document.getElementById(`${type}-bar`).style.width = pct + '%';
}

// ========== 摄像头 & 麦克风 ==========
async function startCamera() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
    const video = document.getElementById('camera-feed');
    video.srcObject = stream;
    video.classList.remove('hidden');
    document.getElementById('cam-btn').classList.add('hidden');
    document.getElementById('cam-stop-btn').classList.remove('hidden');
    isCamOn = true;
    
    // 每5秒自动截图上传
    window._camInterval = setInterval(() => captureAndUpload(video), 5000);
  } catch (err) {
    alert('无法访问摄像头: ' + err.message);
  }
}

function stopCamera() {
  const video = document.getElementById('camera-feed');
  if (video.srcObject) {
    video.srcObject.getTracks().forEach(t => t.stop());
  }
  video.classList.add('hidden');
  document.getElementById('cam-btn').classList.remove('hidden');
  document.getElementById('cam-stop-btn').classList.add('hidden');
  isCamOn = false;
  if (window._camInterval) clearInterval(window._camInterval);
}

function captureAndUpload(video) {
  const canvas = document.createElement('canvas');
  canvas.width = video.videoWidth || 640;
  canvas.height = video.videoHeight || 480;
  const ctx = canvas.getContext('2d');
  ctx.drawImage(video, 0, 0);
  canvas.toBlob(async (blob) => {
    if (!blob) return;
    const form = new FormData();
    form.append('file', blob, `capture_${Date.now()}.jpg`);
    try {
      await fetch(`${API_BASE}/soul/appearance/${USER_ID}/photo`, { method: 'POST', body: form });
      console.log('[Soul] 形象照片已上传');
    } catch (e) {
      console.error('[Soul] 照片上传失败:', e);
    }
  }, 'image/jpeg', 0.8);
}

async function toggleMic() {
  const btn = document.getElementById('mic-btn');
  const indicator = document.getElementById('recording-indicator');
  
  if (!isMicOn) {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaRecorder = new MediaRecorder(stream);
      recordedChunks = [];
      mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) recordedChunks.push(e.data);
      };
      mediaRecorder.onstop = async () => {
        const blob = new Blob(recordedChunks, { type: 'audio/webm' });
        const form = new FormData();
        form.append('file', blob, `voice_${Date.now()}.webm`);
        try {
          await fetch(`${API_BASE}/soul/voice/${USER_ID}/sample`, { method: 'POST', body: form });
          console.log('[Soul] 语音样本已上传');
          loadSoulCompleteness();
        } catch (e) {
          console.error('[Soul] 语音上传失败:', e);
        }
      };
      mediaRecorder.start();
      isMicOn = true;
      btn.classList.add('bg-red-100', 'text-red-600');
      indicator.classList.remove('hidden');
      indicator.classList.add('flex');
      
      // 10秒后自动停止
      setTimeout(() => { if (isMicOn) toggleMic(); }, 10000);
    } catch (err) {
      alert('无法访问麦克风: ' + err.message);
    }
  } else {
    mediaRecorder.stop();
    mediaRecorder.stream.getTracks().forEach(t => t.stop());
    isMicOn = false;
    btn.classList.remove('bg-red-100', 'text-red-600');
    indicator.classList.add('hidden');
    indicator.classList.remove('flex');
  }
}

// ========== 灵魂预览室 ==========
function toggleSoulPreview() {
  const el = document.getElementById('soul-preview');
  if (el.classList.contains('hidden')) {
    el.classList.remove('hidden');
    loadSoulProfile();
  } else {
    el.classList.add('hidden');
  }
}

async function loadSoulProfile() {
  try {
    const res = await fetch(`${API_BASE}/soul/profile/${USER_ID}`);
    const data = await res.json();
    if (data.decision_style !== undefined) {
      document.getElementById('preview-decision').textContent = data.decision_style < 0.4 ? '保守' : data.decision_style > 0.6 ? '冒险' : '平衡';
      document.getElementById('preview-language').textContent = data.language_style < 0.4 ? '随意' : data.language_style > 0.6 ? '正式' : '平衡';
    }
  } catch (e) {
    console.log('[Soul] 画像加载失败:', e);
  }
}

function updateDecisionLabel(val) {
  const labels = ['保守', '偏保守', '平衡', '偏冒险', '冒险'];
  const idx = Math.min(4, Math.floor(val * 4));
  document.getElementById('preview-decision').textContent = labels[idx];
}

function updateLanguageLabel(val) {
  const labels = ['随意', '偏随意', '平衡', '偏正式', '正式'];
  const idx = Math.min(4, Math.floor(val * 4));
  document.getElementById('preview-language').textContent = labels[idx];
}

function testSoulChat() {
  alert('测试对话功能将在 Phase 2 集成风格微调引擎后可用。');
}

async function saveWill() {
  alert('遗嘱设置已保存（本地占位）。');
}

// ========== 视觉反馈 ==========
function updateAvatarEmotion(emotion) {
  const overlay = document.getElementById('avatar-overlay');
  const map = {
    'happy': '😊', 'sad': '😢', 'angry': '😠', 'surprised': '😲',
    'listening': '👤', 'thinking': '🤔', 'calm': '✨',
  };
  overlay.innerHTML = `<span class="text-6xl">${map[emotion] || '👤'}</span>`;
}

function drawSoulOrb(completeness) {
  const canvas = document.getElementById('avatar-canvas');
  const ctx = canvas.getContext('2d');
  const w = canvas.width;
  const h = canvas.height;
  ctx.clearRect(0, 0, w, h);
  
  const centerX = w / 2;
  const centerY = h / 2;
  const baseRadius = 40 + completeness * 30;
  const time = Date.now() * 0.001;
  
  // 外发光
  const glow = ctx.createRadialGradient(centerX, centerY, baseRadius * 0.5, centerX, centerY, baseRadius * 1.5);
  glow.addColorStop(0, `rgba(124, 58, 237, ${0.3 + completeness * 0.4})`);
  glow.addColorStop(1, 'rgba(124, 58, 237, 0)');
  ctx.fillStyle = glow;
  ctx.fillRect(0, 0, w, h);
  
  // 核心球体
  ctx.beginPath();
  ctx.arc(centerX, centerY, baseRadius, 0, Math.PI * 2);
  const grad = ctx.createRadialGradient(centerX - 10, centerY - 10, 5, centerX, centerY, baseRadius);
  grad.addColorStop(0, '#c4b5fd');
  grad.addColorStop(1, `rgba(109, 40, 217, ${0.6 + completeness * 0.4})`);
  ctx.fillStyle = grad;
  ctx.fill();
  
  // 粒子效果
  if (completeness > 0.1) {
    const particles = Math.floor(completeness * 20);
    for (let i = 0; i < particles; i++) {
      const angle = (i / particles) * Math.PI * 2 + time * 0.5;
      const dist = baseRadius + 10 + Math.sin(time * 2 + i) * 5;
      const px = centerX + Math.cos(angle) * dist;
      const py = centerY + Math.sin(angle) * dist;
      ctx.beginPath();
      ctx.arc(px, py, 2, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(167, 139, 250, ${0.5 + Math.sin(time * 3 + i) * 0.3})`;
      ctx.fill();
    }
  }
  
  requestAnimationFrame(() => drawSoulOrb(completeness));
}

// ========== 工具函数 ==========
function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

function formatMessage(text) {
  if (!text) return '';
  // 简单 Markdown 渲染
  let html = escapeHtml(text);
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');
  html = html.replace(/`([^`]+)`/g, '<code class="bg-slate-100 px-1 rounded text-xs">$1</code>');
  html = html.replace(/\n/g, '<br>');
  return html;
}

// 自适应 textarea
document.getElementById('chat-input').addEventListener('input', function() {
  this.style.height = 'auto';
  this.style.height = Math.min(120, this.scrollHeight) + 'px';
});
