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
      datasets: [{ label: 'Votes', data: data.counts, backgroundColor: colors, borderColor: colors }]
    },
    options: {
      responsive: true,
      plugins: { legend: { display: false } },
      animation: { onComplete: drawAvatars }
    }
  });

  function drawAvatars(){
    container.querySelectorAll('.mcq-avatar-col').forEach(e => e.remove());
    const meta = chart.getDatasetMeta(0);
    const xScale = chart.scales.x;
    meta.data.forEach((bar, i) => {
      const div = document.createElement('div');
      div.className = 'mcq-avatar-col';
      div.style.left = bar.x + 'px';
      div.style.top = (xScale.bottom + 4) + 'px';
      div.style.width = bar.width + 'px';
      (data.avatars[i] || []).forEach(id => {
        const img = document.createElement('img');
        img.className = 'avatar small';
        img.src = `/avatars/${id}.jpg`;
        div.appendChild(img);
      });
      container.appendChild(div);
    });
  }
};
