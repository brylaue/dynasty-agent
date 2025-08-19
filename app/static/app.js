const form = document.getElementById('ask-form');
const input = document.getElementById('question');
const messages = document.getElementById('messages');

function addMessage(role, text, sources) {
  const div = document.createElement('div');
  div.className = `msg ${role}`;
  div.textContent = text;
  if (sources && sources.length) {
    const src = document.createElement('div');
    src.style.marginTop = '6px';
    src.style.fontSize = '12px';
    src.style.color = '#666';
    src.textContent = 'Sources: ' + sources.map(s => `${s.tool}${s.args ? '(' + JSON.stringify(s.args) + ')' : ''}`).join(', ');
    div.appendChild(src);
  }
  messages.appendChild(div);
  messages.parentElement.scrollTop = messages.parentElement.scrollHeight;
  return div;
}

async function askJson(q) {
  const res = await fetch('/api/ask', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question: q })
  });
  return res.json();
}

function askStream(q) {
  return new Promise((resolve) => {
    const es = new EventSource(`/api/ask/stream?question=${encodeURIComponent(q)}`);
    const container = addMessage('bot', '');
    es.onmessage = (e) => {
      container.textContent += e.data;
    };
    es.addEventListener('sources', (e) => {
      try {
        const sources = JSON.parse(e.data.replace(/^data: /, ''));
        addMessage('bot', '', sources);
      } catch {}
    });
    es.addEventListener('end', () => {
      es.close();
      resolve();
    });
    es.onerror = () => {
      es.close();
      resolve();
    };
  });
}

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  const q = input.value.trim();
  if (!q) return;
  addMessage('user', q);
  input.value = '';
  const btn = form.querySelector('button');
  btn.disabled = true;
  try {
    const useStream = true;
    if (useStream) {
      await askStream(q);
    } else {
      const data = await askJson(q);
      addMessage('bot', data.answer || 'No answer.', data.sources);
    }
  } catch (err) {
    addMessage('bot', 'Error: ' + (err?.message || String(err)));
  } finally {
    btn.disabled = false;
  }
});