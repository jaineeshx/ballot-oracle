/**
 * Ballot Oracle — Frontend Application Logic
 * State machine: hero → loading → ballot → ghost → quiz → results
 */

'use strict';

// ── Config ────────────────────────────────────────────────────────────────────
const BACKEND_URL = 'https://ballot-oracle-backend-265235104456.us-central1.run.app';
const API = (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1')
  ? 'http://localhost:8000/api'
  : `${BACKEND_URL}/api`;

// ── State ─────────────────────────────────────────────────────────────────────
const state = {
  address: '',
  ballot: null,
  ghostData: null,
  quizQuestions: [],
  quizAnswers: [],
  currentQ: 0,
  matchResults: null,
};

// ── DOM helpers ───────────────────────────────────────────────────────────────
const $  = (id) => document.getElementById(id);
const el = (tag, cls, html = '') => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (html) e.innerHTML = html;
  return e;
};

// ── Section navigation ────────────────────────────────────────────────────────
const SECTIONS = ['hero', 'loading', 'ballot', 'ghost', 'quiz', 'results'];

function showSection(name) {
  SECTIONS.forEach(s => {
    const sec = $(`section-${s}`);
    if (sec) sec.classList.toggle('active', s === name);
  });
  // Update nav steps
  const steps = ['ballot', 'ghost', 'quiz', 'results'];
  steps.forEach(s => {
    const step = document.querySelector(`.nav__step[data-step="${s}"]`);
    if (step) step.classList.toggle('active', s === name);
  });
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

// ── Toast ─────────────────────────────────────────────────────────────────────
let toastTimer;
function toast(msg, duration = 3500) {
  const t = $('toast');
  t.textContent = msg;
  t.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove('show'), duration);
}

// ── Hero Canvas — Particle field ──────────────────────────────────────────────
function initCanvas() {
  const canvas = $('hero-canvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  let W, H, particles;

  function resize() {
    W = canvas.width  = canvas.offsetWidth;
    H = canvas.height = canvas.offsetHeight;
  }

  function makeParticles() {
    particles = Array.from({ length: 80 }, () => ({
      x: Math.random() * W,
      y: Math.random() * H,
      r: Math.random() * 1.5 + 0.5,
      vx: (Math.random() - 0.5) * 0.3,
      vy: (Math.random() - 0.5) * 0.3,
      alpha: Math.random() * 0.5 + 0.2,
    }));
  }

  function draw() {
    ctx.clearRect(0, 0, W, H);
    // Draw connections
    for (let i = 0; i < particles.length; i++) {
      for (let j = i + 1; j < particles.length; j++) {
        const dx = particles[i].x - particles[j].x;
        const dy = particles[i].y - particles[j].y;
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (dist < 120) {
          ctx.beginPath();
          ctx.strokeStyle = `rgba(139,92,246,${0.15 * (1 - dist / 120)})`;
          ctx.lineWidth = 0.5;
          ctx.moveTo(particles[i].x, particles[i].y);
          ctx.lineTo(particles[j].x, particles[j].y);
          ctx.stroke();
        }
      }
    }
    // Draw dots
    particles.forEach(p => {
      p.x += p.vx; p.y += p.vy;
      if (p.x < 0) p.x = W;
      if (p.x > W) p.x = 0;
      if (p.y < 0) p.y = H;
      if (p.y > H) p.y = 0;
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(139,92,246,${p.alpha})`;
      ctx.fill();
    });
    requestAnimationFrame(draw);
  }

  resize();
  makeParticles();
  draw();
  window.addEventListener('resize', () => { resize(); makeParticles(); });
}

// ── Loading step animation ────────────────────────────────────────────────────
let loadingStepTimer;
function animateLoadingSteps() {
  const steps = ['lstep-1', 'lstep-2', 'lstep-3', 'lstep-4'];
  let i = 0;
  clearInterval(loadingStepTimer);
  steps.forEach(id => {
    const el = $(id);
    if (el) { el.classList.remove('active', 'done'); }
  });
  if (steps[0] && $(steps[0])) $(steps[0]).classList.add('active');

  loadingStepTimer = setInterval(() => {
    if (i < steps.length) {
      const cur = $(steps[i]);
      if (cur) { cur.classList.remove('active'); cur.classList.add('done'); }
    }
    i++;
    if (i < steps.length) {
      const next = $(steps[i]);
      if (next) next.classList.add('active');
    } else {
      clearInterval(loadingStepTimer);
    }
  }, 900);
}

// ── Fetch ballot ──────────────────────────────────────────────────────────────
async function fetchBallot(address) {
  showSection('loading');
  animateLoadingSteps();
  try {
    const res = await fetch(`${API}/ballot`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ address }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    state.ballot = await res.json();
    renderBallot(state.ballot);
    showSection('ballot');
  } catch (err) {
    console.error(err);
    toast(`⚠️ Error fetching ballot: ${err.message}`);
    showSection('hero');
  }
}

// ── Render ballot ─────────────────────────────────────────────────────────────
function renderBallot(data) {
  $('ballot-election-date').textContent = data.election_date || 'Election Day 2025';
  $('ballot-polling').textContent = data.polling_location ? `📍 ${data.polling_location}` : '';
  $('ballot-address-display').textContent = data.address || state.address;

  // Vote weight banner
  if (data.vote_weight) {
    $('vw-stat').textContent = `${(data.vote_weight.last_margin_votes || 847).toLocaleString()} votes`;
    $('vw-text').textContent = data.vote_weight.your_impact_statement || '';
  }

  // Races grid
  const grid = $('ballot-grid');
  grid.innerHTML = '';
  (data.races || []).forEach((race, idx) => {
    const card = el('div', 'race-card');
    card.setAttribute('role', 'listitem');
    card.setAttribute('id', `race-card-${idx}`);

    const levelLabel = race.level?.replace('_', ' ') || 'local';
    const candidates = (race.candidates || []).map(c =>
      `<div class="candidate-pill">
        <span class="candidate-pill__name">${c.name}</span>
        <span class="candidate-pill__party">${c.party || ''}</span>
      </div>`
    ).join('');

    card.innerHTML = `
      <div class="race-card__level race-card__level--${race.level || 'local'}">${levelLabel}</div>
      <div class="race-card__office">${race.office}</div>
      <div class="race-card__controls">${race.what_this_controls || ''}</div>
      <div class="race-card__candidates">${candidates}</div>
      <button class="race-card__ripple-btn" id="ripple-btn-${idx}" aria-label="See ripple effect for ${race.office}">
        🌊 See Daily Life Impact
      </button>
    `;

    card.querySelector(`#ripple-btn-${idx}`).addEventListener('click', (e) => {
      e.stopPropagation();
      openRippleModal(race);
    });

    grid.appendChild(card);
  });
}

