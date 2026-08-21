const form = document.getElementById('scan-form');
const formSection = document.getElementById('form-section');
const progressSection = document.getElementById('progress-section');
const resultsSection = document.getElementById('results-section');
const errorSection = document.getElementById('error-section');
const startBtn = document.getElementById('start-btn');
const newScanBtn = document.getElementById('new-scan-btn');
const retryBtn = document.getElementById('retry-btn');

let pollInterval = null;
let currentScanId = null;

window.addEventListener('DOMContentLoaded', () => {
    const activeScanId = localStorage.getItem('active_ultra_scan_id');
    if (activeScanId) {
        currentScanId = activeScanId;
        showSection('progress');
        startPolling(activeScanId);
    } else {
        loadRecentScans();
    }

    const loadScanForm = document.getElementById('load-scan-form');
    if (loadScanForm) {
        loadScanForm.addEventListener('submit', (e) => {
            e.preventDefault();
            const scanId = document.getElementById('load-scan-id').value.trim();
            if (!scanId) return;

            loadUltraScanId(scanId);
        });
    }
});

async function loadRecentScans() {
    try {
        const resp = await fetch('/api/ultra-scan/recent');
        const list = await resp.json();
        const container = document.getElementById('recent-ultra-list');
        if (!container) return;
        
        if (!list || !list.length) {
            container.innerHTML = '<div style="color: var(--text-muted); font-size: 14px;">No previous Ultra scans found.</div>';
            return;
        }
        
        container.innerHTML = list.map(item => {
            const sitemapsStr = item.sitemaps.join(', ');
            const statusClass = item.status === 'COMPLETED' ? 'st-green' : item.status === 'RUNNING' ? 'st-yellow' : 'st-red';
            return `
                <div style="display: flex; justify-content: space-between; align-items: center; padding: 10px 12px; border: 1px solid var(--border-color); border-radius: 6px; background: var(--bg-color); font-size: 14px;">
                    <div style="display: flex; flex-direction: column; gap: 4px; overflow: hidden; margin-right: 10px; text-align: left;">
                        <a href="#" onclick="loadUltraScanId('${item.scan_id}'); return false;" style="font-weight: bold; color: var(--primary-color); font-family: monospace; text-decoration: none;">${item.scan_id}</a>
                        <span style="color: var(--text-muted); font-size: 12px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: left;" title="${esc(sitemapsStr)}">${esc(sitemapsStr)}</span>
                    </div>
                    <div style="display: flex; align-items: center; gap: 10px; white-space: nowrap;">
                        <span style="font-size: 12px; color: var(--text-muted);">${item.date}</span>
                        <span class="status-badge ${statusClass}" style="padding: 2px 6px; font-size: 11px;">${item.status} (${item.completed}/${item.total})</span>
                    </div>
                </div>
            `;
        }).join('');
    } catch (e) {
        console.error('Failed to load recent ultra scans:', e);
    }
}

window.loadUltraScanId = function(scanId) {
    currentScanId = scanId;
    localStorage.setItem('active_ultra_scan_id', scanId);
    showSection('progress');
    startPolling(scanId);
};

form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const sitemapUrl = document.getElementById('sitemap-url').value.trim();
    const additional = document.getElementById('additional-sitemaps').value.trim();
    const concurrency = parseInt(document.getElementById('concurrency').value);

    const sitemaps = [sitemapUrl];
    if (additional) {
        additional.split('\n').forEach(u => {
            const trimmed = u.trim();
            if (trimmed) sitemaps.push(trimmed);
        });
    }

    startBtn.disabled = true;
    startBtn.textContent = 'Starting Ultra Scan...';

    try {
        const resp = await fetch('/api/ultra-scan', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({sitemaps, concurrency}),
        });
        const data = await resp.json();

        if (!resp.ok) {
            throw new Error(data.detail || 'Failed to start ultra scan');
        }

        currentScanId = data.scan_id;
        localStorage.setItem('active_ultra_scan_id', currentScanId);
        showSection('progress');
        startPolling(currentScanId);
    } catch (err) {
        showError(err.message);
    } finally {
        startBtn.disabled = false;
        startBtn.textContent = 'Start Ultra Scan';
    }
});

newScanBtn.addEventListener('click', () => {
    localStorage.removeItem('active_ultra_scan_id');
    showSection('form');
    form.reset();
    document.getElementById('concurrency').value = '50';
    loadRecentScans();
});

retryBtn.addEventListener('click', () => {
    localStorage.removeItem('active_ultra_scan_id');
    showSection('form');
    loadRecentScans();
});

