window.renderMcq = function() {
  const container = document.getElementById('mcqChart');
  if (!container || !window.__mcq) return;
  const data = window.__mcq;
  const styles = getComputedStyle(document.documentElement);
  const primary = styles.getPropertyValue('--color-primary-500').trim() || '#e5231b';
  const neutral = styles.getPropertyValue('--color-slate-400').trim() || '#8c929c';

  container.innerHTML = '';

  data.labels.forEach((label, i) => {
    const row = document.createElement('div');
    row.className = 'mcq-row';

    const lab = document.createElement('div');
    lab.className = 'mcq-label';
    lab.textContent = label;
    row.appendChild(lab);

    const wrap = document.createElement('div');
    wrap.className = 'mcq-bar-area';

    const bar = document.createElement('div');
    bar.className = 'mcq-bar';
    bar.style.width = data.percents[i] + '%';
    bar.style.background = i === data.correct ? primary : neutral;
    wrap.appendChild(bar);

    const count = document.createElement('div');
    count.className = 'mcq-bar-count';
    count.textContent = `${data.counts[i]} (${data.percents[i]}%)`;
    count.style.color = i === data.correct ? primary : neutral;
    wrap.appendChild(count);

    row.appendChild(wrap);

    const avatars = document.createElement('div');
    avatars.className = 'mcq-avatar-row';
    (data.avatars[i] || []).forEach(id => {
      const img = document.createElement('img');
      img.className = 'avatar small';
      img.src = `/avatars/${id}.jpg`;
      if (data.names) img.title = data.names[id] || '';
      avatars.appendChild(img);
    });
    row.appendChild(avatars);

    container.appendChild(row);
  });
};

