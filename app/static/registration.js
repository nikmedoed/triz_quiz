const RATIO = 5 / 4; // height / width for a card
const MAX_SIZE = 192; // px, roughly 1.5 times the previous avatar size

function layoutCards() {
  const content = document.querySelector('.content');
  const grid = document.querySelector('.grid');
  const header = document.querySelector('.topbar');
  const footer = document.querySelector('.bottombar');
  if (!content || !grid) return;

  const n = grid.children.length;
  const gap = parseFloat(getComputedStyle(grid).gap) || 0;
  const width = content.clientWidth;
  const height =
    window.innerHeight - (header ? header.offsetHeight : 0) - (footer ? footer.offsetHeight : 0);

  let bestCols = 1;
  let bestSize = 0;
  let bestCover = 0;

  for (let cols = 1; cols <= n; cols++) {
    const rows = Math.ceil(n / cols);
    const maxW = (width - gap * (cols - 1)) / cols;
    const maxH = ((height - gap * (rows - 1)) - gap) / rows / RATIO;
    const size = Math.min(maxW, maxH, MAX_SIZE);
    if (size <= 0) break;
    const totalW = size * cols + gap * (cols - 1);
    const cover = totalW / width;
    if (size > bestSize || (bestSize - size <= 16 && cover > bestCover)) {
      bestSize = size;
      bestCols = cols;
      bestCover = cover;
    }
  }

  if (bestSize === 0) {
    bestCols = Math.ceil(Math.sqrt(n));
    const rows = Math.ceil(n / bestCols);
    const size = Math.min(
      (width - gap * (bestCols - 1)) / bestCols,
      ((height - gap * (rows - 1)) - gap) / rows / RATIO,
      MAX_SIZE
    );
    bestSize = Math.max(16, size);
  }

  grid.style.setProperty('--cols', bestCols);
  grid.style.setProperty('--card-w', `${bestSize}px`);

  // center the last row by offsetting its first card
  Array.from(grid.children).forEach((child) => child.style.removeProperty('grid-column-start'));
  const rows = Math.ceil(n / bestCols);
  const remaining = n % bestCols;
  if (remaining > 0) {
    const offset = Math.floor((bestCols - remaining) / 2);
    const index = bestCols * (rows - 1);
    const first = grid.children[index];
    if (first) first.style.gridColumnStart = offset + 1;
  }
}

window.addEventListener('DOMContentLoaded', layoutCards);
window.addEventListener('load', layoutCards);
window.addEventListener('resize', layoutCards);

