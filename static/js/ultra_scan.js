const form = document.getElementById('scan-form');
const formSection = document.getElementById('form-section');
const progressSection = document.getElementById('progress-section');
const resultsSection = document.getElementById('results-section');
const errorSection = document.getElementById('error-section');
const startBtn = document.getElementById('start-btn');
const newScanBtn = document.getElementById('new-scan-btn');
const retryBtn = document.getElementById('retry-btn');

let timerInterval = null;
let startTime = 0;
let recentResults = [];

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
    recentResults = [];
    document.getElementById('live-table-body').innerHTML = '<tr><td colspan="8" class="table-empty">Waiting for sitemaps extraction...</td></tr>';

    try {
        const resp = await fetch('/api/ultra-scan', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({sitemaps, concurrency}),
        });

        if (!resp.ok) {
            const data = await resp.json();
            throw new Error(data.detail || 'Failed to start ultra scan');
        }

        showSection('progress');
        startTimer();

        const reader = resp.body.getReader();
        const decoder = new TextDecoder("utf-8");
        let buffer = '';

        while (true) {
            const { value, done } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop(); // keep last incomplete line in buffer

            for (const line of lines) {
                if (line.trim()) {
                    try {
                        const msg = JSON.parse(line);
                        handleStreamMessage(msg);
                    } catch (err) {
                        console.error('Failed to parse line:', line, err);
                    }
                }
            }
        }

    } catch (err) {
        showError(err.message);
    } finally {
        startBtn.disabled = false;
        startBtn.textContent = 'Start Ultra Scan';
    }
});

newScanBtn.addEventListener('click', () => {
    showSection('form');
    form.reset();
    document.getElementById('concurrency').value = '50';
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
    stopTimer();
}

function startTimer() {
    stopTimer();
    startTime = Date.now();
    timerInterval = setInterval(() => {
        const elapsed = Math.round((Date.now() - startTime) / 1000);
        document.getElementById('stat-elapsed').textContent = elapsed + 's';
    }, 1000);
}

function stopTimer() {
    if (timerInterval) clearInterval(timerInterval);
}

function handleStreamMessage(msg) {
    if (msg.type === 'status') {
        document.getElementById('progress-phase').textContent = msg.message;
    } else if (msg.type === 'init') {
        document.getElementById('progress-phase').textContent = 'Crawling Sitemap URLs...';
        document.getElementById('stat-total').textContent = msg.total.toLocaleString();
    } else if (msg.type === 'result') {
        const item = msg.data;
        
        // Update stats
        document.getElementById('stat-completed').textContent = item.completed.toLocaleString();
        document.getElementById('stat-success').textContent = item.success.toLocaleString();
        document.getElementById('stat-redirects').textContent = item.redirects.toLocaleString();
        document.getElementById('stat-client-errors').textContent = item.client_errors.toLocaleString();
        document.getElementById('stat-server-errors').textContent = item.server_errors.toLocaleString();

        const pct = item.percentage || 0;
        document.getElementById('progress-bar').style.width = pct + '%';
        document.getElementById('progress-text').textContent = Math.round(pct) + '%';

        // Keep last 15 results for live table
        recentResults.unshift(item);
        if (recentResults.length > 15) {
            recentResults.pop();
        }
        updateLiveTable(recentResults);

    } else if (msg.type === 'complete') {
        stopTimer();
        
        document.getElementById('result-total').textContent = msg.total.toLocaleString();
        document.getElementById('result-success').textContent = msg.success.toLocaleString();
        document.getElementById('result-redirects').textContent = msg.redirects.toLocaleString();
        document.getElementById('result-client-errors').textContent = msg.client_errors.toLocaleString();
        document.getElementById('result-server-errors').textContent = msg.server_errors.toLocaleString();
        document.getElementById('result-other').textContent = '0';
        document.getElementById('result-duration').textContent = msg.elapsed + 's';

        const dlBtn = document.getElementById('download-btn');
        dlBtn.href = msg.download_url;

        showSection('results');
    } else if (msg.type === 'error') {
        showError(msg.message);
    }
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
