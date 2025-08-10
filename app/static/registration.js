const RATIO = 5 / 4; // height / width for a card
const MAX_SIZE = 192; // px, roughly 1.5 times the previous avatar size

function layoutCards() {
  const content = document.querySelector('.content');
  const grid = document.querySelector('.grid');
  if (!content || !grid) return;

  const n = grid.children.length;
  const width = content.clientWidth;
  const height = content.clientHeight;
  const gap = parseFloat(getComputedStyle(grid).gap) || 0;

  let bestCols = 1;
  let bestSize = 0;

  for (let cols = 1; cols <= n; cols++) {
    const size = (width - gap * (cols - 1)) / cols;
    if (size <= 0) break;
    const clamped = Math.min(size, MAX_SIZE);
    const rows = Math.ceil(n / cols);
    const totalHeight = rows * (clamped * RATIO) + gap * (rows - 1);
    if (totalHeight <= height && clamped > bestSize) {
      bestSize = clamped;
      bestCols = cols;
    }
  }

  if (bestSize === 0) {
    bestCols = Math.ceil(Math.sqrt(n));
    const size = (width - gap * (bestCols - 1)) / bestCols;
    bestSize = Math.max(16, Math.min(size, MAX_SIZE));
  }

  grid.style.setProperty('--cols', bestCols);
  grid.style.setProperty('--card-w', `${bestSize}px`);
}

window.addEventListener('load', layoutCards);
window.addEventListener('resize', layoutCards);

