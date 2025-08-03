const socket = io();

function formatTime(sec) {
    const m = String(Math.floor(sec / 60)).padStart(2, '0');
    const s = String(sec % 60).padStart(2, '0');
    return `${m}:${s}`;
}

let timerId, sinceId, lastTs = Date.now();

function hideProgress() {
    ['timer', 'answerStats', 'lastAnswer'].forEach(id => {
        document.getElementById(id).style.display = 'none';
    });
    clearInterval(timerId);
    clearInterval(sinceId);
}

function startTimer(seconds) {
    clearInterval(timerId);
    let remaining = seconds;
    const div = document.getElementById('timer');
    div.style.display = 'block';
    const tick = () => {
        div.textContent = formatTime(remaining);
        remaining--;
        if (remaining < 0) clearInterval(timerId);
    };
    tick();
    timerId = setInterval(tick, 1000);
}

function updateSince(ts) {
    lastTs = ts * 1000;
    clearInterval(sinceId);
    const div = document.getElementById('lastAnswer');
    div.style.display = 'block';
    const tick = () => {
        const diff = Math.floor((Date.now() - lastTs) / 1000);
        div.textContent = `Последний ответ: ${formatTime(diff)} назад`;
    };
    tick();
    sinceId = setInterval(tick, 1000);
}

document.body.addEventListener('htmx:afterSwap', (e) => {
    if (e.target.id === 'step') {
        const stepEl = e.target;
        if (stepEl.dataset.type !== 'quiz_results') {
            document.getElementById('results').innerHTML = '';
        }
        const timer = stepEl.dataset.timer;
        if (timer) {
            startTimer(parseInt(timer, 10));
        } else {
            hideProgress();
        }
    }
});

socket.on('reload', () => {
    htmx.ajax('GET', '/current', '#step');
});

socket.on('progress', data => {
    if (data.inactive) {
        hideProgress();
        return;
    }
    document.getElementById('answerStats').style.display = 'block';
    document.getElementById('answerStats').textContent = `Ответов: ${data.answered}/${data.total}`;
    if (data.ts) {
        updateSince(data.ts);
    } else {
        clearInterval(sinceId);
        const div = document.getElementById('lastAnswer');
        div.style.display = 'block';
        div.textContent = 'Последний ответ: —';
    }
});

socket.on('rating', rating => {
    document.getElementById('title').textContent = 'Итоговый рейтинг';
    document.getElementById('content').textContent = '';
    const div = document.getElementById('results');
    let html = '';
    rating.forEach(p => {
        html += `<div style="display:flex;align-items:center;margin-bottom:0.5rem">` +
            `<div style="width:2rem">${p.place}</div>` +
            `<img src="/avatar/${p.id}" width="40" height="40"/>` +
            `<div style="flex:1;margin-left:0.5rem">${p.name}</div>` +
            `<div class="highlight">${p.score}</div>` +
            `</div>`;
    });
    div.innerHTML = html;
});

socket.on('participants', data => {
    const div = document.getElementById('participants');
    div.innerHTML = '';
    data.who.forEach(p => {
        div.innerHTML += `<div class="participant"><img src="/avatar/${p.id}"/><div>${p.name}</div></div>`;
    });
});

document.getElementById('resetBtn').addEventListener('click', () => {
    window.location.href = '/reset';
});

socket.on('started', () => {
    document.getElementById('startBtn').style.display = 'none';
    document.getElementById('nextBtn').style.display = 'inline-block';
    document.getElementById('participants').style.display = 'none';
    document.getElementById('resetBtn').style.display = 'none';
    hideProgress();
});

socket.on('end', () => {
    document.getElementById('nextBtn').style.display = 'none';
    document.getElementById('resetBtn').style.display = 'inline-block';
    hideProgress();
});

socket.on('reset', () => {
    document.getElementById('startBtn').style.display = 'inline-block';
    document.getElementById('nextBtn').style.display = 'none';
    document.getElementById('resetBtn').style.display = 'inline-block';
    document.getElementById('participants').style.display = 'grid';
    document.getElementById('title').textContent = 'Ожидание начала…';
    document.getElementById('content').textContent = '';
    document.getElementById('results').innerHTML = '';
    hideProgress();
});
