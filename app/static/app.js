window.renderMcq = function() {
  const container = document.getElementById('mcqChart');
  if (!container || !window.__mcq) return;
  const data = window.__mcq;
  const styles = getComputedStyle(document.documentElement);
  const primary = styles.getPropertyValue('--color-primary-500').trim() || '#e5231b';
  const neutral = styles.getPropertyValue('--color-slate-400').trim() || '#8c929c';

  container.classList.add('mcq-chart');
  container.innerHTML = '';

  data.labels.forEach((label, i) => {
    const col = document.createElement('div');
    col.className = 'mcq-col';

    const bar = document.createElement('div');
    bar.className = 'mcq-bar';
    bar.style.height = data.percents[i] + '%';
    bar.style.background = i === data.correct ? primary : neutral;

    const count = document.createElement('div');
    count.className = 'mcq-bar-count';
    count.textContent = `${data.counts[i]} (${data.percents[i]}%)`;
    bar.appendChild(count);

    col.appendChild(bar);

    const lab = document.createElement('div');
    lab.className = 'mcq-label';
    lab.textContent = label;
    col.appendChild(lab);

    const avatars = document.createElement('div');
    avatars.className = 'mcq-avatar-row';
    (data.avatars[i] || []).forEach(id => {
      const img = document.createElement('img');
      img.className = 'avatar small';
      img.src = `/avatars/${id}.jpg`;
      if (data.names) img.title = data.names[id] || '';
      avatars.appendChild(img);
    });
    col.appendChild(avatars);

    container.appendChild(col);
  });
};
