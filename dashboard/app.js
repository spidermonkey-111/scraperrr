/**
 * Scraperrr — app.js
 * Dashboard Logic: localStorage, article rendering, filters, sidebar, auto-refresh.
 */

'use strict';

// ── Constants ─────────────────────────────────────────────────
const DATA_URL = '/.tmp/articles.json';
const SCRAPER_URL = '/run-scraper';
const LS_KEY = 'scraperrr_v1';
const REFRESH_MS = 24 * 60 * 60 * 1000;
const STALE_MS = 24 * 60 * 60 * 1000;

// ── State ──────────────────────────────────────────────────────
const state = {
    articles: [],
    savedIds: new Set(),
    activeFilter: 'all',
    searchQuery: '',
    lastFetched: null,
    nextRefreshAt: null,
};

// ── DOM ────────────────────────────────────────────────────────
const $ = id => document.getElementById(id);

const els = {
    sidebar: $('sidebar'),
    overlay: $('sidebar-overlay'),
    hamburger: $('hamburger'),
    statusDot: $('status-dot'),
    statusText: $('status-text'),
    btnRefresh: $('btn-refresh'),
    btnRefreshMob: $('btn-refresh-mobile'),
    btnClearSaved: $('btn-clear-saved'),
    btnRefreshEmpty: $('btn-refresh-empty'),
    statTotal: $('stat-total-val'),
    statSaved: $('stat-saved-val'),
    statAge: $('stat-age-val'),
    nextRefresh: $('next-refresh-val'),
    feedGrid: $('feed-grid'),
    savedGrid: $('saved-grid'),
    savedSection: $('saved-section'),
    feedSection: $('feed-section'),
    feedCount: $('feed-count'),
    emptyState: $('empty-state'),
    skeleton: $('skeleton-loader'),
    toastCtr: $('toast-container'),
    searchInput: $('search-input'),
    navBtns: document.querySelectorAll('.nav-btn'),
    pageTitle: $('page-title'),
    navSavedCount: $('nav-saved-count'),
};

const cardTemplate = document.getElementById('card-template');

// ── localStorage ───────────────────────────────────────────────
function lsLoad() { try { return JSON.parse(localStorage.getItem(LS_KEY)) || null; } catch { return null; } }
function lsSave(p) { try { localStorage.setItem(LS_KEY, JSON.stringify(p)); } catch { } }
function persistState() {
    lsSave({ last_fetched: state.lastFetched, articles: state.articles, saved_ids: [...state.savedIds] });
}

// ── Helpers ────────────────────────────────────────────────────
function setStatus(mode, text) {
    els.statusDot.className = 'status-dot ' + mode;
    els.statusText.textContent = text;
}

function timeAgo(iso) {
    if (!iso) return '—';
    const m = Math.floor((Date.now() - new Date(iso)) / 60000);
    if (m < 1) return 'just now';
    if (m < 60) return `${m}m ago`;
    const h = Math.floor(m / 60);
    if (h < 24) return `${h}h ago`;
    return `${Math.floor(h / 24)}d ago`;
}

function formatNum(n) {
    if (n == null) return '';
    return n >= 1000 ? (n / 1000).toFixed(1) + 'k' : String(n);
}

function timeUntil(iso) {
    if (!iso) return '—';
    const ms = new Date(iso) - Date.now();
    if (ms <= 0) return 'now';
    const h = Math.floor(ms / 3600000);
    const m = Math.floor((ms % 3600000) / 60000);
    return h > 0 ? `${h}h ${m}m` : `${m}m`;
}

// ── Toast ──────────────────────────────────────────────────────
function toast(icon, text, dur = 2800) {
    const el = document.createElement('div');
    el.className = 'toast';
    el.innerHTML = `<span class="toast-icon">${icon}</span><span class="toast-text">${text}</span>`;
    els.toastCtr.appendChild(el);
    setTimeout(() => {
        el.classList.add('toast-exit');
        el.addEventListener('animationend', () => el.remove(), { once: true });
    }, dur);
}

// ── Sidebar ────────────────────────────────────────────────────
function openSidebar() {
    els.sidebar.classList.add('open');
    els.overlay.classList.add('visible');
    els.hamburger.classList.add('open');
    els.hamburger.setAttribute('aria-expanded', 'true');
}

function closeSidebar() {
    els.sidebar.classList.remove('open');
    els.overlay.classList.remove('visible');
    els.hamburger.classList.remove('open');
    els.hamburger.setAttribute('aria-expanded', 'false');
}

function toggleSidebar() {
    els.sidebar.classList.contains('open') ? closeSidebar() : openSidebar();
}

