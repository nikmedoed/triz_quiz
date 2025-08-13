(() => {
  Office.onReady(() => {
    const questionEl = document.getElementById('question');
    const optionsEl = document.getElementById('options');
    const statusEl = document.getElementById('status');
    const prevBtn = document.getElementById('prev');
    const nextBtn = document.getElementById('next');
    let steps = [];
    let index = 0;

    function render() {
      if (!steps.length) {
        questionEl.textContent = 'No questions';
        optionsEl.innerHTML = '';
        return;
      }
      const step = steps[index];
      questionEl.textContent = step.title || 'Untitled';
      optionsEl.innerHTML = '';
      if (Array.isArray(step.options)) {
        for (const opt of step.options) {
          const li = document.createElement('li');
          li.textContent = opt;
          optionsEl.appendChild(li);
        }
      }
    }

    async function loadScenario() {
      try {
        const res = await fetch('http://localhost:8000/scenario.json');
        steps = await res.json();
        index = 0;
        render();
        statusEl.textContent = 'Scenario loaded';
      } catch (err) {
        statusEl.textContent = 'Failed to load scenario';
      }
    }

    prevBtn.onclick = () => {
      if (!steps.length) return;
      index = (index - 1 + steps.length) % steps.length;
      render();
    };

    nextBtn.onclick = () => {
      if (!steps.length) return;
      index = (index + 1) % steps.length;
      render();
    };

    const ws = new WebSocket('ws://localhost:8000/ws');
    ws.onopen = () => {
      statusEl.textContent = 'Connected';
      loadScenario();
    };
    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.type === 'reload') {
          loadScenario();
        }
      } catch {
        // ignore malformed messages
      }
    };
    ws.onerror = () => {
      statusEl.textContent = 'Connection error';
    };
  });
})();
