let API_BASE = '';
let LEAGUE_ID = localStorage.getItem('league_id') || '';
const backendInput = document.getElementById('backend-base');
const saveBackendBtn = document.getElementById('save-backend');
const leagueInput = document.getElementById('league-id');
const saveLeagueBtn = document.getElementById('save-league');
if (leagueInput) leagueInput.value = LEAGUE_ID;

function apiUrl(path, params = {}) {
  const urlBase = API_BASE ? API_BASE.replace(/\/$/, '') : '';
  const search = new URLSearchParams(params).toString();
  const full = (urlBase + path) + (search ? `?${search}` : '');
  return full;
}

// Tabs
const tabs = document.querySelectorAll('.tab');
const panels = document.querySelectorAll('.tab-panel');
tabs.forEach((t)=>{
  t.addEventListener('click',()=>{
    tabs.forEach(x=>x.classList.remove('active'));
    panels.forEach(p=>p.classList.remove('show'));
    t.classList.add('active');
    document.querySelector(`.tab-panel[data-tab="${t.dataset.tab}"]`).classList.add('show');
  });
});

// Chat
const form = document.getElementById('ask-form');
const input = document.getElementById('question');
const messages = document.getElementById('messages');

// Rosters
const loadBtn = document.getElementById('load-rosters');
const ownerSelect = document.getElementById('owner-select');
const saveTeamBtn = document.getElementById('save-team');
const rosterList = document.getElementById('roster-list');
let myTeamName = '';

function addMessage(role, text, sources) {
  const div = document.createElement('div');
  div.className = `msg ${role}`;
  div.textContent = text || '';
  if (sources && sources.length) {
    const src = document.createElement('div');
    src.style.marginTop = '6px';
    src.style.fontSize = '12px';
    src.style.color = '#9aa3b2';
    src.textContent = 'Sources: ' + sources.map(s => `${s.tool}${s.args ? '(' + JSON.stringify(s.args) + ')' : ''}`).join(', ');
    div.appendChild(src);
  }
  messages.appendChild(div);
  messages.parentElement.scrollTop = messages.parentElement.scrollHeight;
  return div;
}

async function askJson(q) {
  const res = await fetch(apiUrl('/api/ask'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question: q, league_id: LEAGUE_ID || undefined })
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data?.error || 'Request failed');
  return data;
}

function askStream(q) {
  return new Promise((resolve, reject) => {
    const qs = {};
    if (LEAGUE_ID) qs.league_id = LEAGUE_ID;
    const es = new EventSource(apiUrl('/api/ask/stream', { ...qs, question: q }));
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

function rosterCard(r) {
  const card = document.createElement('div');
  card.className = 'roster-card';
  if (myTeamName && r.owner === myTeamName) card.classList.add('mine');
  const title = document.createElement('div');
  title.className = 'title';
  title.textContent = r.owner;
  const meta = document.createElement('div');
  meta.className = 'meta';
  meta.textContent = `Roster ${r.roster_id} • Record ${r.wins||0}-${r.losses||0}-${r.ties||0}`;
  const badge = document.createElement('span');
  badge.className = 'badge';
  badge.textContent = 'View';
  badge.style.cursor = 'pointer';
  badge.addEventListener('click', async ()=>{
    badge.textContent = 'Loading…';
    const params = LEAGUE_ID ? { league_id: LEAGUE_ID } : {};
    const res = await fetch(apiUrl(`/api/rosters/${r.roster_id}`, params));
    const detail = await res.json();
    badge.textContent = 'View';
    const list = document.createElement('div');
    list.className = 'players';
    const head = document.createElement('div');
    head.className = 'meta';
    head.textContent = 'Starters';
    list.appendChild(head);
    (detail.starters||[]).forEach(p=>{
      const row = document.createElement('div');
      row.className = 'player';
      row.innerHTML = `<span>${p.full_name}</span><span>${p.position||''} ${p.team||''}</span>`;
      list.appendChild(row);
    });
    const head2 = document.createElement('div');
    head2.className = 'meta';
    head2.style.marginTop = '6px';
    head2.textContent = 'Bench';
    list.appendChild(head2);
    (detail.bench||[]).forEach(p=>{
      const row = document.createElement('div');
      row.className = 'player';
      row.innerHTML = `<span>${p.full_name}</span><span>${p.position||''} ${p.team||''}</span>`;
      list.appendChild(row);
    });
    const existing = card.querySelector('.players');
    if (existing) existing.remove(); else card.appendChild(list);
  });
  title.appendChild(badge);
  card.appendChild(title);
  card.appendChild(meta);
  return card;
}

async function loadRosters() {
  rosterList.innerHTML = 'Loading rosters…';
  const params = LEAGUE_ID ? { league_id: LEAGUE_ID } : {};
  const res = await fetch(apiUrl('/api/rosters', params));
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

  rosterList.innerHTML = '';
  data.forEach((r) => rosterList.appendChild(rosterCard(r)));
}

async function saveMyTeam() {
  const owner_name = ownerSelect.value;
  myTeamName = owner_name;
  try {
    await fetch(apiUrl('/api/my-team'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ owner_name })
    });
    addMessage('bot', `Saved your team as: ${owner_name}`);
    Array.from(document.querySelectorAll('.roster-card')).forEach(card=>{
      const name = card.querySelector('.title')?.childNodes[0]?.textContent || '';
      card.classList.toggle('mine', name === myTeamName);
    });
  } catch (e) {
    addMessage('bot', 'Error saving team');
  }
}

saveBackendBtn?.addEventListener('click', () => {
  API_BASE = (backendInput?.value || '').trim();
  addMessage('bot', API_BASE ? `Using backend: ${API_BASE}` : 'Using Netlify proxy');
});

saveLeagueBtn?.addEventListener('click', () => {
  LEAGUE_ID = (leagueInput?.value || '').trim();
  localStorage.setItem('league_id', LEAGUE_ID);
  addMessage('bot', LEAGUE_ID ? `Using league: ${LEAGUE_ID}` : 'Cleared league ID');
});

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