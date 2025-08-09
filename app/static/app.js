// Minimal Chart.js render for MCQ reveal (no custom colors per requirements)
window.renderMcq = function() {
  const ctx = document.getElementById('mcqChart');
  if (!ctx || !window.__mcq) return;
  const data = window.__mcq;
  const container = ctx.parentNode;
  const colors = data.labels.map((_, i) => i === data.correct ? '#4caf50' : '#888');
  const counts = data.counts;
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
            label: ctx => `${counts[ctx.dataIndex]} (${data.percents[ctx.dataIndex]}%)`
          }
        }
      },
      scales: {
        y: {
          ticks: { callback: value => value + '%' },
          suggestedMax: 100
        }
      },
      animation: { onComplete: () => { drawAvatars(); drawCounts(); } }
    }
  });

  function drawCounts(){
    const meta = chart.getDatasetMeta(0);
    const ctx2 = chart.ctx;
    ctx2.save();
    ctx2.fillStyle = '#000';
    ctx2.textAlign = 'center';
    meta.data.forEach((bar, i) => {
      ctx2.fillText(`${counts[i]} (${data.percents[i]}%)`, bar.x, bar.y - 5);
    });
    ctx2.restore();
  }

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
