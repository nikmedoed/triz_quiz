const RATIO = 5 / 4; // height / width for a card
const MAX_SIZE = 192; // px, roughly 1.5 times the previous avatar size

function layoutCards() {
  const content = document.querySelector('.content');
  const grid = document.querySelector('.grid');
  const header = document.querySelector('.topbar');
  const footer = document.querySelector('.bottombar');
  if (!content || !grid) return;

  const cards = Array.from(grid.children);
  cards
    .sort((a, b) => new Date(a.dataset.joined) - new Date(b.dataset.joined))
    .forEach((c) => grid.appendChild(c));

  const n = cards.length;
  const gap = parseFloat(getComputedStyle(grid).gap) || 0;
  const width = content.clientWidth;
  const height =
    window.innerHeight - (header ? header.offsetHeight : 0) - (footer ? footer.offsetHeight : 0);

  const aspect = width / height;
  let cols = Math.ceil(Math.sqrt(n * aspect * RATIO));
  cols = Math.min(n, Math.max(1, cols));
  while (cols > 1 && n % cols !== 0 && n % cols <= cols / 2) {
    cols -= 1;
  }
  const rows = Math.ceil(n / cols);

  const maxW = (width - gap * (cols - 1)) / cols;
  const maxH = (height - gap * (rows - 1)) / rows / RATIO;
  const size = Math.min(maxW, maxH, MAX_SIZE);

  grid.style.setProperty('--cols', cols);
  grid.style.setProperty('--card-w', `${size}px`);

  cards.forEach((child) => child.style.removeProperty('grid-column-start'));

  const base = Math.floor(n / rows);
  const extras = n % rows;
  const rowSizes = Array(rows).fill(base);
  const center = (rows - 1) / 2;
  const order = Array.from({ length: rows }, (_, i) => i).sort(
    (a, b) => Math.abs(a - center) - Math.abs(b - center)
  );
  for (let i = 0; i < extras; i++) {
    rowSizes[order[i]] += 1;
  }

  let index = 0;
  for (let r = 0; r < rows; r++) {
    const count = rowSizes[r];
    const offset = Math.round((cols - count) / 2);
    const first = cards[index];
    if (first) first.style.gridColumnStart = offset + 1;
    index += count;
  }
}

window.addEventListener('DOMContentLoaded', layoutCards);
window.addEventListener('load', layoutCards);
window.addEventListener('resize', layoutCards);

