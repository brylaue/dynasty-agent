let API_BASE = '';
let PROVIDER = localStorage.getItem('provider') || 'sleeper';
let LEAGUE_ID = localStorage.getItem('league_id') || '';
const backendInput = document.getElementById('backend-base');
const saveBackendBtn = document.getElementById('save-backend');
const leagueInput = document.getElementById('league-id');
const saveLeagueBtn = document.getElementById('save-league');
if (leagueInput) leagueInput.value = LEAGUE_ID;

function apiUrl(path, params = {}) {
  const urlBase = API_BASE ? API_BASE.replace(/\/$/, '') : '';
  const merged = { provider: PROVIDER, ...params };
  const search = new URLSearchParams(merged).toString();
  return (urlBase + path) + (search ? `?${search}` : '');
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

function addMessage(role, text, sources) {
  const div = document.createElement('div');
  div.className = `msg ${role}`;
  div.textContent = text || '';
  if (sources && sources.length) {
    const src = document.createElement('div');
    src.style.marginTop = '6px';
    src.style.fontSize = '12px';
    src.style.color = '#6b7280';
    const parts = sources.map(s => {
      if (s.url) {
        return `<a href="${s.url}" target="_blank">${s.title || s.url}</a>`;
      }
      return `${s.tool}${s.args ? '(' + JSON.stringify(s.args) + ')' : ''}`;
    });
    src.innerHTML = 'Sources: ' + parts.join(', ');
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

form?.addEventListener('submit', async (e) => {
  e.preventDefault();
  const q = input.value.trim();
  if (!q) return;
  addMessage('user', q);
  input.value = '';
  const btn = form.querySelector('button');
  btn.disabled = true;
  try {
    // Disable streaming by default to avoid timeouts on some hosts
    const data = await askJson(q);
    addMessage('bot', data.answer || 'No answer.', data.sources);
  } catch (e2) {
    addMessage('bot', 'Error: ' + (e2?.message || String(e2)));
  } finally {
    btn.disabled = false;
  }
});

// Roster Drawer
const openDrawerBtn = document.getElementById('open-rosters');
const drawer = document.getElementById('drawer');
const overlay = document.getElementById('drawer-overlay');
const closeDrawerBtn = document.getElementById('close-drawer');
const ownerSelect = document.getElementById('owner-select');
const saveTeamBtn = document.getElementById('save-team');
const rosterList = document.getElementById('roster-list');

function showDrawer(show) {
  if (!drawer || !overlay) return;
  drawer.classList.toggle('hidden', !show);
  overlay.classList.toggle('hidden', !show);
}

openDrawerBtn?.addEventListener('click', async ()=>{
  await loadRosters();
  showDrawer(true);
});
closeDrawerBtn?.addEventListener('click', ()=> showDrawer(false));
overlay?.addEventListener('click', ()=> showDrawer(false));

function playerThumbUrl(playerId) {
  if (!playerId) return '';
  return `https://sleepercdn.com/content/nfl/players/thumb/${playerId}.jpg`;
}

function rosterCard(r) {
  const card = document.createElement('div');
  card.className = 'roster-card';
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
    const params = {};
    if (LEAGUE_ID) params.league_id = LEAGUE_ID;
    const res = await fetch(apiUrl(`/api/rosters/${r.roster_id}`, params));
    const detail = await res.json();
    badge.textContent = 'View';
    const existing = card.querySelector('.players');
    if (existing) existing.remove();
    const list = document.createElement('div');
    list.className = 'players';
    const head = document.createElement('div');
    head.className = 'meta';
    head.textContent = 'Starters';
    list.appendChild(head);
    (detail.starters||[]).forEach(p=>{
      const row = document.createElement('div');
      row.className = 'player';
      const left = document.createElement('div');
      const img = document.createElement('img');
      img.src = playerThumbUrl(p.player_id);
      img.alt = p.full_name;
      img.width = 22; img.height = 22; img.style.borderRadius = '50%'; img.style.marginRight = '6px';
      left.appendChild(img);
      const name = document.createElement('span');
      name.textContent = p.full_name;
      left.appendChild(name);
      const right = document.createElement('span');
      const proj = (p.projected_points != null) ? ` • ${p.projected_points.toFixed ? p.projected_points.toFixed(1) : p.projected_points} pts` : '';
      right.textContent = `${p.position||''} ${p.team||''}${proj}`;
      row.appendChild(left);
      row.appendChild(right);
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
      const left = document.createElement('div');
      const img = document.createElement('img');
      img.src = playerThumbUrl(p.player_id);
      img.alt = p.full_name;
      img.width = 22; img.height = 22; img.style.borderRadius = '50%'; img.style.marginRight = '6px';
      left.appendChild(img);
      const name = document.createElement('span');
      name.textContent = p.full_name;
      left.appendChild(name);
      const right = document.createElement('span');
      right.textContent = `${p.position||''} ${p.team||''}`;
      row.appendChild(left);
      row.appendChild(right);
      list.appendChild(row);
    });
    card.appendChild(list);
  });
  title.appendChild(badge);
  card.appendChild(title);
  card.appendChild(meta);
  return card;
}

// Persist my team locally for frontend behavior
let MY_TEAM = localStorage.getItem('my_team') || '';

async function loadRosters() {
  if (!rosterList) return;
  rosterList.innerHTML = 'Loading rosters…';
  const params = {};
  if (LEAGUE_ID) params.league_id = LEAGUE_ID;
  const res = await fetch(apiUrl('/api/rosters', params));
  if (!res.ok) {
    const data = await res.json().catch(()=>({}));
    rosterList.textContent = `Error loading rosters: ${data?.error || res.statusText}`;
    return;
  }
  const data = await res.json();
  if (!Array.isArray(data)) {
    rosterList.textContent = 'No rosters found.';
    return;
  }
  ownerSelect.innerHTML = '';
  data.forEach((r) => {
    const opt = document.createElement('option');
    opt.value = r.owner;
    opt.textContent = `${r.owner} (W-L-T: ${r.wins || 0}-${r.losses || 0}-${r.ties || 0})`;
    ownerSelect.appendChild(opt);
  });
  if (MY_TEAM) ownerSelect.value = MY_TEAM;
  rosterList.innerHTML = '';
  data.forEach((r) => rosterList.appendChild(rosterCard(r)));
}

async function saveMyTeam() {
  const owner_name = ownerSelect.value;
  MY_TEAM = owner_name;
  localStorage.setItem('my_team', owner_name);
  try {
    const url = apiUrl('/api/my-team', { owner_name, user_id: 'default' });
    const res = await fetch(url, { method: 'GET' });
    if (!res.ok) throw new Error('Failed to save');
    addMessage('bot', `Saved your team as: ${owner_name}`);
  } catch (e) {
    addMessage('bot', 'Error saving team');
  }
}

// Gentle hint if team is not set when chatting
if (!MY_TEAM) {
  addMessage('bot', 'Tip: set your team in the Rosters drawer to personalize advice.');
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

saveTeamBtn?.addEventListener('click', saveMyTeam);

// Projections
const projBtn = document.getElementById('load-proj');
const projList = document.getElementById('proj-list');
projBtn?.addEventListener('click', async ()=>{
  projList.innerHTML = 'Loading projections…';
  const params = {};
  if (LEAGUE_ID) params.league_id = LEAGUE_ID;
  const res = await fetch(apiUrl('/api/projections', params));
  const data = await res.json();
  if (!res.ok) { projList.textContent = data?.error || 'Error.'; return; }
  const items = data.projections || [];
  projList.innerHTML = '';
  items.forEach(p => {
    const card = document.createElement('div');
    card.className = 'roster-card';
    card.innerHTML = `<div class="title">Roster ${p.roster_id}</div><div class="meta">Projected: ${p.projected_points ?? 'N/A'}</div>`;
    projList.appendChild(card);
  });
});

// News
const newsBtn = document.getElementById('load-news');
const newsList = document.getElementById('news-list');
newsBtn?.addEventListener('click', async ()=>{
  newsList.innerHTML = 'Loading news…';
  const res = await fetch(apiUrl('/api/news', { user_id: 'default', lookback_hours: 48, limit: 25, league_id: LEAGUE_ID || '' }));
  const data = await res.json();
  if (!res.ok) { newsList.textContent = data?.error || 'Error.'; return; }
  const items = data.rss || [];
  newsList.innerHTML = '';
  items.forEach(n => {
    const div = document.createElement('div');
    div.className = 'msg bot';
    const a = document.createElement('a');
    a.href = n.link; a.target = '_blank'; a.textContent = n.title;
    const meta = document.createElement('div'); meta.className='meta'; meta.textContent = `${n.source} • ${n.published || ''}`;
    div.appendChild(a); div.appendChild(meta);
    newsList.appendChild(div);
  });
});

// Trade Calculator
const tradeAInput = document.getElementById('trade-a-search');
const tradeASuggest = document.getElementById('trade-a-suggest');
const tradeAList = document.getElementById('trade-a-list');
const tradeBInput = document.getElementById('trade-b-search');
const tradeBSuggest = document.getElementById('trade-b-suggest');
const tradeBList = document.getElementById('trade-b-list');
const tradeEvalBtn = document.getElementById('trade-eval');
const tradeResult = document.getElementById('trade-result');
let teamA = []; let teamB = [];

function renderTradeList(listEl, arr) {
  listEl.innerHTML = '';
  arr.forEach((p, idx) => {
    const item = document.createElement('div');
    item.className = 'player';
    item.innerHTML = `<span>${p.full_name} (${p.position||''} ${p.team||''})</span><button class='btn btn-secondary' data-idx='${idx}'>Remove</button>`;
    item.querySelector('button').addEventListener('click', ()=>{
      arr.splice(idx,1); renderTradeList(listEl, arr);
    });
    listEl.appendChild(item);
  });
}

async function searchPlayers(q, suggestEl, onPick) {
  suggestEl.innerHTML = '';
  if (!q || q.length < 2) return;
  const res = await fetch(apiUrl('/api/players/search', { q }));
  const data = await res.json();
  (data||[]).forEach(p => {
    const item = document.createElement('div');
    item.className = 'player';
    item.textContent = `${p.full_name} (${p.position||''} ${p.team||''})`;
    item.addEventListener('click', ()=>{ onPick(p); suggestEl.innerHTML=''; });
    suggestEl.appendChild(item);
  });
}

tradeAInput?.addEventListener('input', ()=> searchPlayers(tradeAInput.value, tradeASuggest, (p)=>{ teamA.push(p); renderTradeList(tradeAList, teamA); }));
tradeBInput?.addEventListener('input', ()=> searchPlayers(tradeBInput.value, tradeBSuggest, (p)=>{ teamB.push(p); renderTradeList(tradeBList, teamB); }));

tradeEvalBtn?.addEventListener('click', async ()=>{
  tradeResult.innerHTML = 'Evaluating…';
  const res = await fetch(apiUrl('/api/trade/evaluate'), {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ teamA: teamA.map(p=>p.player_id), teamB: teamB.map(p=>p.player_id), league_id: LEAGUE_ID || undefined, provider: PROVIDER })
  });
  const data = await res.json();
  if (!res.ok) { tradeResult.textContent = data?.error || 'Error.'; return; }
  tradeResult.innerHTML = '';
  addMessage('bot', data.narrative || 'Result shown above.');
});