/**
 * Exhibition Lead Sniper — Frontend Logic
 * Handles drag-and-drop, API calls, state management, and UI rendering.
 */

/* ── State ───────────────────────────────────────────────────────────────── */
const state = {
  currentPanel: 'upload',
  imageBase64: null,
  imageFilename: null,
  leadId: null,
  leadData: null,
  customsData: null,
  emailData: null,
  deckFilename: null,
  deckDownloadUrl: null,
};

/* ── Init ────────────────────────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  initDropzone();
  checkBackendStatus();
  checkCustomsStatus();
  loadHistory();
});

/* ── Panel Navigation ────────────────────────────────────────────────────── */
const panelTitles = {
  upload: 'Upload Namecard',
  analysis: 'AI Analysis',
  emails: 'Generated Emails',
  pitchdeck: 'Pitch Deck Generator',
  history: 'Lead History',
};

function switchPanel(name) {
  state.currentPanel = name;

  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  const panel = document.getElementById('panel-' + name);
  if (panel) panel.classList.add('active');

  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  const navItem = document.querySelector(`.nav-item[data-panel="${name}"]`);
  if (navItem) navItem.classList.add('active');

  document.getElementById('topbarTitle').textContent = panelTitles[name] || name;

  if (name === 'history') loadHistory();
}

function markStepCompleted(name) {
  const navItem = document.querySelector(`.nav-item[data-panel="${name}"]`);
  if (navItem) navItem.classList.add('completed');
}

/* ── Toast Notifications ─────────────────────────────────────────────────── */
function showToast(message, type = 'info', duration = 4000) {
  const container = document.getElementById('toastContainer');
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.textContent = message;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateX(40px)';
    toast.style.transition = 'all 0.3s ease';
    setTimeout(() => toast.remove(), 300);
  }, duration);
}

/* ── Loading Overlay ─────────────────────────────────────────────────────── */
function showLoading(text = 'Processing…') {
  document.getElementById('loadingText').textContent = text;
  document.getElementById('loadingOverlay').style.display = 'flex';
}

function hideLoading() {
  document.getElementById('loadingOverlay').style.display = 'none';
}

/* ── Drag & Drop ─────────────────────────────────────────────────────────── */
function initDropzone() {
  const dropzone = document.getElementById('dropzone');
  const fileInput = document.getElementById('fileInput');

  ['dragenter', 'dragover'].forEach(evt => {
    dropzone.addEventListener(evt, e => {
      e.preventDefault();
      e.stopPropagation();
      dropzone.classList.add('dragover');
    });
  });

  ['dragleave', 'drop'].forEach(evt => {
    dropzone.addEventListener(evt, e => {
      e.preventDefault();
      e.stopPropagation();
      dropzone.classList.remove('dragover');
    });
  });

  dropzone.addEventListener('drop', e => {
    const files = e.dataTransfer.files;
    if (files.length > 0) handleFile(files[0]);
  });

  fileInput.addEventListener('change', e => {
    if (e.target.files.length > 0) handleFile(e.target.files[0]);
  });
}

function handleFile(file) {
  const allowed = ['image/jpeg', 'image/png', 'image/webp'];
  if (!allowed.includes(file.type)) {
    showToast('Please upload a JPG, PNG, or WebP image.', 'error');
    return;
  }
  if (file.size > 16 * 1024 * 1024) {
    showToast('File too large. Maximum 16 MB.', 'error');
    return;
  }

  const reader = new FileReader();
  reader.onload = e => {
    const dataUrl = e.target.result;
    state.imageBase64 = dataUrl.split(',')[1];
    state.imageFilename = file.name;

    document.getElementById('previewImg').src = dataUrl;
    document.getElementById('previewArea').style.display = 'block';
    document.getElementById('dropzone').style.display = 'none';
  };
  reader.readAsDataURL(file);
}

function clearUpload() {
  state.imageBase64 = null;
  state.imageFilename = null;
  document.getElementById('previewArea').style.display = 'none';
  document.getElementById('dropzone').style.display = 'block';
  document.getElementById('fileInput').value = '';
}