// ── Data Fetching ─────────────────────────────────────────────
async function fetchArticles(triggerScrape = false) {
    setStatus('loading', triggerScrape ? 'Scraping...' : 'Fetching...');
    els.btnRefresh.classList.add('spinning');
    if (els.btnRefreshMob) els.btnRefreshMob.classList.add('spinning');

    try {
        let data;
        if (triggerScrape) {
            // Run the Python scraper via the server endpoint
            const res = await fetch(SCRAPER_URL + '?t=' + Date.now());
            if (!res.ok) throw new Error(`Scraper HTTP ${res.status}`);
            data = await res.json();
            if (data.ok === false) throw new Error(data.error || 'Scraper failed');
        } else {
            // Just load the existing JSON file (used on page load)
            const res = await fetch(DATA_URL + '?t=' + Date.now());
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            data = await res.json();
        }

        state.articles = (data.articles || []).map(a => ({ ...a, is_saved: state.savedIds.has(a.id) }));
        state.lastFetched = data.scraped_at || new Date().toISOString();
        state.nextRefreshAt = new Date(new Date(state.lastFetched).getTime() + REFRESH_MS).toISOString();

        persistState();
        setStatus('online', 'Live');
        toast('✅', `${state.articles.length} articles loaded`);
        return true;
    } catch (e) {
        console.warn('[Scraperrr] fetch failed:', e);
        setStatus('error', 'Offline');
        toast('❌', `Failed: ${e.message}`, 5000);
        return false;
    } finally {
        els.btnRefresh.classList.remove('spinning');
        if (els.btnRefreshMob) els.btnRefreshMob.classList.remove('spinning');
    }
}

async function loadData() {
    showSkeleton(true);

    const cached = lsLoad();
    if (cached?.articles?.length) {
        state.savedIds = new Set(cached.saved_ids || []);
        state.lastFetched = cached.last_fetched;
        state.nextRefreshAt = new Date(new Date(state.lastFetched || 0).getTime() + REFRESH_MS).toISOString();
        state.articles = cached.articles.map(a => ({ ...a, is_saved: state.savedIds.has(a.id) }));

        const stale = Date.now() - new Date(state.lastFetched || 0) > STALE_MS;
        if (!stale) {
            showSkeleton(false);
            render(); updateStats();
            setStatus('online', 'Cached');
            toast('⚡', 'Loaded from cache');
            return;
        }
    }

    const ok = await fetchArticles();
    showSkeleton(false);
    if (!ok && !state.articles.length) { showEmpty(true); return; }
    render(); updateStats();
}

// ── Rendering ─────────────────────────────────────────────────
function showSkeleton(v) {
    els.skeleton.hidden = !v;
    if (v) { els.feedSection.hidden = true; els.savedSection.hidden = true; }
}

function showEmpty(v) {
    els.emptyState.hidden = !v;
    if (v) { els.feedSection.hidden = true; }
}

function getFiltered() {
    const q = state.searchQuery.toLowerCase();
    return state.articles.filter(a => {
        if (state.activeFilter === 'saved') { if (!state.savedIds.has(a.id)) return false; }
        else if (state.activeFilter !== 'all') {
            if (!a.source.startsWith(state.activeFilter)) return false;
        }
        if (q) { if (![a.title, a.summary, a.source].join(' ').toLowerCase().includes(q)) return false; }
        return true;
    });
}

function buildCard(article) {
    const clone = cardTemplate.content.cloneNode(true);
    const card = clone.querySelector('.article-card');

    card.setAttribute('data-id', article.id);
    card.setAttribute('data-source', article.source);
    if (article.is_saved) card.classList.add('saved');

    card.querySelector('.card-source-icon').textContent = article.source_icon || '📰';
    card.querySelector('.card-source-name').textContent = article.source;
    card.querySelector('.card-title').textContent = article.title || 'Untitled';

    const summaryEl = card.querySelector('.card-summary');
    if (article.summary) summaryEl.textContent = article.summary;
    else summaryEl.hidden = true;

    if (article.image_url) {
        const wrap = card.querySelector('.card-image-wrapper');
        const img = card.querySelector('.card-image');
        img.src = article.image_url; img.alt = article.title;
        img.onerror = () => { wrap.hidden = true; };
        wrap.hidden = false;
    }

    card.querySelector('.card-time').textContent = timeAgo(article.published_at);

    if (article.reddit_score != null) {
        const statsEl = card.querySelector('.card-reddit-stats');
        statsEl.hidden = false;
        card.querySelector('.reddit-score').append(formatNum(article.reddit_score));
        card.querySelector('.reddit-comments').append(formatNum(article.reddit_comments));
    }

    const linkEl = card.querySelector('.card-link');
    linkEl.href = article.url;
    linkEl.setAttribute('aria-label', `Read: ${article.title}`);

    const btnSave = card.querySelector('.btn-save');
    if (article.is_saved) { btnSave.classList.add('saved'); btnSave.setAttribute('aria-pressed', 'true'); }
    btnSave.setAttribute('aria-label', article.is_saved ? 'Unsave article' : 'Save article');
    btnSave.addEventListener('click', e => { e.stopPropagation(); toggleSave(article.id); });

    card.style.animationDelay = `${Math.random() * 0.12}s`;
    return card;
}

