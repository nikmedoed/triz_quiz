// Minimal Chart.js render for MCQ reveal (no custom colors per requirements)
window.renderMcq = function() {
  const ctx = document.getElementById('mcqChart');
  if (!ctx || !window.__mcq) return;
  const data = window.__mcq;
  const container = ctx.parentNode;
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
      div.style.top = (xScale.bottom + 4) + 'px';
      div.style.width = bar.width + 'px';
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