/* ── Process Namecard ────────────────────────────────────────────────────── */
async function processCard() {
  if (!state.imageBase64) {
    showToast('No image to process.', 'error');
    return;
  }

  const btn = document.getElementById('btnProcess');
  btn.disabled = true;

  const progressBar = document.getElementById('uploadProgress');
  const progressFill = document.getElementById('uploadProgressFill');
  progressBar.style.display = 'block';
  progressFill.style.width = '20%';

  showLoading('Sending to AI for OCR + enrichment…');

  try {
    progressFill.style.width = '50%';

    const resp = await fetch('/api/upload-namecard', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        image_base64: state.imageBase64,
        filename: state.imageFilename,
      }),
    });

    progressFill.style.width = '80%';

    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ error: 'Unknown error' }));
      throw new Error(err.error || err.detail || `HTTP ${resp.status}`);
    }

    const result = await resp.json();
    progressFill.style.width = '100%';

    state.leadId = result.lead_id;
    state.leadData = result.data;
    state.customsData = result.customs;

    renderAnalysis(result);
    markStepCompleted('upload');
    showToast('Namecard processed successfully!', 'success');

    setTimeout(() => switchPanel('analysis'), 600);
  } catch (e) {
    showToast(`Processing failed: ${e.message}`, 'error');
  } finally {
    hideLoading();
    btn.disabled = false;
    setTimeout(() => {
      progressBar.style.display = 'none';
      progressFill.style.width = '0%';
    }, 1000);
  }
}

/* ── Render Analysis Results ─────────────────────────────────────────────── */
function renderAnalysis(result) {
  document.getElementById('analysisEmpty').style.display = 'none';
  document.getElementById('analysisResult').style.display = 'block';

  const data = result.data?.data || result.data || {};
  const grid = document.getElementById('contactGrid');

  const fields = [
    { label: 'Name', key: 'name', icon: '👤' },
    { label: 'Company', key: 'company', icon: '🏢' },
    { label: 'Title', key: 'title', icon: '💼' },
    { label: 'Email', key: 'email', icon: '📧' },
    { label: 'Phone', key: 'phone', icon: '📱' },
    { label: 'LinkedIn', key: 'linkedin', icon: '🔗' },
    { label: 'Website', key: 'website', icon: '🌐' },
    { label: 'Address', key: 'address', icon: '📍' },
  ];

  grid.innerHTML = fields
    .filter(f => data[f.key])
    .map(f => `
      <div class="info-item">
        <div class="label">${f.icon} ${f.label}</div>
        <div class="value">${escHtml(data[f.key])}</div>
      </div>
    `)
    .join('');

  // If no fields extracted, show raw data
  if (grid.innerHTML === '') {
    grid.innerHTML = `
      <div class="info-item" style="grid-column: 1/-1;">
        <div class="label">📄 Raw Response</div>
        <div class="value" style="font-size:12px; white-space:pre-wrap; word-break:break-all;">${escHtml(JSON.stringify(data, null, 2))}</div>
      </div>`;
  }

  // Pre-fill pitch deck company
  const company = data.company || '';
  if (company) {
    document.getElementById('deckCompany').value = company;
  }

  // Customs data
  renderCustoms(result.customs);
}

function renderCustoms(customs) {
  const card = document.getElementById('customsCard');
  if (!customs) {
    card.style.display = 'none';
    return;
  }
  card.style.display = 'block';

  const badge = document.getElementById('customsBadge');
  const tableWrap = document.getElementById('customsTableWrap');

  if (customs.matched) {
    badge.innerHTML = `<span class="customs-badge match">✅ ${customs.records.length} matching record(s) found (score: ${customs.best_score})</span>`;

    if (customs.records.length > 0) {
      const cols = Object.keys(customs.records[0]).filter(k => !k.startsWith('_'));
      let html = '<table class="customs-table"><thead><tr>';
      cols.forEach(c => { html += `<th>${escHtml(c)}</th>`; });
      html += '</tr></thead><tbody>';
      customs.records.forEach(r => {
        html += '<tr>';
        cols.forEach(c => { html += `<td>${escHtml(r[c] || '')}</td>`; });
        html += '</tr>';
      });
      html += '</tbody></table>';
      tableWrap.innerHTML = html;
    }
  } else {
    badge.innerHTML = `<span class="customs-badge no-match">⚠️ No matching customs records for "${escHtml(customs.query)}"</span>`;
    tableWrap.innerHTML = '';
  }
}