// ── Ripple Effect Modal ───────────────────────────────────────────────────────
async function openRippleModal(race) {
  const overlay = $('ripple-modal-overlay');
  const title   = $('ripple-modal-title');
  const loading = $('ripple-loading');
  const content = $('ripple-content');

  title.textContent = race.office;
  loading.hidden = false;
  content.hidden = true;
  overlay.hidden = false;

  try {
    const res = await fetch(`${API}/ripple`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        race_name: race.office,
        candidate: (race.candidates?.[0]?.name) || '',
        district: state.ballot?.address || '',
      }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    renderRipple(content, data);
    loading.hidden = true;
    content.hidden = false;
  } catch (err) {
    loading.innerHTML = `<p style="color:var(--red)">Error loading impact data: ${err.message}</p>`;
  }
}

function renderRipple(container, data) {
  container.innerHTML = '';
  (data.ripples || []).forEach(r => {
    const card = el('div', 'ripple-card');
    card.innerHTML = `
      <div class="ripple-card__category">${r.category}</div>
      <div class="ripple-card__headline">${r.headline}</div>
      <div class="ripple-card__detail">${r.detail}</div>
      <div class="ripple-card__timeline">⏱ ${r.timeline}</div>
    `;
    container.appendChild(card);
  });
  if (data.bottom_line) {
    const bl = el('div', 'ripple-bottom-line', `💡 ${data.bottom_line}`);
    container.appendChild(bl);
  }
}

// ── Ghost Voter ───────────────────────────────────────────────────────────────
async function runGhostVoter() {
  const zip = $('ghost-zip').value.trim();
  const age = $('ghost-age').value;
  if (!zip || zip.length < 4) { toast('Please enter a valid ZIP code'); return; }

  $('ghost-result').hidden = true;
  $('ghost-loading').hidden = false;

  try {
    const res = await fetch(`${API}/ghost-voter`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ zip_code: zip, age_group: age, state: 'IL' }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    state.ghostData = await res.json();
    renderGhostResult(state.ghostData, age);
    $('ghost-loading').hidden = true;
    $('ghost-result').hidden = false;
  } catch (err) {
    $('ghost-loading').hidden = true;
    toast(`⚠️ Ghost Voter error: ${err.message}`);
  }
}

