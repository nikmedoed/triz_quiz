// Minimal Chart.js render for MCQ reveal (no custom colors per requirements)
const mcqCountPlugin = {
  id: 'mcqCounts',
  afterDatasetsDraw(chart, args, opts) {
    const {ctx} = chart;
    ctx.save();
    ctx.fillStyle = '#000';
    ctx.textAlign = 'center';
    const meta = chart.getDatasetMeta(0);
    meta.data.forEach((bar, i) => {
      ctx.fillText(`${opts.counts[i]} (${opts.percents[i]}%)`, bar.x, bar.y - 5);
    });
    ctx.restore();
  }
};

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
        },
        mcqCounts: { counts: data.counts, percents: data.percents }
      },
      scales: {
        y: {
          ticks: { callback: value => value + '%' },
          suggestedMax: 100
        }
      },
      animation: { onComplete: () => { drawAvatars(); } }
    },
    plugins: [mcqCountPlugin]
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