/* ── Generate Emails ─────────────────────────────────────────────────────── */
async function generateEmails() {
  if (!state.leadData) {
    showToast('No lead data available. Process a namecard first.', 'error');
    return;
  }

  showLoading('Generating personalized email sequence…');

  try {
    const data = state.leadData?.data || state.leadData || {};
    const payload = {
      lead_id: state.leadId,
      contact: data,
      customs: state.customsData,
    };

    const resp = await fetch('/api/generate-emails', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ error: 'Unknown error' }));
      throw new Error(err.error || err.detail || `HTTP ${resp.status}`);
    }

    const result = await resp.json();
    state.emailData = result.data;
    renderEmails(result.data);
    markStepCompleted('analysis');
    showToast('Email sequence generated!', 'success');
    setTimeout(() => switchPanel('emails'), 400);
  } catch (e) {
    showToast(`Email generation failed: ${e.message}`, 'error');
  } finally {
    hideLoading();
  }
}

/* ── Render Emails ───────────────────────────────────────────────────────── */
function renderEmails(emailResult) {
  document.getElementById('emailsEmpty').style.display = 'none';
  document.getElementById('emailsResult').style.display = 'block';

  const left = document.getElementById('emailsLeft');
  const data = state.leadData?.data || state.leadData || {};
  const targetName = data.name || data.company || 'Lead';

  document.getElementById('outreachTarget').textContent = `Target: ${targetName}`;

  // Try to extract email array from various response shapes
  let emails = [];
  if (Array.isArray(emailResult)) {
    emails = emailResult;
  } else if (emailResult?.emails && Array.isArray(emailResult.emails)) {
    emails = emailResult.emails;
  } else if (emailResult?.data?.emails) {
    emails = emailResult.data.emails;
  } else if (emailResult?.email_1 || emailResult?.email1) {
    // Key-based format
    for (let i = 1; i <= 5; i++) {
      const e = emailResult[`email_${i}`] || emailResult[`email${i}`];
      if (e) emails.push(e);
    }
  } else {
    // Fallback: treat entire response as single email
    emails = [{ subject: 'Generated Email', body: JSON.stringify(emailResult, null, 2) }];
  }

  const dotColors = ['#8B9EA4', '#B5C4B1', '#D4A5A5'];
  const labels = ['Initial Outreach', 'Follow-up', 'Final Touch'];

  left.innerHTML = emails.slice(0, 3).map((email, i) => {
    const subject = email.subject || email.title || `Email ${i + 1}`;
    const body = email.body || email.content || email.text || '';

    return `
      <div class="email-card">
        <div class="email-num">
          <span class="dot" style="background:${dotColors[i % 3]}"></span>
          Email ${i + 1} — ${labels[i] || `Step ${i + 1}`}
        </div>
        <div class="email-subject">${escHtml(subject)}</div>
        <textarea id="emailBody${i}" spellcheck="false">${escHtml(body)}</textarea>
      </div>`;
  }).join('');

  // Summary
  const summary = document.getElementById('outreachSummary');
  summary.innerHTML = `
    <div style="margin-top: 12px; font-size: 13px; color: #666;">
      <p>✅ ${emails.length} email(s) generated</p>
      <p style="margin-top:4px;">📝 Edit the emails in the left panel, then continue to create a pitch deck.</p>
    </div>`;

  markStepCompleted('emails');
}

/* ── Generate Pitch Deck ─────────────────────────────────────────────────── */
async function generateDeck() {
  const company = document.getElementById('deckCompany').value.trim();
  if (!company) {
    showToast('Please enter a target company name.', 'error');
    return;
  }

  let products = [];
  const productsStr = document.getElementById('deckProducts').value.trim();
  if (productsStr) {
    try {
      products = JSON.parse(productsStr);
    } catch {
      showToast('Invalid products JSON. Please check the format.', 'error');
      return;
    }
  }

  let contactInfo = {};
  const contactStr = document.getElementById('deckContact').value.trim();
  if (contactStr) {
    try {
      contactInfo = JSON.parse(contactStr);
    } catch {
      showToast('Invalid contact info JSON.', 'error');
      return;
    }
  }

  const btn = document.getElementById('btnDeck');
  btn.disabled = true;
  showLoading('Generating Morandi-themed pitch deck…');

  try {
    const resp = await fetch('/api/generate-pitch-deck', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        company,
        products,
        contact_info: contactInfo,
        lead_id: state.leadId,
      }),
    });

    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ error: 'Unknown error' }));
      throw new Error(err.error || `HTTP ${resp.status}`);
    }

    const result = await resp.json();
    state.deckFilename = result.filename;
    state.deckDownloadUrl = `/api/download/${encodeURIComponent(result.filename)}`;

    document.getElementById('deckEmpty').style.display = 'none';
    document.getElementById('deckResult').style.display = 'block';
    document.getElementById('deckFilename').textContent = result.filename;
    document.getElementById('deckMeta').textContent = `${result.pages} pages • Morandi theme • Created for ${result.company}`;

    markStepCompleted('pitchdeck');
    showToast('Pitch deck created successfully!', 'success');
  } catch (e) {
    showToast(`Pitch deck failed: ${e.message}`, 'error');
  } finally {
    hideLoading();
    btn.disabled = false;
  }
}

