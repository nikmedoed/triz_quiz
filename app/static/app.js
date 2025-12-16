const MAX_LABEL_LENGTH = 40;
const MIN_LABEL_LENGTH = 12;
const LABEL_CHAR_ESTIMATE = 7.5;
const LABEL_SIDE_PADDING = 12;
const LABEL_FONT_SIZE = 16;
const AVATAR_BOTTOM_GAP = 10;

function wrapLabel(text, maxLen = MAX_LABEL_LENGTH) {
    const limit = Math.max(
        MIN_LABEL_LENGTH,
        Math.min(MAX_LABEL_LENGTH, Math.floor(maxLen || MAX_LABEL_LENGTH))
    );
    const words = text.split(' ');
    const lines = [];
    let current = words.shift() || '';
    words.forEach(w => {
        if ((current + ' ' + w).length > limit) {
            lines.push(current);
            current = w;
        } else {
            current += ' ' + w;
        }
    });
    lines.push(current);
    return lines;
}

window.initTimer = function (id, sinceIso, durationMs) {
    const el = id ? document.getElementById(id) : null;
    if (!el || !sinceIso || !durationMs) return;
    const start = new Date(sinceIso + 'Z').getTime();

    function tick() {
        let left = durationMs - (Date.now() - start);
        if (left < 0) left = 0;
        const m = String(Math.floor(left / 60000)).padStart(2, '0');
        const s = String(Math.floor((left % 60000) / 1000)).padStart(2, '0');
        el.textContent = m + ':' + s;
    }

    tick();
    setInterval(tick, 1000);
};

function renderBarWithAvatars(data, correctSet) {
    const ctx = document.getElementById('mcqChart');
    if (!ctx || !data || !window.Chart) {
        setTimeout(() => renderBarWithAvatars(data, correctSet), 50);
        return;
    }
    const existing = window.Chart.getChart ? window.Chart.getChart(ctx) : null;
    if (existing) {
        existing.destroy();
    }
    const container = ctx.parentNode;
    ctx.width = container.clientWidth;
    ctx.height = container.clientHeight;
    const rawLabels = data.labels || [];
    const estimatedColumnWidth = rawLabels.length
        ? (container.clientWidth / rawLabels.length)
        : container.clientWidth;
    const dynamicMaxLen = Math.min(
        MAX_LABEL_LENGTH,
        Math.max(
            MIN_LABEL_LENGTH,
            Math.floor(Math.max(estimatedColumnWidth - LABEL_SIDE_PADDING * 2, 80) / LABEL_CHAR_ESTIMATE)
        )
    );
    const labels = rawLabels.map(l => wrapLabel(l, dynamicMaxLen));
    const styles = getComputedStyle(document.documentElement);
    const primary = styles.getPropertyValue('--color-primary-500').trim() || '#e5231b';
    const neutral = styles.getPropertyValue('--color-slate-400').trim() || '#8c929c';
    const colors = labels.map((_, i) => correctSet.has(i) ? primary : neutral);
    let chart;
    try {
        chart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [{label: 'Votes (%)', data: data.percents, backgroundColor: colors, borderColor: colors}]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {display: false},
                    tooltip: {
                        callbacks: {
                            label: ctx => `${data.counts[ctx.dataIndex]} (${data.percents[ctx.dataIndex]}%)`
                        }
                    }
                },
                scales: {
                    x: {
                        ticks: {
                            color: ctx => correctSet.has(ctx.index) ? primary : neutral,
                            font: {size: LABEL_FONT_SIZE},
                        }
                    },
                    y: {
                        ticks: {callback: value => value + '%'},
                        suggestedMax: 100
                    }
                }
            },
        });
    } catch (e) {
        console.error('Chart init failed', e);
        return;
    }

    // Run overlays after initial paint
    setTimeout(drawOverlays, 0);

    let drawLock = false;

    function drawOverlays(skipRetry) {
        if (!chart) return;
        if (drawLock) return;
        drawLock = true;
        container.querySelectorAll('.mcq-avatar-col, .mcq-count').forEach(e => e.remove());
        const meta = chart.getDatasetMeta(0);
        const area = chart.chartArea || {
            top: 0,
            bottom: container.clientHeight || 0,
            left: 0,
        };
        if (!meta || !meta.data || !meta.data.length) {
            if (!skipRetry) setTimeout(() => drawOverlays(true), 30);
            drawLock = false;
            return;
        }
        const minTop = area.top + 15;
        const fallbackWidth = container.clientWidth / Math.max(labels.length, 1);
        const basePositions = meta.data
            .map(bar => typeof bar.base === 'number' ? bar.base : area.bottom);
        const baseline = basePositions.length ? Math.max(...basePositions) : area.bottom;
        const safeBottom = area.bottom - AVATAR_BOTTOM_GAP;
        const desiredTop = baseline + AVATAR_BOTTOM_GAP;
        const avatarMaxHeight = Math.max(safeBottom - area.top, 0);
        meta.data.forEach((bar, i) => {
            const barWidth = bar && typeof bar.width === 'number' ? bar.width : fallbackWidth * 0.7;
            const barX = bar && typeof bar.x === 'number'
                ? bar.x
                : ((i + 0.5) * fallbackWidth);
            const barY = bar && typeof bar.y === 'number' ? bar.y : area.bottom;
            const label = document.createElement('div');
            label.className = 'mcq-count';
            label.textContent = `${data.counts[i]} (${data.percents[i]}%)`;
            label.style.left = barX + 'px';
            label.style.top = Math.max(barY - 24, minTop) + 'px';
            label.style.color = correctSet.has(i) ? primary : neutral;
            container.appendChild(label);

            const div = document.createElement('div');
            div.className = 'mcq-avatar-col';
            div.style.left = barX + 'px';
            div.style.width = barWidth + 'px';
            div.style.maxHeight = avatarMaxHeight + 'px';
            (data.avatars?.[i] || []).filter(Boolean).forEach(id => {
                const img = document.createElement('img');
                img.className = 'avatar small';
                img.src = `/avatars/${id}.png`;
                const key = String(id);
                if (data.names) img.title = data.names[key] || '';
                div.appendChild(img);
            });
            container.appendChild(div);
            const actualHeight = div.offsetHeight || 0;
            const fallbackTop = safeBottom - actualHeight;
            const finalTop = Math.max(chart.chartArea.top, Math.min(desiredTop, fallbackTop));
            div.style.top = finalTop + 'px';
        });
        drawLock = false;
    }
}

// Minimal Chart.js renders for reveal phases with avatar stacks
window.renderMcq = function () {
    const data = window.__mcq;
    if (!data) return;
    renderBarWithAvatars(data, new Set([data.correct]));
};

window.renderMulti = function () {
    const data = window.__mcq;
    if (!data) return;
    renderBarWithAvatars(data, new Set(data.correct || []));
};

window.renderSequence = function () {
    const data = window.__sequence || window.__mcq;
    if (!data) return;
    renderBarWithAvatars(data, new Set([0]));
};
