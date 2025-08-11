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

  let bestRows = 1;
  let bestCols = n;
  let bestSize = 0;
  let bestEmpty = n;

  for (let rows = 1; rows <= n; rows++) {
    const cols = Math.ceil(n / rows);
    const maxW = (width - gap * (cols - 1)) / cols;
    const maxH = ((height - gap * (rows - 1)) - gap) / rows / RATIO;
    const size = Math.min(maxW, maxH, MAX_SIZE);
    if (size <= 0) break;
    const empty = rows * cols - n;
    if (
      size > bestSize ||
      (Math.abs(size - bestSize) <= 16 && (empty < bestEmpty || (empty === bestEmpty && cols < bestCols)))
    ) {
      bestSize = size;
      bestRows = rows;
      bestCols = cols;
      bestEmpty = empty;
    }
  }

  grid.style.setProperty('--cols', bestCols);
  grid.style.setProperty('--card-w', `${bestSize}px`);

  Array.from(grid.children).forEach((child) => child.style.removeProperty('grid-column-start'));

  const base = Math.floor(n / bestRows);
  const extras = n % bestRows;
  const rowSizes = Array(bestRows).fill(base);
  const center = (bestRows - 1) / 2;
  const order = Array.from({ length: bestRows }, (_, i) => i).sort(
    (a, b) => Math.abs(a - center) - Math.abs(b - center)
  );
  for (let i = 0; i < extras; i++) {
    rowSizes[order[i]] += 1;
  }

  let index = 0;
  for (let r = 0; r < bestRows; r++) {
    const count = rowSizes[r];
    const offset = Math.floor((bestCols - count) / 2);
    const first = grid.children[index];
    if (first) first.style.gridColumnStart = offset + 1;
    index += count;
  }
}

window.addEventListener('DOMContentLoaded', layoutCards);
window.addEventListener('load', layoutCards);
window.addEventListener('resize', layoutCards);

