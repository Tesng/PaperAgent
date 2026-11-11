/* Paper 講義 — 靜態網站（讀 data/papers.json 與 notes/*.md） */
(() => {
  'use strict';

  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => Array.from(el.querySelectorAll(s));
  const app = $('#app');
  const searchInput = $('#search');

  const state = {
    data: null,
    papers: [],
    bySlug: new Map(),
    query: '',
    tag: null,
    sort: 'added',
    bodies: new Map(),      // slug -> 純文字（全文搜尋用）
    bodiesPromise: null,
    tocObserver: null,
  };

  const QUESTIONS = [
    ['0', '問題', 'var(--s0)'],
    ['1', '核心想法', 'var(--s1)'],
    ['2', '資料流', 'var(--s2)'],
    ['3', '怎麼訓練', 'var(--s3)'],
    ['4', '證據與位置', 'var(--s4)'],
  ];

  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const uniq = (arr) => [...new Set(arr.filter(Boolean))];
  const encPath = (p) => String(p || '').split('/').map(encodeURIComponent).join('/');

  /* ───────── 資料 ───────── */

  async function loadIndex() {
    const res = await fetch('data/papers.json', { cache: 'no-store' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const papers = (data.papers || []).map((p) => ({
      authors: [], tags: [], builds_on: [], superseded_by: [], ...p,
    }));
    state.data = data;
    state.papers = papers;
    state.bySlug = new Map(papers.map((p) => [p.slug, p]));
  }

  async function fetchNote(p) {
    const res = await fetch(encPath(p.note), { cache: 'no-store' });
    if (!res.ok) throw new Error(`讀不到 ${p.note}（HTTP ${res.status}）`);
    return res.text();
  }

  function stripFrontmatter(md) {
    return md.replace(/^---[ \t]*\r?\n[\s\S]*?\r?\n---[ \t]*(\r?\n|$)/, '');
  }

  function ensureBodies() {
    if (state.bodiesPromise) return state.bodiesPromise;
    state.bodiesPromise = Promise.all(state.papers.map(async (p) => {
      try {
        const md = stripFrontmatter(await fetchNote(p));
        state.bodies.set(p.slug, md.replace(/[#*`>|_\-\[\]()!$]/g, ' ').toLowerCase());
      } catch (e) { /* 忽略 */ }
    })).then(() => { if (isHome()) renderHome(); });
    return state.bodiesPromise;
  }

  /* ───────── 路由 ───────── */

  const isHome = () => !/^#\/p\//.test(location.hash);

  function route() {
    const h = location.hash.replace(/^#/, '');
    const m = h.match(/^\/p\/([^/?#]+)/);
    if (m) return renderPaper(decodeURIComponent(m[1]));
    const qs = new URLSearchParams(h.split('?')[1] || '');
    if (qs.has('tag')) state.tag = qs.get('tag') || null;
    renderHome();
  }

  /* ───────── 首頁 ───────── */

  function filtered() {
    const q = state.query.trim().toLowerCase();
    let list = state.papers.filter((p) => !state.tag || p.tags.includes(state.tag));
    if (q) {
      const terms = q.split(/\s+/);
      list = list.filter((p) => {
        const hay = [p.short, p.title, p.one_liner, p.venue, p.year, p.slug,
          ...p.tags, ...p.authors, state.bodies.get(p.slug) || ''].join(' ').toLowerCase();
        return terms.every((t) => hay.includes(t));
      });
    }
    const by = {
      added: (a, b) => String(b.added).localeCompare(String(a.added)) || (b.year || 0) - (a.year || 0),
      'year-desc': (a, b) => (b.year || 0) - (a.year || 0) || a.short.localeCompare(b.short),
      'year-asc': (a, b) => (a.year || 0) - (b.year || 0) || a.short.localeCompare(b.short),
      name: (a, b) => a.short.localeCompare(b.short, 'en', { sensitivity: 'base' }),
    }[state.sort];
    return list.slice().sort(by);
  }

  function venueText(p) {
    const v = p.venue || '';
    return p.year && !v.includes(String(p.year)) ? [v, p.year].filter(Boolean).join(' · ') : v || p.year || '';
  }

  function card(p) {
    const cover = p.cover
      ? `<img src="${esc(encPath(p.cover))}" alt="${esc(p.short)} 架構圖" loading="lazy">`
      : `<span class="ph">${esc(p.short)}</span>`;
    return `
      <a class="card" href="#/p/${encodeURIComponent(p.slug)}">
        <div class="card-cover">${cover}</div>
        <div class="card-body">
          <div class="card-meta"><span>${esc(venueText(p))}</span>${p.status === 'draft' || p.incomplete ? '<span class="badge">草稿</span>' : ''}</div>
          <h2 class="card-title">${esc(p.short)}</h2>
          <p class="card-full">${esc(p.title)}</p>
          <p class="card-oneliner">${esc(p.one_liner)}</p>
          <div class="tag-row">${p.tags.map((t) => `<span class="tag">${esc(t)}</span>`).join('')}</div>
        </div>
      </a>`;
  }

  function emptyHtml() {
    if (!state.papers.length) {
      return `
        <div class="notice">
          <h2>還沒有任何講義</h2>
          <ol>
            <li>把論文 PDF 放進 <code>papers/</code> 資料夾。</li>
            <li>對 agent 說「<strong>整理新論文</strong>」。</li>
            <li>完成後重新整理這個頁面。</li>
          </ol>
          <p>每份講義會回答：它要解決什麼、核心想法、資料流、怎麼訓練、證據與位置。</p>
        </div>`;
    }
    const what = [state.query && `「${esc(state.query)}」`, state.tag && `標籤「${esc(state.tag)}」`].filter(Boolean).join('、');
    return `<div class="notice"><h2>沒有符合的論文</h2><p>找不到符合 ${what} 的講義。</p></div>`;
  }

  let renderSeq = 0;

  function renderHome() {
    renderSeq++;
    document.title = 'Paper 講義';
    disconnectToc();
    const list = filtered();
    const tags = Object.entries(state.data.tags || {});
    const chip = (label, value, n) => `<button class="chip" type="button" data-tag="${esc(value ?? '')}" aria-pressed="${state.tag === value}">${esc(label)}${n ? `<small>${n}</small>` : ''}</button>`;
    const searching = state.query.trim();
    app.innerHTML = `
      <section class="home">
        <div class="home-head">
          <div>
            <h1>論文講義</h1>
            <p class="sub">${searching ? `搜尋結果 ${list.length} / ${state.papers.length} 篇${state.bodiesPromise && state.bodies.size ? '（含內文）' : ''}` : `共 ${state.papers.length} 篇`}</p>
          </div>
          <label class="sort">排序
            <select id="sort">
              <option value="added">最新加入</option>
              <option value="year-desc">年份：新 → 舊</option>
              <option value="year-asc">年份：舊 → 新</option>
              <option value="name">名稱</option>
            </select>
          </label>
        </div>
        <ul class="qs" aria-label="每份講義回答的問題">
          ${QUESTIONS.map(([n, t, c]) => `<li style="--c:${c}"><b>${n}</b>${t}</li>`).join('')}
        </ul>
        ${tags.length ? `<div class="tags">${chip('全部', null)}${tags.map(([t, n]) => chip(t, t, n)).join('')}</div>` : ''}
        ${list.length ? `<div class="grid">${list.map(card).join('')}</div>` : emptyHtml()}
      </section>`;
    $('#sort').value = state.sort;
    $('#sort').addEventListener('change', (e) => { state.sort = e.target.value; renderHome(); });
    $$('.chip').forEach((b) => b.addEventListener('click', () => {
      const v = b.dataset.tag || null;
      state.tag = state.tag === v ? null : v;
      history.replaceState(null, '', state.tag ? `#/?tag=${encodeURIComponent(state.tag)}` : '#/');
      renderHome();
    }));
  }

  /* ───────── Markdown 渲染 ───────── */

  let currentBase = '';

  function resolveHref(href) {
    if (!href || /^([a-z][a-z0-9+.-]*:|\/\/|#)/i.test(href)) return href;
    try { return new URL(href, new URL(currentBase, location.href)).href; } catch (e) { return href; }
  }

  if (window.marked) {
    marked.use({
      gfm: true,
      walkTokens(token) {
        if (token.type === 'image') token.href = resolveHref(token.href);
        if (token.type === 'link') {
          const m = /^(?![a-z]+:)(?:.*\/)?([a-z0-9-]+)\.md(#.*)?$/i.exec(token.href || '');
          if (m && state.bySlug.has(m[1])) token.href = `#/p/${m[1]}`;
          else token.href = resolveHref(token.href);
        }
      },
    });
  }

  function mathHtml(item) {
    if (!window.katex) return `<code class="math-fallback">${esc(item.tex)}</code>`;
    try {
      return katex.renderToString(item.tex, { displayMode: item.display, throwOnError: false });
    } catch (e) {
      return `<code class="math-fallback">${esc(item.tex)}</code>`;
    }
  }

  function renderMarkdown(md, notePath) {
    if (!window.marked) return `<pre>${esc(md)}</pre>`;
    currentBase = notePath;
    const store = [];
    const keep = (tex, display) => { store.push({ tex: tex.trim(), display }); return `KXMATH${store.length - 1}KX`; };
    // 先把公式換成佔位符，避免被 Markdown 解析（略過程式碼區塊與行內程式碼）
    const parts = md.split(/(^```[\s\S]*?^```[^\n]*$|^~~~[\s\S]*?^~~~[^\n]*$)/m);
    const protectedMd = parts.map((part, i) => (i % 2 ? part : part.split(/(`[^`\n]+`)/).map((seg, j) => (j % 2 ? seg : seg
      .replace(/\$\$([\s\S]+?)\$\$/g, (_, t) => keep(t, true))
      .replace(/(^|[^\\$\w])\$(?!\s)([^$\n]+?)(?<![\s\\])\$(?![\w$])/g, (_, pre, t) => pre + keep(t, false))
    )).join(''))).join('');

    let html = marked.parse(protectedMd);
    html = html
      .replace(/<p>\s*KXMATH(\d+)KX\s*<\/p>/g, (_, i) => mathHtml(store[+i]))
      .replace(/KXMATH(\d+)KX/g, (_, i) => mathHtml(store[+i]))
      .replace(/[（(]待確認[）)]/g, (m) => `<mark class="tbc">${m}</mark>`);
    return html;
  }

  function splitTitle(md) {
    const m = md.match(/^[ \t]*#[ \t]+(.+?)[ \t#]*$/m);
    if (!m) return { title: '', body: md };
    return { title: m[1].trim(), body: md.slice(0, m.index) + md.slice(m.index + m[0].length) };
  }

  function enhanceNote(root) {
    // 章節編號與顏色
    $$('h2, h3', root).forEach((h, i) => {
      h.id = `sec-${i}`;
      if (h.tagName === 'H2') {
        const m = h.textContent.trim().match(/^(\d)\s*[.、．]/);
        if (m) h.dataset.sec = m[1];
      }
    });
    // 表格外框；第一張「速覽」表加特殊樣式
    $$('table', root).forEach((t) => {
      const wrap = document.createElement('div');
      wrap.className = 'table-wrap';
      const first = t.querySelector('th');
      if (first && first.textContent.trim() === '速覽') wrap.classList.add('summary');
      t.parentNode.insertBefore(wrap, t);
      wrap.appendChild(t);
    });
    // 圖片與圖說
    $$('p', root).forEach((p) => {
      const kids = Array.from(p.childNodes).filter((n) => !(n.nodeType === 3 && !n.textContent.trim()));
      if (kids.length && kids.every((n) => n.nodeName === 'IMG')) {
        p.classList.add('figure');
        const next = p.nextElementSibling;
        if (next && next.tagName === 'P' && next.children.length === 1 && next.firstElementChild.tagName === 'EM'
            && next.textContent.trim() === next.firstElementChild.textContent.trim()) {
          next.classList.add('figcap');
        }
      }
    });
    $$('img', root).forEach((img) => {
      img.loading = 'lazy';
      img.addEventListener('click', () => openLightbox(img.src, img.alt));
      img.addEventListener('error', () => {
        const span = document.createElement('span');
        span.className = 'img-missing';
        span.textContent = `圖片載入失敗：${decodeURIComponent(img.getAttribute('src') || '').replace(location.origin, '')}`;
        img.replaceWith(span);
      }, { once: true });
    });
    // 「解讀：」區塊
    $$('blockquote', root).forEach((b) => {
      if (/^\s*(\*\*)?解讀/.test(b.textContent)) b.classList.add('interp');
    });
    // 外部連結開新分頁
    $$('a[href]', root).forEach((a) => {
      const href = a.getAttribute('href');
      if (/^https?:/.test(href) && !href.startsWith(location.origin)) { a.target = '_blank'; a.rel = 'noopener'; }
    });
  }

  /* ───────── 講義頁 ───────── */

  function refChip(ref) {
    const q = state.bySlug.get(ref);
    return q
      ? `<a class="lchip" href="#/p/${encodeURIComponent(q.slug)}" title="${esc(q.title)}">${esc(q.short)}${q.year ? ` <small>${q.year}</small>` : ''}</a>`
      : `<span class="lchip">${esc(ref)}</span>`;
  }

  function lineageHtml(p) {
    const prev = uniq([...p.builds_on, ...state.papers.filter((o) => o.superseded_by.includes(p.slug)).map((o) => o.slug)]);
    const next = uniq([...p.superseded_by, ...state.papers.filter((o) => o.builds_on.includes(p.slug)).map((o) => o.slug)]);
    if (!prev.length && !next.length) return '';
    const items = (arr) => (arr.length ? arr.map(refChip).join('') : '<span class="lin-none">—</span>');
    return `
      <section class="lineage" aria-label="論文脈絡">
        <div class="lin-col"><div class="lin-label">改良自</div><div class="lin-items">${items(prev)}</div></div>
        <div class="lin-arrow" aria-hidden="true">→</div>
        <div class="lin-col self"><div class="lin-label">本篇</div><div class="lin-items"><span class="lchip self">${esc(p.short)}</span></div></div>
        <div class="lin-arrow" aria-hidden="true">→</div>
        <div class="lin-col"><div class="lin-label">被延伸 / 取代</div><div class="lin-items">${items(next)}</div></div>
      </section>`;
  }

  function pagerHtml(p) {
    const list = filtered();
    const idx = list.findIndex((x) => x.slug === p.slug);
    if (idx < 0) return '';
    const prev = list[idx - 1];
    const next = list[idx + 1];
    if (!prev && !next) return '';
    return `
      <nav class="pager" aria-label="上一篇與下一篇">
        ${prev ? `<a href="#/p/${encodeURIComponent(prev.slug)}"><small>← 上一篇</small>${esc(prev.short)}</a>` : '<span></span>'}
        ${next ? `<a class="next" href="#/p/${encodeURIComponent(next.slug)}"><small>下一篇 →</small>${esc(next.short)}</a>` : ''}
      </nav>`;
  }

  async function renderPaper(slug) {
    disconnectToc();
    const p = state.bySlug.get(slug);
    if (!p) {
      app.innerHTML = `<div class="notice"><h2>找不到這篇講義</h2><p><code>${esc(slug)}</code> 不在索引中。若剛新增，請執行 <code>python3 scripts/paper_tools.py index</code>。</p><p><a href="#/">← 回到列表</a></p></div>`;
      return;
    }
    const seq = ++renderSeq;
    app.innerHTML = '<div class="loading">載入講義中…</div>';
    let md;
    try {
      md = stripFrontmatter(await fetchNote(p));
    } catch (e) {
      if (seq !== renderSeq) return;
      app.innerHTML = `<div class="notice"><h2>講義載入失敗</h2><p>${esc(e.message)}</p><p><a href="#/">← 回到列表</a></p></div>`;
      return;
    }
    if (seq !== renderSeq) return; // 載入期間使用者已切換頁面

    const { title, body } = splitTitle(md);
    const links = [
      p.pdf && `<a class="btn" href="${esc(encPath(p.pdf))}" target="_blank" rel="noopener">PDF</a>`,
      p.arxiv && `<a class="btn" href="https://arxiv.org/abs/${esc(p.arxiv)}" target="_blank" rel="noopener">arXiv</a>`,
      p.code && `<a class="btn" href="${esc(p.code)}" target="_blank" rel="noopener">程式碼</a>`,
      p.project && `<a class="btn" href="${esc(p.project)}" target="_blank" rel="noopener">專案頁</a>`,
      '<button class="btn" type="button" id="print-btn">列印講義</button>',
    ].filter(Boolean).join('');

    document.title = `${p.short}｜Paper 講義`;
    app.innerHTML = `
      <article class="paper">
        <nav class="crumb"><a href="#/">← 全部論文</a></nav>
        <header class="paper-head">
          <div class="card-meta"><span>${esc(venueText(p))}</span>${p.status === 'draft' || p.incomplete ? '<span class="badge">草稿</span>' : ''}</div>
          <h1>${esc(title || p.short)}</h1>
          <p class="paper-title-en">${esc(p.title)}</p>
          ${p.authors.length ? `<p class="paper-authors">${esc(p.authors.join(', '))}</p>` : ''}
          <div class="paper-links">${links}</div>
          <div class="tag-row">${p.tags.map((t) => `<a class="tag" href="#/?tag=${encodeURIComponent(t)}">${esc(t)}</a>`).join('')}</div>
        </header>
        ${lineageHtml(p)}
        <div class="paper-layout">
          <aside class="toc" aria-label="目錄"><div class="toc-title">目錄</div><nav id="toc"></nav></aside>
          <div class="note" id="note">${renderMarkdown(body, p.note)}</div>
        </div>
        ${pagerHtml(p)}
      </article>`;

    const note = $('#note');
    enhanceNote(note);
    buildToc(note);
    $('#print-btn').addEventListener('click', () => window.print());
    window.scrollTo(0, 0);
  }

  /* ───────── 目錄 ───────── */

  function disconnectToc() {
    if (state.tocObserver) { state.tocObserver.disconnect(); state.tocObserver = null; }
  }

  function buildToc(note) {
    const toc = $('#toc');
    const heads = $$('h2, h3', note);
    toc.innerHTML = heads.map((h) => {
      const color = h.dataset.sec ? ` style="--c: var(--s${h.dataset.sec})"` : '';
      const text = h.textContent.replace(/：.*$/, '');
      return `<a href="#${h.id}" data-id="${h.id}" class="${h.tagName.toLowerCase()}"${color}>${esc(text)}</a>`;
    }).join('');
    toc.addEventListener('click', (e) => {
      const a = e.target.closest('a[data-id]');
      if (!a) return;
      e.preventDefault();
      document.getElementById(a.dataset.id)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
    if (!('IntersectionObserver' in window) || !heads.length) return;
    const setActive = (id) => $$('a', toc).forEach((a) => a.classList.toggle('active', a.dataset.id === id));
    state.tocObserver = new IntersectionObserver((entries) => {
      const visible = entries.filter((e) => e.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
      if (visible.length) setActive(visible[0].target.id);
    }, { rootMargin: '-70px 0px -70% 0px' });
    heads.forEach((h) => state.tocObserver.observe(h));
    setActive(heads[0].id);
  }

  /* ───────── 其他互動 ───────── */

  function openLightbox(src, alt) {
    const lb = $('#lightbox');
    const img = $('img', lb);
    img.src = src;
    img.alt = alt || '';
    lb.hidden = false;
  }
  $('#lightbox').addEventListener('click', () => { $('#lightbox').hidden = true; });

  let searchTimer = null;
  searchInput.addEventListener('input', () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      state.query = searchInput.value;
      if (state.query.trim()) ensureBodies();
      if (!isHome()) location.hash = state.tag ? `#/?tag=${encodeURIComponent(state.tag)}` : '#/';
      else renderHome();
    }, 120);
  });

  document.addEventListener('keydown', (e) => {
    const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement?.tagName);
    if (e.key === '/' && !typing) { e.preventDefault(); searchInput.focus(); searchInput.select(); }
    if (e.key === 'Escape') {
      if (!$('#lightbox').hidden) $('#lightbox').hidden = true;
      else if (document.activeElement === searchInput && searchInput.value) {
        searchInput.value = ''; state.query = ''; if (isHome()) renderHome();
      }
    }
  });

  $('#theme-toggle').addEventListener('click', () => {
    const root = document.documentElement;
    const dark = root.dataset.theme ? root.dataset.theme === 'dark' : matchMedia('(prefers-color-scheme: dark)').matches;
    root.dataset.theme = dark ? 'light' : 'dark';
    try { localStorage.setItem('paper-theme', root.dataset.theme); } catch (e) { /* 無痕模式等 */ }
  });

  function showLoadError(err) {
    const isFile = location.protocol === 'file:';
    app.innerHTML = isFile
      ? `<div class="notice">
           <h2>請用本機伺服器開啟</h2>
           <p>瀏覽器不允許直接從檔案讀取講義。請在 PaperAgent 資料夾執行：</p>
           <pre><code>python3 -m http.server 8000</code></pre>
           <p>然後打開 <a href="http://localhost:8000">http://localhost:8000</a>。</p>
         </div>`
      : `<div class="notice">
           <h2>讀不到索引檔</h2>
           <p><code>data/papers.json</code> 載入失敗（${esc(err.message)}）。</p>
           <p>請在專案根目錄執行 <code>python3 scripts/paper_tools.py index</code>。</p>
         </div>`;
  }

  /* ───────── 啟動 ───────── */

  window.addEventListener('hashchange', route);
  loadIndex().then(route).catch(showLoadError);
})();
