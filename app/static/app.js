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

async function authorizedFetch(url, options={}) {
  const headers = (await (window.getAuthHeaders ? window.getAuthHeaders() : {})) || {};
  const merged = { ...(options||{}), headers: { ...(options.headers||{}), ...headers } };
  return fetch(url, merged);
}

// Typing indicator
let typingDiv = null;
function showTyping(){ if (!messages) return; typingDiv = document.createElement('div'); typingDiv.className='msg bot'; typingDiv.textContent='…'; messages.appendChild(typingDiv); messages.parentElement.scrollTop = messages.parentElement.scrollHeight; }
function hideTyping(){ if (typingDiv) typingDiv.remove(); typingDiv = null; }

function sleeperPlayerLink(name){ const q = encodeURIComponent(name); return `https://sleeper.com/search/${q}`; }
function linkPlayerNames(text){ return text.replace(/\b([A-Z][a-z]+\s[A-Z][a-z]+)\b/g, (m)=>`[${m}](${sleeperPlayerLink(m)})`); }

async function askJson(q) {
  showTyping();
  try {
    const res = await authorizedFetch(apiUrl('/api/ask'), {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question: q, league_id: LEAGUE_ID || undefined })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data?.error || 'Request failed');
    const answer = linkPlayerNames(data.answer || '');
    addMessage('bot', answer, data.sources);
    return data;
  } finally { hideTyping(); }
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
    // addMessage('bot', data.answer || 'No answer.', data.sources); // This line is now handled by askJson
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

// Week selector in roster drawer for My Team
let currentWeek = null;
const weekPrevBtn = document.createElement('button'); weekPrevBtn.className='btn btn-secondary'; weekPrevBtn.textContent='Prev Week';
const weekNextBtn = document.createElement('button'); weekNextBtn.className='btn btn-secondary'; weekNextBtn.textContent='Next Week';
const weekLabel = document.createElement('span'); weekLabel.className='meta'; weekLabel.style.marginLeft='8px';

async function loadMyTeamWeek(delta=0){
  // initialize week if unknown
  if (currentWeek === null) {
    try { const s = await (await fetch(apiUrl('/api/health'))).json(); } catch {}
    // fallback: try /api/projections to get week
    const pj = await (await authorizedFetch(apiUrl('/api/projections'))).json().catch(()=>({}));
    currentWeek = pj.week || 1;
  }
  currentWeek = Math.max(1, (currentWeek||1) + delta);
  weekLabel.textContent = `Week ${currentWeek}`;
  const res = await authorizedFetch(apiUrl('/api/my-team/week', { week: currentWeek, league_id: LEAGUE_ID||'' }));
  const data = await res.json();
  const list = document.getElementById('roster-list');
  if (!res.ok) { list.innerHTML = `Error: ${data?.error || 'Failed to load'}`; return; }
  // Render starters for this week
  list.innerHTML = '';
  const card = document.createElement('div'); card.className='roster-card';
  const title = document.createElement('div'); title.className='title'; title.textContent = `${data.owner} — Week ${data.week}`; card.appendChild(title);
  const section = document.createElement('div'); section.className='players';
  const head = document.createElement('div'); head.className='meta'; head.textContent='Starters'; section.appendChild(head);
  (data.starters||[]).forEach(p=>{
    const row = document.createElement('div'); row.className='player';
    const left = document.createElement('div');
    const img = document.createElement('img'); img.src=playerThumbUrl(p.player_id); img.alt=p.full_name; img.width=22; img.height=22; img.style.borderRadius='50%'; img.style.marginRight='6px';
    left.appendChild(img); const name=document.createElement('span'); name.textContent=p.full_name; left.appendChild(name);
    const right = document.createElement('span'); const proj = (p.projected_points!=null)?` • ${p.projected_points} pts`:''; right.textContent=`${p.position||''} ${p.team||''}${proj}`;
    row.appendChild(left); row.appendChild(right); section.appendChild(row);
  });
  card.appendChild(section); list.appendChild(card);
}