function renderGhostResult(data, ageGroup) {
  $('ghost-headline').textContent = data.headline || '';
  $('ghost-summary').textContent  = data.summary  || '';
  $('ghost-hook').textContent     = data.emotional_hook || '';

  // Animate bars
  const actual  = data.actual_turnout?.age_group_25_35   ?? 34;
  const senior  = data.actual_turnout?.age_group_65_plus ?? 71;
  const counter = data.counterfactual_turnout?.turnout_rate ?? 71;

  $('bar-young-label').textContent = `Ages ${ageGroup} (actual)`;
  $('bar-ghost-label').textContent = `Ages ${ageGroup} (if equal turnout)`;

  // Trigger CSS transitions after short delay
  setTimeout(() => {
    $('bar-senior').style.width = `${senior}%`;
    $('bar-young').style.width  = `${actual}%`;
    $('bar-ghost').style.width  = `${counter}%`;
  }, 200);

  $('bar-senior-val').textContent = `${senior}%`;
  $('bar-young-val').textContent  = `${actual}%`;
  $('bar-ghost-val').textContent  = `${counter}%`;

  // Flip cards
  const flipsEl = $('ghost-flips');
  flipsEl.innerHTML = '';
  (data.races_that_flip || []).forEach(r => {
    const card = el('div', 'flip-card');
    card.innerHTML = `
      <div class="flip-card__race">${r.race}</div>
      <div class="flip-card__actual">Actual winner: <strong>${r.actual_winner}</strong> (+${r.actual_margin?.toLocaleString() || 0} votes)</div>
      <div class="flip-card__arrow">↓</div>
      <div class="flip-card__winner">${r.counterfactual_winner}</div>
      ${r.flip ? '<span class="flip-card__badge">🔄 WOULD FLIP</span>' : ''}
    `;
    flipsEl.appendChild(card);
  });
}
// ── Quiz ──────────────────────────────────────────────────────────────────────
async function loadQuiz() {
  showSection('quiz');
  $('quiz-loading').style.display = 'block';
  $('quiz-card').hidden = true;
  state.quizAnswers = [];
  state.currentQ = 0;

  try {
    const res = await fetch(`${API}/quiz/questions`, { method: 'GET' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    state.quizQuestions = data.questions || [];
    $('quiz-loading').style.display = 'none';
    $('quiz-card').hidden = false;
    renderQuestion(0);
  } catch (err) {
    $('quiz-loading').innerHTML = `<p style="color:var(--red)">Error: ${err.message}</p>`;
  }
}

function renderQuestion(idx) {
  const q = state.quizQuestions[idx];
  if (!q) { submitQuiz(); return; }

  const total = state.quizQuestions.length;
  const pct   = (idx / total) * 100;

  $('quiz-progress').style.width = `${pct}%`;
  $('quiz-progress').parentElement.setAttribute('aria-valuenow', idx);
  $('quiz-progress-text').textContent = `Question ${idx + 1} of ${total}`;
  $('quiz-q-number').textContent = `Q${idx + 1}`;
  $('quiz-question').textContent = q.question;
  $('quiz-dimension').textContent = q.value_dimension || '';

  const optionsEl = $('quiz-options');
  optionsEl.innerHTML = '';
  (q.options || []).forEach((opt) => {
    const btn = el('button', 'quiz__option');
    btn.textContent = opt.text;
    btn.id = `quiz-opt-${idx}-${opt.id}`;
    btn.setAttribute('aria-label', opt.text);
    btn.addEventListener('click', () => {
      // Mark selected
      optionsEl.querySelectorAll('.quiz__option').forEach(b => b.classList.remove('selected'));
      btn.classList.add('selected');

      // Record answer
      state.quizAnswers.push({ question_id: q.id, answer_id: opt.id, value_score: opt.value_score });

      // Advance after brief visual pause
      setTimeout(() => {
        state.currentQ++;
        if (state.currentQ < state.quizQuestions.length) {
          // Animate card out/in
          const card = $('quiz-card');
          card.style.animation = 'none';
          card.offsetHeight; // reflow
          card.style.animation = '';
          renderQuestion(state.currentQ);
        } else {
          submitQuiz();
        }
      }, 340);
    });
    optionsEl.appendChild(btn);
  });
}

async function submitQuiz() {
  // Show 100% progress
  $('quiz-progress').style.width = '100%';
  $('quiz-progress-text').textContent = 'Analyzing your values…';

  showSection('results');
  $('results-loading').hidden = false;
  $('results-content').hidden = true;

  try {
    const res = await fetch(`${API}/quiz/match`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ answers: state.quizAnswers, address: state.address }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    state.matchResults = await res.json();
    renderResults(state.matchResults);
    $('results-loading').hidden = true;
    $('results-content').hidden = false;
  } catch (err) {
    $('results-loading').innerHTML = `<p style="color:var(--red)">Error matching values: ${err.message}</p>`;
  }
}

// ── Results ───────────────────────────────────────────────────────────────────
function renderResults(data) {
  const profile = data.values_profile || {};

  // Archetype emoji — pick from name
  const archetypeEmoji = pickArchetypeEmoji(data.civic_archetype || '');
  $('profile-archetype').textContent = archetypeEmoji;
  $('profile-name').textContent = data.civic_archetype || profile.profile_name || '';
  $('profile-desc').textContent = profile.profile_description || '';
  $('profile-primary').textContent = profile.primary_value || '';
  $('profile-secondary').textContent = profile.secondary_value || '';

  // Candidate matches
  const grid = $('matches-grid');
  grid.innerHTML = '';

  (data.candidate_matches || []).forEach((c, i) => {
    const score = c.match_score || 0;
    const scoreColor = score >= 75 ? 'var(--green)' : score >= 55 ? 'var(--gold)' : 'var(--red)';
    const card = el('div', 'match-card');
    card.setAttribute('role', 'listitem');
    card.setAttribute('id', `match-card-${i}`);
    card.innerHTML = `
      <div>
        <div class="match-card__name">${c.candidate_name}</div>
        <div class="match-card__office">${c.office}</div>
        <span class="match-card__party">${c.party || ''}</span>
        <div class="match-card__align">✅ Aligns on: <span>${c.top_alignment || ''}</span></div>
        <div class="match-card__diverg">⚡ Diverges on: <span>${c.top_divergence || ''}</span></div>
        <div style="font-size:0.82rem;color:var(--text-2);margin-top:0.4rem">${c.summary || ''}</div>
      </div>
      <div class="match-score">
        <div class="match-score__value" style="color:${scoreColor}">${score}%</div>
        <div class="match-score__label">match</div>
        <div class="match-score__bar"><div class="match-score__fill" id="mscore-fill-${i}" style="width:0%"></div></div>
      </div>
    `;
    grid.appendChild(card);

    // Animate score bar
    setTimeout(() => {
      const fill = $(`mscore-fill-${i}`);
      if (fill) fill.style.width = `${score}%`;
    }, 200 + i * 150);
  });
}

function pickArchetypeEmoji(name) {
  const n = (name || '').toLowerCase();
  if (n.includes('builder') || n.includes('community')) return '🏗️';
  if (n.includes('realist') || n.includes('pragmatic')) return '⚙️';
  if (n.includes('guardian') || n.includes('tradition')) return '🛡️';
  if (n.includes('visionar') || n.includes('future')) return '🔭';
  if (n.includes('justice') || n.includes('equity')) return '⚖️';
  if (n.includes('liberty') || n.includes('freedom')) return '🦅';
  return '🌟';
}

// ── Reset ─────────────────────────────────────────────────────────────────────
function resetApp() {
  state.address = '';
  state.ballot = null;
  state.ghostData = null;
  state.quizQuestions = [];
  state.quizAnswers = [];
  state.currentQ = 0;
  state.matchResults = null;
  $('address-input').value = '';
  showSection('hero');
}

// ── Event Bindings ────────────────────────────────────────────────────────────
function bindEvents() {
  // Address form
  $('address-form').addEventListener('submit', (e) => {
    e.preventDefault();
    const addr = $('address-input').value.trim();
    if (!addr || addr.length < 5) { toast('Please enter a full address'); return; }
    state.address = addr;
    fetchBallot(addr);
  });

  // Ghost voter from ballot banner
  $('btn-ghost-voter').addEventListener('click', () => {
    // Pre-fill ZIP from address if possible
    const zipMatch = state.address.match(/\b\d{5}\b/);
    if (zipMatch) $('ghost-zip').value = zipMatch[0];
    showSection('ghost');
  });

  // Run ghost simulation
  $('btn-run-ghost').addEventListener('click', runGhostVoter);

  // Ghost → Quiz
  $('btn-ghost-to-quiz').addEventListener('click', loadQuiz);

  // Ballot → Quiz
  $('btn-to-quiz').addEventListener('click', loadQuiz);

  // Restart buttons
  $('btn-restart').addEventListener('click', resetApp);
  $('btn-start-over-results').addEventListener('click', resetApp);

  // Close ripple modal
  $('btn-close-ripple').addEventListener('click', () => {
    $('ripple-modal-overlay').hidden = true;
  });
  $('ripple-modal-overlay').addEventListener('click', (e) => {
    if (e.target === $('ripple-modal-overlay')) $('ripple-modal-overlay').hidden = true;
  });

  // Keyboard: close modal on Escape
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') $('ripple-modal-overlay').hidden = true;
  });

  // Ghost ZIP: allow only digits
  $('ghost-zip').addEventListener('input', (e) => {
    e.target.value = e.target.value.replace(/\D/g, '').slice(0, 5);
  });
}

// ── Init ──────────────────────────────────────────────────────────────────────
function init() {
  showSection('hero');
  initCanvas();
  bindEvents();

  // Verify backend health
  fetch(`${API}/health`)
    .then(r => r.json())
    .then(d => {
      if (d.status === 'ok') {
        console.info(`✅ Ballot Oracle backend: ${d.model}`);
      }
    })
    .catch(() => {
      toast('⚠️ Backend offline — make sure the server is running');
    });
}

document.addEventListener('DOMContentLoaded', init);

