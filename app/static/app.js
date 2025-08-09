// Minimal Chart.js render for MCQ reveal (no custom colors per requirements)
window.renderMcq = function() {
  const ctx = document.getElementById('mcqChart');
  if (!ctx || !window.__mcq) return;
  const data = window.__mcq;
  const container = ctx.parentNode;
  const colors = data.labels.map((_, i) => i === data.correct ? '#4caf50' : '#888');
  const chart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: data.labels,
      datasets: [{ label: 'Votes (%)', data: data.percents, backgroundColor: colors, borderColor: colors }]
    },
    options: {
      responsive: true,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: ctx => `${data.counts[ctx.dataIndex]} (${data.percents[ctx.dataIndex]}%)`
          }
        }
      },
      scales: {
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
      container.appendChild(label);

      const div = document.createElement('div');
      div.className = 'mcq-avatar-col';
      div.style.left = bar.x + 'px';
      div.style.top = (xScale.bottom + 4) + 'px';
      div.style.width = bar.width + 'px';
      (data.avatars[i] || []).forEach(id => {
        const img = document.createElement('img');
        img.className = 'avatar small';
        img.src = `/avatars/${id}.jpg`;
        if (data.names) img.title = data.names[id] || '';
        div.appendChild(img);
      });
      container.appendChild(div);
    });
  }
};
