// Minimal Chart.js render for MCQ reveal (no custom colors per requirements)
window.renderMcq = function() {
  const ctx = document.getElementById('mcqChart');
  if (!ctx || !window.__mcq) return;
  const data = window.__mcq;
  new Chart(ctx, {
    type: 'bar',
    data: { labels: data.labels, datasets: [{ label: 'Votes', data: data.counts }] },
    options: { responsive: true, plugins: { legend: { display: false } } }
  });
};