function render() {
    const filtered = getFiltered();
    els.feedGrid.innerHTML = '';
    els.savedGrid.innerHTML = '';

    if (!filtered.length && state.articles.length) {
        showEmpty(true); els.feedSection.hidden = true; els.savedSection.hidden = true;
        return;
    }
    showEmpty(false); els.feedSection.hidden = false;

    const saved = filtered.filter(a => state.savedIds.has(a.id));
    const unsaved = filtered.filter(a => !state.savedIds.has(a.id));

    if (saved.length > 0) {
        els.savedSection.hidden = false;
        saved.forEach(a => els.savedGrid.appendChild(buildCard(a)));
    } else {
        els.savedSection.hidden = true;
    }
    unsaved.forEach(a => els.feedGrid.appendChild(buildCard(a)));
    els.feedCount.textContent = unsaved.length;
}

function updateStats() {
    els.statTotal.textContent = state.articles.length || '—';
    els.statSaved.textContent = state.savedIds.size || '0';
    els.statAge.textContent = timeAgo(state.lastFetched);
    els.nextRefresh.textContent = timeUntil(state.nextRefreshAt);

    const cnt = state.savedIds.size;
    els.navSavedCount.hidden = cnt === 0;
    els.navSavedCount.textContent = cnt;
}

// ── Save ───────────────────────────────────────────────────────
function toggleSave(id) {
    const article = state.articles.find(a => a.id === id);
    if (!article) return;
    if (state.savedIds.has(id)) {
        state.savedIds.delete(id); article.is_saved = false;
        toast('🔖', 'Article removed');
    } else {
        state.savedIds.add(id); article.is_saved = true;
        toast('🔖', 'Article saved!');
    }
    persistState(); render(); updateStats();
}

function clearAllSaved() {
    if (!confirm('Clear all saved articles?')) return;
    state.savedIds.clear();
    state.articles.forEach(a => a.is_saved = false);
    persistState(); render(); updateStats();
    toast('🗑️', 'All saved articles cleared');
}

// ── Filters ────────────────────────────────────────────────────
const FILTER_LABELS = {
    'all': 'All Feed',
    'saved': 'Saved',
    "Ben's Bites": "Ben's Bites",
    'The AI Rundown': 'AI Rundown',
    'Reddit': 'Reddit',
};

function setFilter(val) {
    state.activeFilter = val;
    els.navBtns.forEach(btn => {
        const active = btn.dataset.filter === val;
        btn.classList.toggle('active', active);
        btn.setAttribute('aria-pressed', active ? 'true' : 'false');
    });
    els.pageTitle.textContent = FILTER_LABELS[val] || val;
    render();
}

// ── Tooltips for icon-only sidebar ────────────────────────────
function addTooltips() {
    els.navBtns.forEach(btn => {
        const label = btn.querySelector('.nav-label')?.textContent || btn.dataset.filter;
        btn.setAttribute('data-tooltip', label);
    });
}

// ── Auto-Refresh ───────────────────────────────────────────────
function scheduleAutoRefresh() {
    const nextMs = Math.max(0, new Date(state.nextRefreshAt || 0) - Date.now());
    setTimeout(async () => {
        toast('🔄', 'Auto-refreshing...');
        const ok = await fetchArticles();
        if (ok) { render(); updateStats(); }
        scheduleAutoRefresh();
    }, nextMs || REFRESH_MS);
}

// ── Next-refresh countdown ticker ──────────────────────────────
function startCountdown() {
    setInterval(() => { if (els.nextRefresh) els.nextRefresh.textContent = timeUntil(state.nextRefreshAt); }, 60000);
}

// ── Events ─────────────────────────────────────────────────────
function attachEvents() {
    // Hamburger
    els.hamburger?.addEventListener('click', toggleSidebar);
    els.overlay?.addEventListener('click', closeSidebar);

    // Refresh buttons — trigger a real scrape via server
    const doRefresh = async () => {
        showSkeleton(true);
        const ok = await fetchArticles(true); // true = call /run-scraper
        showSkeleton(false);
        if (ok) { render(); updateStats(); }
    };
    els.btnRefresh.addEventListener('click', doRefresh);
    els.btnRefreshMob?.addEventListener('click', doRefresh);
    els.btnRefreshEmpty?.addEventListener('click', doRefresh);

    // Nav filters
    els.navBtns.forEach(btn => btn.addEventListener('click', () => {
        setFilter(btn.dataset.filter);
        // Close sidebar on mobile after selecting
        if (window.innerWidth <= 640) closeSidebar();
    }));

    // Clear saved
    els.btnClearSaved?.addEventListener('click', clearAllSaved);

    // Search
    let timer;
    els.searchInput?.addEventListener('input', e => {
        clearTimeout(timer);
        timer = setTimeout(() => { state.searchQuery = e.target.value.trim(); render(); }, 250);
    });
}