function showSection(name) {
    formSection.classList.toggle('hidden', name !== 'form');
    progressSection.classList.toggle('hidden', name !== 'progress');
    resultsSection.classList.toggle('hidden', name !== 'results');
    errorSection.classList.toggle('hidden', name !== 'error');
}

function showError(msg) {
    document.getElementById('error-message').textContent = msg;
    showSection('error');
    if (pollInterval) clearInterval(pollInterval);
}

function startPolling(scanId) {
    if (pollInterval) clearInterval(pollInterval);
    pollInterval = setInterval(() => pollStatus(scanId), 2000);
    pollStatus(scanId);
}

async function pollStatus(scanId) {
    try {
        const resp = await fetch(`/api/ultra-scan/${scanId}/status`);
        const data = await resp.json();

        if (data.status === 'COMPLETED') {
            clearInterval(pollInterval);
            showResults(data);
        } else if (data.status === 'FAILED') {
            clearInterval(pollInterval);
            showError(data.phase || 'Scan failed');
        } else {
            updateProgress(data);
        }
    } catch (e) {
        // Keep polling on minor network glitches
    }
}

function updateProgress(data) {
    document.getElementById('scan-id-display').textContent = currentScanId;
    const pct = data.percentage || 0;
    document.getElementById('progress-bar').style.width = pct + '%';
    document.getElementById('progress-text').textContent = Math.round(pct) + '%';
    document.getElementById('stat-total').textContent = data.total.toLocaleString();
    document.getElementById('stat-completed').textContent = data.completed.toLocaleString();
    document.getElementById('stat-success').textContent = data.success.toLocaleString();
    document.getElementById('stat-redirects').textContent = data.redirects.toLocaleString();
    document.getElementById('stat-client-errors').textContent = data.client_errors.toLocaleString();
    document.getElementById('stat-server-errors').textContent = data.server_errors.toLocaleString();
    
    let timeText = data.elapsed + 's';
    if (data.eta) {
        timeText += ` (ETA: ${data.eta}s)`;
    }
    document.getElementById('stat-elapsed').textContent = timeText;

    const h2 = document.getElementById('progress-phase');
    h2.textContent = data.phase || 'Crawling URLs...';

    updateLiveTable(data.recent_results || []);
}

function updateLiveTable(results) {
    const tbody = document.getElementById('live-table-body');
    if (!results.length) return;

    tbody.innerHTML = results.map(r => {
        const statusClass = getStatusClass(r.status);
        const score = r.score || 0;
        const scoreClass = score >= 90 ? 'score-excellent' : score >= 75 ? 'score-good' : score >= 60 ? 'score-warn' : score >= 40 ? 'score-poor' : 'score-critical';
        return `<tr>
            <td class="url-cell" title="${esc(r.url)}">${esc(r.url)}</td>
            <td style="text-align: center;"><span class="status-badge ${statusClass}">${esc(String(r.status))}</span></td>
            <td style="text-align: center;"><span class="score-badge ${scoreClass}">${score}</span></td>
            <td style="text-align: center;">${esc(r.time)}</td>
            <td style="text-align: center;">${esc(r.size)}</td>
            <td class="title-cell" title="${esc(r.title)}">${esc(r.title)}</td>
            <td style="text-align: center;">${esc(String(r.words))}</td>
            <td style="text-align: center;" class="${r.issues > 0 ? 'has-issues' : ''}">${r.issues}</td>
        </tr>`;
    }).join('');
}

function getStatusClass(status) {
    const s = String(status);
    if (s.startsWith('2')) return 'st-green';
    if (s.startsWith('3')) return 'st-yellow';
    if (s.startsWith('4')) return 'st-red';
    if (s.startsWith('5')) return 'st-red';
    return 'st-gray';
}

function esc(str) {
    const d = document.createElement('div');
    d.textContent = str;
    return d.innerHTML;
}

function showResults(data) {
    localStorage.removeItem('active_ultra_scan_id');
    document.getElementById('result-scan-id').textContent = currentScanId;
    
    document.getElementById('result-total').textContent = data.total.toLocaleString();
    document.getElementById('result-success').textContent = data.success.toLocaleString();
    document.getElementById('result-redirects').textContent = data.redirects.toLocaleString();
    document.getElementById('result-client-errors').textContent = data.client_errors.toLocaleString();
    document.getElementById('result-server-errors').textContent = data.server_errors.toLocaleString();
    document.getElementById('result-other').textContent = '0';
    document.getElementById('result-duration').textContent = data.elapsed + 's';

    const dlBtn = document.getElementById('download-btn');
    dlBtn.href = `/api/ultra-scan/download/${currentScanId}`;

    showSection('results');
}
