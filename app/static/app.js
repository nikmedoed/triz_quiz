// Minimal Chart.js render for MCQ reveal (no custom colors per requirements)
window.renderMcq = function() {
  const ctx = document.getElementById('mcqChart');
  if (!ctx || !window.__mcq) return;
  const data = window.__mcq;
  const container = ctx.parentNode;
  // Ensure the canvas matches the container dimensions
  ctx.width = container.clientWidth;
  ctx.height = container.clientHeight;
  const labels = data.labels.map(l => {
    const words = l.split(' ');
    const lines = [];
    let current = words.shift();
    words.forEach(w => {
      if ((current + ' ' + w).length > 20) { lines.push(current); current = w; }
      else { current += ' ' + w; }
    });
    lines.push(current);
    return lines;
  });
  const styles = getComputedStyle(document.documentElement);
  const primary = styles.getPropertyValue('--color-primary-500').trim() || '#e5231b';
  const neutral = styles.getPropertyValue('--color-slate-400').trim() || '#8c929c';
  const colors = labels.map((_, i) => i === data.correct ? primary : neutral);
    const chart = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: labels,
        datasets: [{ label: 'Votes (%)', data: data.percents, backgroundColor: colors, borderColor: colors }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: ctx => `${data.counts[ctx.dataIndex]} (${data.percents[ctx.dataIndex]}%)`
            }
        }
      },
      scales: {
        x: {
          ticks: {
            color: ctx => ctx.index === data.correct ? primary : neutral,
          }
        },
        y: {
          ticks: { callback: value => value + '%' },
          suggestedMax: 100
        }
      },
      animation: { onComplete: () => { drawOverlays(); } }
    },
  });
  function drawOverlays(){
    container.querySelectorAll('.mcq-avatar-col, .mcq-count').forEach(e => e.remove());
    const meta = chart.getDatasetMeta(0);
    const xScale = chart.scales.x;
    const minTop = chart.chartArea.top + 15;
    const avatarOffset = 55;
    meta.data.forEach((bar, i) => {
      const label = document.createElement('div');
      label.className = 'mcq-count';
      label.textContent = `${data.counts[i]} (${data.percents[i]}%)`;
      label.style.left = bar.x + 'px';
      label.style.top = Math.max(bar.y - 24, minTop) + 'px';
      label.style.color = i === data.correct ? primary : neutral;
      container.appendChild(label);

      const div = document.createElement('div');
      div.className = 'mcq-avatar-col';
      div.style.left = bar.x + 'px';
      div.style.bottom = (container.clientHeight - xScale.bottom + avatarOffset) + 'px';
      div.style.width = bar.width + 'px';
      div.style.maxHeight = Math.max(bar.height - avatarOffset, 0) + 'px';
      (data.avatars[i] || []).forEach(id => {
        const img = document.createElement('img');
        img.className = 'avatar small';
        img.src = `/avatars/${id}.png`;
        if (data.names) img.title = data.names[id] || '';
        div.appendChild(img);
      });
      container.appendChild(div);
    });
  }
};

// Auto-scrolling loop for a vertical container
(() => {
  /** @param {HTMLElement} el */
  function setupAutoLoop(el) {
    const prefersReduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (!el || prefersReduced) return;

    const speed = Math.max(1, parseFloat(el.getAttribute('data-speed') || '28'));
    const firstChild = el.firstElementChild;
    if (!firstChild) return;
    const originalHeight = el.scrollHeight;
    if (originalHeight <= el.clientHeight + 1) return;
    if (!el.querySelector('[data-clone="1"]')) {
      const clone = firstChild.cloneNode(true);
      const head = clone.querySelector('thead');
      if (head) head.remove();
      clone.setAttribute('data-clone', '1');
      el.appendChild(clone);
    }

    let raf = 0;
    let last = performance.now();
    let paused = false;

    const setPaused = (v) => { paused = v; };
    el.addEventListener('mouseenter', () => setPaused(true));
    el.addEventListener('mouseleave', () => setPaused(false));
    el.addEventListener('focusin', () => setPaused(true));
    el.addEventListener('focusout', () => setPaused(false));

    document.addEventListener('visibilitychange', () => {
      paused = document.hidden;
    });

    const step = (now) => {
      const dt = (now - last) / 1000;
      last = now;
      if (!paused) {
        el.scrollTop += speed * dt;
        if (el.scrollTop >= originalHeight) {
          el.scrollTop = el.scrollTop - originalHeight;
        }
      }
      raf = requestAnimationFrame(step);
    };

    raf = requestAnimationFrame((t) => { last = t; step(t); });
    el.__destroyAutoLoop = () => cancelAnimationFrame(raf);
  }

  const targets = document.querySelectorAll('[data-auto-scroll="leaderboard"]');
  targets.forEach(setupAutoLoop);
})();