// Insert week controls into drawer header
(function attachWeekControls(){ if(!drawer) return; const header = drawer.querySelector('.drawer-header'); if (!header) return; const ctrls = document.createElement('div'); ctrls.style.display='flex'; ctrls.style.gap='6px'; ctrls.style.alignItems='center'; ctrls.appendChild(weekPrevBtn); ctrls.appendChild(weekNextBtn); ctrls.appendChild(weekLabel); header.appendChild(ctrls); })();

weekPrevBtn.addEventListener('click', ()=> loadMyTeamWeek(-1));
weekNextBtn.addEventListener('click', ()=> loadMyTeamWeek(+1));

openDrawerBtn?.addEventListener('click', async ()=>{
  await loadRosters();
  await loadMyTeamWeek(0);
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
  const res = await authorizedFetch(apiUrl('/api/rosters', params));
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
    const res = await authorizedFetch(url, { method: 'GET' });
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

// Projects (league projections)
const projBtn = document.getElementById('load-proj');
const projList = document.getElementById('proj-list');
projBtn?.addEventListener('click', async ()=>{
  projList.innerHTML = 'Loading projections…';
  const res = await authorizedFetch(apiUrl('/api/league/projections', { league_id: LEAGUE_ID||'' }));
  const data = await res.json();
  if (!res.ok) { projList.textContent = data?.error || 'Error.'; return; }
  const table = data.standings || [];
  projList.innerHTML = '';
  table.forEach(entry => {
    const card = document.createElement('div'); card.className='roster-card';
    const title = document.createElement('div'); title.className='title'; title.textContent = `${entry.owner}`; card.appendChild(title);
    const metrics = document.createElement('div'); metrics.className='metrics';
    const m1 = document.createElement('div'); m1.className='metric'; m1.innerHTML = `<div class='label'>Proj Wins</div><div class='value'>${entry.proj_wins}</div>`;
    const m2 = document.createElement('div'); m2.className='metric'; m2.innerHTML = `<div class='label'>Proj Losses</div><div class='value'>${entry.proj_losses}</div>`;
    const m3 = document.createElement('div'); m3.className='metric'; m3.innerHTML = `<div class='label'>Proj Ties</div><div class='value'>${entry.proj_ties}</div>`;
    metrics.appendChild(m1); metrics.appendChild(m2); metrics.appendChild(m3);
    card.appendChild(metrics); projList.appendChild(card);
  });
});

// News
const newsBtn = document.getElementById('load-news');
const newsList = document.getElementById('news-list');
newsBtn?.addEventListener('click', async ()=>{
  newsList.innerHTML = 'Loading news…';
  const res = await authorizedFetch(apiUrl('/api/news', { user_id: 'default', lookback_hours: 48, limit: 25, league_id: LEAGUE_ID || '' }));
  const data = await res.json();
  if (!res.ok) { newsList.textContent = data?.error || 'Error.'; return; }
  const items = data.rss || [];
  newsList.innerHTML = '';
  items.forEach(n => {
    const div = document.createElement('div');
    div.className = 'msg bot';
    const a = document.createElement('a'); a.href = n.link; a.target = '_blank'; a.textContent = n.tldr || n.title;
    const meta = document.createElement('div'); meta.className='meta'; meta.textContent = `${n.source || n.domain || ''}`;
    div.appendChild(a); div.appendChild(meta); newsList.appendChild(div);
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
  const res = await authorizedFetch(apiUrl('/api/players/search', { q }));
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
  const res = await authorizedFetch(apiUrl('/api/trade/evaluate'), {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ teamA: teamA.map(p=>p.player_id), teamB: teamB.map(p=>p.player_id), league_id: LEAGUE_ID || undefined, provider: PROVIDER })
  });
  const data = await res.json();
  if (!res.ok) { tradeResult.textContent = data?.error || 'Error.'; return; }
  tradeResult.innerHTML = '';
  addMessage('bot', data.narrative || 'Result shown above.');
});