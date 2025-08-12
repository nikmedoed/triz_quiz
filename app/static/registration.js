const RATIO = 7 / 5; // height / width for a card, extra room for names
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
    if (!n) return;

    const gap = parseFloat(getComputedStyle(grid).gap) || 0;
    const width = content.clientWidth;
    const height =
        window.innerHeight -
        (header ? header.offsetHeight : 0) -
        (footer ? footer.offsetHeight : 0) -
        gap * 2; // keep a safety margin so names do not clip

    const target = width / height;
    let best = {rows: n, cols: 1, size: 0, score: 0};
    for (let rows = 1; rows <= n; rows++) {
        const cols = Math.ceil(n / rows);
        const maxW = (width - gap * (cols - 1)) / cols;
        const maxH = (height - gap * (rows - 1)) / rows;
        const size = Math.min(maxW, maxH / RATIO, MAX_SIZE);
        const gridRatio = cols / (rows * RATIO);
        const diff = Math.abs(gridRatio - target);
        const score = size - diff * 20;
        if (score > best.score) {
            best = {rows, cols, size, score};
        }
    }

    grid.style.setProperty('--card-w', `${best.size}px`);
    const gridWidth = best.cols * best.size + gap * (best.cols - 1);
    grid.style.width = `${gridWidth}px`;
}

window.addEventListener('DOMContentLoaded', layoutCards);
window.addEventListener('load', layoutCards);
window.addEventListener('resize', layoutCards);

