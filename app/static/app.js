const form = document.getElementById('ask-form');
const input = document.getElementById('question');
const messages = document.getElementById('messages');

function addMessage(role, text) {
  const div = document.createElement('div');
  div.className = `msg ${role}`;
  div.textContent = text;
  messages.appendChild(div);
  messages.parentElement.scrollTop = messages.parentElement.scrollHeight;
}

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  const q = input.value.trim();
  if (!q) return;
  addMessage('user', q);
  input.value = '';
  form.querySelector('button').disabled = true;
  try {
    const res = await fetch('/api/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question: q })
    });
    const data = await res.json();
    addMessage('bot', data.answer || 'No answer.');
  } catch (err) {
    addMessage('bot', 'Error: ' + (err?.message || String(err)));
  } finally {
    form.querySelector('button').disabled = false;
  }
});