function downloadDeck() {
  if (state.deckDownloadUrl) {
    window.open(state.deckDownloadUrl, '_blank');
  }
}

/* ── Status Checks ───────────────────────────────────────────────────────── */
async function checkBackendStatus() {
  const dot = document.getElementById('statusBackend');
  const text = document.getElementById('statusBackendText');
  try {
    const resp = await fetch('/api/backend-status');
    const data = await resp.json();
    if (data.online) {
      dot.className = 'status-dot green';
      text.textContent = 'Backend online';
    } else {
      dot.className = 'status-dot red';
      text.textContent = 'Backend offline';
    }
  } catch {
    dot.className = 'status-dot red';
    text.textContent = 'Backend unreachable';
  }
}

async function checkCustomsStatus() {
  const dot = document.getElementById('statusCustoms');
  const text = document.getElementById('statusCustomsText');
  try {
    const resp = await fetch('/api/customs-status');
    const data = await resp.json();
    if (data.loaded) {
      dot.className = 'status-dot green';
      text.textContent = data.message.replace('✅ ', '');
    } else {
      dot.className = 'status-dot yellow';
      text.textContent = data.message.replace('⚠️ ', '');
    }
  } catch {
    dot.className = 'status-dot red';
    text.textContent = 'Status check failed';
  }
}

/* ── Lead History ────────────────────────────────────────────────────────── */
async function loadHistory() {
  try {
    const resp = await fetch('/api/leads');
    const leads = await resp.json();
    const list = document.getElementById('historyList');
    const count = document.getElementById('leadCount');

    count.textContent = `${leads.length} lead${leads.length !== 1 ? 's' : ''}`;

    if (leads.length === 0) {
      list.innerHTML = `
        <div class="empty-state">
          <div class="empty-icon">📭</div>
          <p>No leads captured yet.</p>
        </div>`;
      return;
    }

    list.innerHTML = leads.map(lead => {
      const initials = (lead.name || '?').split(' ').map(w => w[0]).join('').toUpperCase().slice(0, 2);
      const timeAgo = formatTimeAgo(lead.created_at);
      return `
        <div class="lead-row" onclick="viewLead(${lead.id})">
          <div class="lead-avatar">${initials}</div>
          <div class="lead-info">
            <div class="lead-name">${escHtml(lead.name || 'Unknown')}</div>
            <div class="lead-company">${escHtml(lead.company || '—')} ${lead.customs_match ? '🛃' : ''}</div>
          </div>
          <div class="lead-time">${timeAgo}</div>
        </div>`;
    }).join('');
  } catch (e) {
    console.error('Failed to load history:', e);
  }
}

async function viewLead(leadId) {
  try {
    const resp = await fetch(`/api/leads/${leadId}`);
    const data = await resp.json();

    state.leadId = leadId;
    state.leadData = data.lead.raw_enrichment ? JSON.parse(data.lead.raw_enrichment) : data.lead;

    if (data.lead.customs_match) {
      state.customsData = JSON.parse(data.lead.customs_match);
    }

    renderAnalysis({ data: state.leadData, customs: state.customsData });
    switchPanel('analysis');
  } catch (e) {
    showToast('Failed to load lead details.', 'error');
  }
}

/* ── Utilities ───────────────────────────────────────────────────────────── */
function escHtml(str) {
  if (typeof str !== 'string') return '';
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

function formatTimeAgo(dateStr) {
  if (!dateStr) return '';
  const date = new Date(dateStr + (dateStr.includes('Z') ? '' : 'Z'));
  const diff = (Date.now() - date.getTime()) / 1000;
  if (diff < 60) return 'just now';
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}