// ── Animated Tooltip Component ─────────────────────────────────
// Vanilla JS port of the React AnimatedTooltipMotion component.
// Simulates Framer Motion spring physics for rotate + translateX.

const TOOLTIP_PEOPLE = [
    {
        id: 1,
        name: 'Aarav Mehta',
        designation: 'AI Researcher',
        image: 'https://images.unsplash.com/photo-1535713875002-d1d0cf377fde?w=64&h=64&fit=crop&crop=face',
    },
    {
        id: 2,
        name: 'Sofia Martinez',
        designation: 'Cloud Architect',
        image: 'https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=64&h=64&fit=crop&crop=face',
    },
    {
        id: 3,
        name: 'Kenji Tanaka',
        designation: 'Cybersecurity Analyst',
        image: 'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=64&h=64&fit=crop&crop=face',
    },
    {
        id: 4,
        name: 'Amelia Rossi',
        designation: 'UX Strategist',
        image: 'https://images.unsplash.com/photo-1438761681033-6461ffad8d80?w=64&h=64&fit=crop&crop=face',
    },
];

/**
 * Lightweight spring-physics simulator.
 * Replicates Framer Motion useSpring + useTransform behaviour.
 */
function createSpring({ stiffness = 100, damping = 15 } = {}) {
    let value = 0;
    let velocity = 0;
    let target = 0;
    let raf = null;

    const listeners = [];

    function tick() {
        const force = -stiffness * (value - target);
        const drag = -damping * velocity;
        const acceleration = force + drag;
        velocity += acceleration * 0.016; // ~60fps frame
        value += velocity * 0.016;

        listeners.forEach(fn => fn(value));

        if (Math.abs(value - target) > 0.01 || Math.abs(velocity) > 0.01) {
            raf = requestAnimationFrame(tick);
        } else {
            value = target;
            velocity = 0;
            raf = null;
            listeners.forEach(fn => fn(value));
        }
    }

    return {
        set(newTarget) {
            target = newTarget;
            if (!raf) raf = requestAnimationFrame(tick);
        },
        onChange(fn) { listeners.push(fn); },
    };
}

/** Map a value from one range to another. */
function mapRange(val, inMin, inMax, outMin, outMax) {
    return outMin + ((val - inMin) / (inMax - inMin)) * (outMax - outMin);
}

function initAnimatedTooltip() {
    const wrap = document.getElementById('animated-tooltip-wrap');
    if (!wrap) return;

    TOOLTIP_PEOPLE.forEach(person => {
        const item = document.createElement('div');
        item.className = 'tooltip-item';

        const bubble = document.createElement('div');
        bubble.className = 'tooltip-bubble';
        bubble.innerHTML = `
            <span class="tooltip-name">${person.name}</span>
            <span class="tooltip-designation">${person.designation}</span>
        `;

        const img = document.createElement('img');
        img.src = person.image;
        img.alt = person.name;
        img.width = 36;
        img.height = 36;
        img.loading = 'lazy';

        item.appendChild(bubble);
        item.appendChild(img);
        wrap.appendChild(item);

        // Spring physics for smooth rotation + translateX
        const rotateSpring = createSpring({ stiffness: 100, damping: 15 });
        const translateSpring = createSpring({ stiffness: 100, damping: 15 });

        let currentRotate = 0;
        let currentTranslate = 0;

        rotateSpring.onChange(v => {
            currentRotate = v;
            applyTransform();
        });
        translateSpring.onChange(v => {
            currentTranslate = v;
            applyTransform();
        });

        function applyTransform() {
            // base: translateX(-50%) for centering, plus dynamic offset
            bubble.style.transform =
                `translateX(calc(-50% + ${currentTranslate}px)) translateY(0) rotate(${currentRotate}deg)`;
        }

        img.addEventListener('mousemove', e => {
            const halfW = e.currentTarget.offsetWidth / 2;
            const relX = e.offsetX - halfW; // -halfW to +halfW

            const rotate = mapRange(relX, -halfW, halfW, -20, 20);
            const tx = mapRange(relX, -halfW, halfW, -24, 24);

            rotateSpring.set(rotate);
            translateSpring.set(tx);
        });

        img.addEventListener('mouseleave', () => {
            rotateSpring.set(0);
            translateSpring.set(0);
        });
    });
}

// ── Init ───────────────────────────────────────────────────────
async function init() {
    addTooltips();
    attachEvents();
    initAnimatedTooltip();
    await loadData();
    scheduleAutoRefresh();
    startCountdown();
}

document.addEventListener('DOMContentLoaded', init);
