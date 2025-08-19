const form = document.getElementById('ask-form');
const input = document.getElementById('question');
const messages = document.getElementById('messages');

const loadBtn = document.getElementById('load-rosters');
const ownerSelect = document.getElementById('owner-select');
const saveTeamBtn = document.getElementById('save-team');
const rosterList = document.getElementById('roster-list');

function addMessage(role, text, sources) {
  const div = document.createElement('div');
  div.className = `msg ${role}`;
  div.textContent = text || '';
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
  const data = await res.json();
  if (!res.ok) throw new Error(data?.error || 'Request failed');
  return data;
}

function askStream(q) {
  return new Promise((resolve, reject) => {
    const es = new EventSource(`/api/ask/stream?question=${encodeURIComponent(q)}`);
    const container = addMessage('bot', '');
    es.onmessage = (e) => {
      try {
        const obj = JSON.parse(e.data);
        if (obj.status === 'planning') {
          container.textContent = 'Planning…';
        } else if (obj.token) {
          if (container.textContent === 'Planning…') container.textContent = '';
          container.textContent += obj.token;
        }
      } catch {
        container.textContent += e.data;
      }
    };
    es.addEventListener('sources', (e) => {
      try {
        const sources = JSON.parse(e.data);
        addMessage('bot', '', sources);
      } catch {}
    });
    es.addEventListener('error', (e) => {
      try {
        const data = JSON.parse(e.data);
        addMessage('bot', 'Error: ' + (data?.error || 'stream error'));
      } catch {
        addMessage('bot', 'Stream error');
      }
      es.close();
      reject(new Error('stream-error'));
    });
    es.addEventListener('end', () => {
      es.close();
      resolve();
    });
  });
}

async function loadRosters() {
  rosterList.innerHTML = 'Loading rosters…';
  const res = await fetch('/api/rosters');
  const data = await res.json();
  if (!Array.isArray(data)) {
    rosterList.textContent = 'Error loading rosters';
    return;
  }
  ownerSelect.innerHTML = '';
  const defaultName = 'Immigrants';
  data.forEach((r) => {
    const opt = document.createElement('option');
    opt.value = r.owner;
    opt.textContent = `${r.owner} (W-L-T: ${r.wins || 0}-${r.losses || 0}-${r.ties || 0})`;
    ownerSelect.appendChild(opt);
  });
  const found = Array.from(ownerSelect.options).find(o => o.value.toLowerCase().includes(defaultName.toLowerCase()));
  if (found) ownerSelect.value = found.value;

  // Render simple roster cards
  rosterList.innerHTML = '';
  data.forEach((r) => {
    const card = document.createElement('div');
    card.style.border = '1px solid #eee';
    card.style.borderRadius = '8px';
    card.style.padding = '8px';
    card.style.marginBottom = '8px';
    const h = document.createElement('div');
    h.style.fontWeight = '600';
    h.textContent = `${r.owner} • Roster ${r.roster_id}`;
    const rec = document.createElement('div');
    rec.style.color = '#666';
    rec.textContent = `Record: ${r.wins || 0}-${r.losses || 0}-${r.ties || 0}`;
    card.appendChild(h);
    card.appendChild(rec);
    rosterList.appendChild(card);
  });
}

async function saveMyTeam() {
  const owner_name = ownerSelect.value;
  try {
    await fetch('/api/my-team', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ owner_name })
    });
    addMessage('bot', `Saved your team as: ${owner_name}`);
  } catch (e) {
    addMessage('bot', 'Error saving team');
  }
}

loadBtn?.addEventListener('click', loadRosters);
saveTeamBtn?.addEventListener('click', saveMyTeam);

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
    try {
      const data = await askJson(q);
      addMessage('bot', data.answer || 'No answer.', data.sources);
    } catch (e2) {
      addMessage('bot', 'Error: ' + (e2?.message || String(e2)));
    }
  } finally {
    btn.disabled = false;
  }
});