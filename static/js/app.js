const form = document.getElementById('scan-form');
const formSection = document.getElementById('form-section');
const progressSection = document.getElementById('progress-section');
const resultsSection = document.getElementById('results-section');
const errorSection = document.getElementById('error-section');
const startBtn = document.getElementById('start-btn');
const cancelBtn = document.getElementById('cancel-btn');
const newScanBtn = document.getElementById('new-scan-btn');
const retryBtn = document.getElementById('retry-btn');

let pollInterval = null;
let currentScanId = null;

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
    startBtn.textContent = 'Starting...';

    try {
        const resp = await fetch('/api/scan', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({sitemaps, concurrency}),
        });
        const data = await resp.json();

        if (!resp.ok) {
            throw new Error(data.detail || 'Failed to start scan');
        }

        currentScanId = data.scan_id;
        document.getElementById('partial-download-btn').href = `/api/scan/${currentScanId}/download-partial`;
        showSection('progress');
        startPolling();
    } catch (err) {
        showError(err.message);
    } finally {
        startBtn.disabled = false;
        startBtn.textContent = 'Start Scan';
    }
});

cancelBtn.addEventListener('click', async () => {
    if (!currentScanId) return;
    try {
        await fetch(`/api/scan/${currentScanId}/cancel`, {method: 'POST'});
    } catch (e) {}
});

newScanBtn.addEventListener('click', () => {
    showSection('form');
    form.reset();
    document.getElementById('concurrency').value = '25';
});

retryBtn.addEventListener('click', () => {
    showSection('form');
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
}

function startPolling() {
    if (pollInterval) clearInterval(pollInterval);
    pollInterval = setInterval(pollStatus, 2000);
    pollStatus();
}

async function pollStatus() {
    if (!currentScanId) return;

    try {
        const resp = await fetch(`/api/scan/${currentScanId}/status`);
        const data = await resp.json();

        if (data.status === 'COMPLETED') {
            clearInterval(pollInterval);
            showResults(data);
        } else if (data.status === 'FAILED') {
            clearInterval(pollInterval);
            showError(data.error || 'Scan failed');
        } else if (data.status === 'CANCELLED') {
            clearInterval(pollInterval);
            showError('Scan was cancelled');
        } else {
            updateProgress(data);
        }
    } catch (e) {
        // keep polling
    }
}

function updateProgress(data) {
    const pct = data.percentage || 0;
    document.getElementById('progress-bar').style.width = pct + '%';
    document.getElementById('progress-text').textContent = Math.round(pct) + '%';
    document.getElementById('stat-total').textContent = data.total.toLocaleString();
    document.getElementById('stat-completed').textContent = data.completed.toLocaleString();
    document.getElementById('stat-success').textContent = data.success.toLocaleString();
    document.getElementById('stat-redirects').textContent = data.redirects.toLocaleString();
    document.getElementById('stat-client-errors').textContent = data.client_errors.toLocaleString();
    document.getElementById('stat-server-errors').textContent = data.server_errors.toLocaleString();
    document.getElementById('stat-elapsed').textContent = formatTime(data.elapsed);
    document.getElementById('stat-eta').textContent = data.eta ? formatTime(data.eta) + ' (est.)' : 'calculating...';

    const h2 = progressSection.querySelector('h2');
    h2.textContent = data.phase || 'Scanning...';

    const curUrl = document.getElementById('current-url');
    curUrl.textContent = data.current_url || '-';
    curUrl.title = data.current_url || '';

    updateLiveTable(data.recent_results || []);
}

function updateLiveTable(results) {
    const tbody = document.getElementById('live-table-body');
    if (!results.length) return;

    tbody.innerHTML = results.map(r => {
        const statusClass = getStatusClass(r.status);
        return `<tr>
            <td class="url-cell" title="${esc(r.url)}">${esc(r.url)}</td>
            <td class="status-cell ${statusClass}">${esc(String(r.status))}</td>
            <td>${esc(r.time)}</td>
            <td>${esc(r.size)}</td>
            <td class="title-cell" title="${esc(r.title)}">${esc(r.title)}</td>
            <td>${esc(String(r.words))}</td>
            <td class="${r.issues > 0 ? 'has-issues' : ''}">${r.issues}</td>
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
    document.getElementById('result-total').textContent = data.total.toLocaleString();
    document.getElementById('result-success').textContent = data.success.toLocaleString();
    document.getElementById('result-redirects').textContent = data.redirects.toLocaleString();
    document.getElementById('result-client-errors').textContent = data.client_errors.toLocaleString();
    document.getElementById('result-server-errors').textContent = data.server_errors.toLocaleString();
    const other = data.other_errors + data.timeouts + data.dns_errors + data.ssl_errors;
    document.getElementById('result-other').textContent = other.toLocaleString();
    document.getElementById('result-seo').textContent = data.seo_issues.toLocaleString();
    document.getElementById('result-content').textContent = data.content_issues.toLocaleString();
    document.getElementById('result-duration').textContent = formatTime(data.elapsed);

    const dlBtn = document.getElementById('download-btn');
    dlBtn.href = `/api/scan/${currentScanId}/download`;

    document.getElementById('urls-link').href = `/scan/${currentScanId}/urls`;
    document.getElementById('issues-link').href = `/scan/${currentScanId}/issues`;

    loadSummaryCards(currentScanId);
    showSection('results');
}

async function loadSummaryCards(scanId) {
    try {
        const resp = await fetch(`/api/scan/${scanId}/summary`);
        const data = await resp.json();
        renderSummaryCards(data);
    } catch (e) {}
}

function renderSummaryCards(data) {
    const container = document.getElementById('summary-cards');
    if (!container) return;
    let html = '';

    if (data.error_summary && data.error_summary.length) {
        html += '<div class="summary-group"><h3>Error Groups</h3><table class="summary-table">';
        html += '<tr><th>Error</th><th>Count</th><th>Sample URLs</th></tr>';
        data.error_summary.forEach(e => {
            const urls = (e.sample_urls || []).slice(0, 3).map(u => `<span class="sample-url">${esc(u)}</span>`).join('<br>');
            html += `<tr><td>${esc(e.error_type)}</td><td class="count-cell">${e.count}</td><td class="sample-cell">${urls}</td></tr>`;
        });
        html += '</table></div>';
    }

    if (data.seo_summary && data.seo_summary.length) {
        html += '<div class="summary-group"><h3>SEO Issues</h3><table class="summary-table">';
        html += '<tr><th>Issue</th><th>Count</th></tr>';
        data.seo_summary.forEach(s => {
            html += `<tr><td>${esc(s.issue)}</td><td class="count-cell">${s.count}</td></tr>`;
        });
        html += '</table></div>';
    }

    if (data.content_summary && data.content_summary.length) {
        html += '<div class="summary-group"><h3>Content Issues</h3><table class="summary-table">';
        html += '<tr><th>Issue</th><th>Count</th></tr>';
        data.content_summary.forEach(s => {
            html += `<tr><td>${esc(s.issue)}</td><td class="count-cell">${s.count}</td></tr>`;
        });
        html += '</table></div>';
    }

    container.innerHTML = html;
}

function formatTime(seconds) {
    if (!seconds && seconds !== 0) return '--';
    const m = Math.floor(seconds / 60);
    const s = Math.round(seconds % 60);
    if (m === 0) return s + 's';
    return m + 'm ' + s + 's';
}
