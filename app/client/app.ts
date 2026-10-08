/* CallVerse browser script (TypeScript, compiled to public/js/app.js by `npm run build`).
   Progressive enhancement only: every page works without it. No inline styles (CSP). */
(() => {
  const calm = matchMedia('(prefers-reduced-motion: reduce)').matches;

  // ---- tiny DOM helpers ------------------------------------------------------------------------
  const $ = <T extends Element = HTMLElement>(sel: string, root: ParentNode = document) => root.querySelector<T>(sel);
  const $$ = <T extends Element = HTMLElement>(sel: string, root: ParentNode = document) => [...root.querySelectorAll<T>(sel)];
  const byId = <T extends HTMLElement = HTMLElement>(id: string) => document.getElementById(id) as T | null;
  const make = <K extends keyof HTMLElementTagNameMap>(tag: K, props: Partial<HTMLElementTagNameMap[K]> = {}): HTMLElementTagNameMap[K] =>
    Object.assign(document.createElement(tag), props);
  /** The closest ancestor of the event target matching `sel` (event delegation). */
  const hit = <T extends Element = HTMLElement>(e: Event, sel: string) =>
    ((e.target as Element | null)?.closest?.(sel) ?? null) as T | null;

  // Small storage helpers: storage can be blocked, and the app must keep working without it
  const store = {
    get(k: string) { try { return localStorage.getItem(k); } catch { return null; } },
    set(k: string, v: string) { try { localStorage.setItem(k, v); } catch { /* blocked */ } },
    sget(k: string) { try { return sessionStorage.getItem(k); } catch { return null; } },
    sset(k: string, v: string) { try { sessionStorage.setItem(k, v); } catch { /* blocked */ } },
    sdel(k: string) { try { sessionStorage.removeItem(k); } catch { /* blocked */ } },
  };

  // Toasts
  const stack = document.body.appendChild(make('div', { className: 'toasts', role: 'status', ariaLive: 'polite' }));
  const toast = (msg: string) => {
    const t = stack.appendChild(make('div', { className: 'toast', textContent: msg }));
    setTimeout(() => { t.classList.add('out'); setTimeout(() => t.remove(), 450); }, 2600);
  };

  // Advisor actions (demo: nothing is sent anywhere)
  const answer = $('.answer');
  $$('[data-action]').forEach((b) => b.addEventListener('click', async () => {
    const text = answer?.querySelector('p')?.textContent?.trim() ?? '';
    switch (b.dataset.action) {
      case 'use':
        try { await navigator.clipboard.writeText(text); toast('Answer copied to clipboard'); }
        catch { toast('Copy blocked by the browser, select the text instead'); }
        break;
      case 'edit': {
        const p = answer && $('p', answer);
        if (!answer || !p) break;
        const on = p.getAttribute('contenteditable') !== 'true';
        p.setAttribute('contenteditable', String(on));
        answer.toggleAttribute('contenteditable', on);
        if (on) { p.focus(); toast('Editing, press Edit again to finish'); } else toast('Edits kept in this page only');
        break;
      }
      case 'escalate': toast('Escalation noted (demo, nothing was sent)'); break;
    }
  }));

  // Tables: live filter + click-to-sort
  $$<HTMLTableElement>('table.data').forEach((table) => {
    const body = table.tBodies[0];
    const head = table.tHead!.rows[0];
    const rows = [...body.rows];
    if (rows.length > 3) {
      const tools = make('div', { className: 'table-tools' });
      const input = make('input', { type: 'search', placeholder: 'Filter rows', ariaLabel: 'Filter table rows' });
      tools.append(input);
      table.before(tools);
      const none = make('tr', { className: 'empty-row', hidden: true });
      none.innerHTML = `<td colspan="${head.cells.length}">No rows match.</td>`;
      body.append(none);
      input.addEventListener('input', () => {
        const q = input.value.trim().toLowerCase();
        let shown = 0;
        rows.forEach((r) => { const found = r.textContent!.toLowerCase().includes(q); r.hidden = !found; shown += found ? 1 : 0; });
        none.hidden = shown > 0;
      });
    }
    [...head.cells].forEach((th, i) => {
      th.setAttribute('aria-sort', 'none');
      th.tabIndex = 0;
      const sort = () => {
        const dir = th.getAttribute('aria-sort') === 'ascending' ? -1 : 1;
        $$('th', head).forEach((o) => o.setAttribute('aria-sort', 'none'));
        th.setAttribute('aria-sort', dir === 1 ? 'ascending' : 'descending');
        const val = (r: HTMLTableRowElement) => r.cells[i].textContent!.trim();
        rows.sort((a, b) => dir * val(a).localeCompare(val(b), undefined, { numeric: true }))
          .forEach((r) => body.insertBefore(r, $('.empty-row', body)));
      };
      th.addEventListener('click', sort);
      th.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); sort(); } });
    });
  });

  // Scores count up once
  if (!calm) $$('.score').forEach((el) => {
    const m = el.textContent!.match(/^(\d+)\/(\d+)$/);
    if (!m) return;
    const end = +m[1], t0 = performance.now(), dur = 900;
    const tick = (t: number) => {
      const k = Math.min((t - t0) / dur, 1);
      el.textContent = `${Math.round(end * (1 - Math.pow(1 - k, 3)))}/${m[2]}`;
      if (k < 1) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  });

  // Back/forward cache can restore a page mid-spinner
  addEventListener('pageshow', () => $$('.is-loading').forEach((b) => b.classList.remove('is-loading')));

  // Submit feedback: spinner in the button while the server works
  $$<HTMLFormElement>('form').forEach((f) => f.addEventListener('submit', () => {
    const b = $('button.btn[type="submit"]', f);
    if (b) { b.classList.add('is-loading'); b.setAttribute('aria-busy', 'true'); }
  }));
  // Demo buttons: any element with data-toast shows a toast (nothing is sent anywhere)
  document.addEventListener('click', (e) => {
    const b = hit(e, '[data-toast]');
    if (b) toast(b.dataset.toast ?? '');
  });

  // Page transition: a sheet in the destination workspace's colour sweeps up, and the new page sweeps it away.
  // The colour comes from the link's p-* class (nav items and home cards carry one).
  const ICONS: Record<string, string> = {
    '/client': 'M5 4h4l2 5-2.5 1.5a11 11 0 005 5L15 13l5 2v4a2 2 0 01-2 2A16 16 0 013 6a2 2 0 012-2z',
    '/advisor': 'M4 14v-2a8 8 0 0116 0v2M4 14h3v5H5a1 1 0 01-1-1v-4zm16 0h-3v5h2a1 1 0 001-1v-4zM17 19c0 1.7-2 2.5-5 2.5',
    '/workforce': 'M4 20v-7m5 7V4m5 16v-9m5 9v-5',
    '/quality': 'M12 3l2.6 5.3 5.9.9-4.3 4.1 1 5.8L12 16.3 6.8 19.1l1-5.8L3.5 9.2l5.9-.9L12 3z',
    '/complaints': 'M12 4l9 16H3L12 4zm0 6v4m0 3v.01',
    '/training': 'M3 9l9-5 9 5-9 5-9-5zm4 3v4c0 1.5 2.2 3 5 3s5-1.5 5-3v-4',
    '/sales': 'M20 12l-8 8-9-9V4h7l10 8zM7.5 7.5h.01',
    '/personas': 'M16 19v-1a4 4 0 00-4-4H8a4 4 0 00-4 4v1M10 11a3 3 0 100-6 3 3 0 000 6zm9 8v-1a3 3 0 00-2-2.8M15 5.2a3 3 0 010 5.6',
    '/ideas': 'M9 18h6m-5 3h4M12 3a6 6 0 00-3.5 10.9V16h7v-2.1A6 6 0 0012 3z',
    '/pipeline': 'M6 6a2 2 0 100 .01M6 8v8m0 0a2 2 0 100 .01M18 12a2 2 0 100 .01M6 12h4a4 4 0 004-4V6',
    '/present': 'M4 5h16v11H4zM9 21h6m-3-5v5M10 8.5v4l4-2z',
  };
  if (!calm) {
    const personaOf = (a: Element) => [...(a.closest('[class*="p-"]')?.classList ?? [])].find((c) => /^p-/.test(c));
    document.addEventListener('click', (e) => {
      const a = hit<HTMLAnchorElement>(e, 'a[href]');
      if (!a || e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      if (a.target || a.hasAttribute('download')) return;
      const url = new URL(a.href, location.href);
      if (url.origin !== location.origin || url.pathname === location.pathname) return;
      e.preventDefault();
      const sheet = document.body.appendChild(make('div', { className: 'wipe' }));
      const p = personaOf(a);
      if (p) sheet.classList.add(p);
      const d = ICONS[url.pathname];
      if (d) {
        const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        svg.setAttribute('viewBox', '0 0 24 24'); svg.setAttribute('aria-hidden', 'true');
        const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        path.setAttribute('d', d);
        svg.append(path);
        sheet.append(svg);
      }
      sheet.append((a.querySelector('strong') ?? a).textContent!.trim());
      requestAnimationFrame(() => requestAnimationFrame(() => sheet.classList.add('go')));
      setTimeout(() => { location.href = url.href; }, 520);
    });
    addEventListener('pageshow', (e) => { if (e.persisted) $$('.wipe').forEach((w) => w.remove()); });
  }

  // Ideas: filter by decision
  const filters = $$('[data-filter]');
  filters.forEach((btn) => btn.addEventListener('click', () => {
    filters.forEach((b) => b.setAttribute('aria-pressed', String(b === btn)));
    const f = btn.dataset.filter;
    $$('.idea').forEach((i) => { i.hidden = f !== 'all' && i.dataset.decision !== f; });
    $$('.idea-set').forEach((s) => { s.hidden = !s.querySelector('.idea:not([hidden])'); });
  }));

  // Training: scenario builder, replay and what-if (demo data; the Training agent would supply these)
  const deck = byId('scenarios');
  if (deck) {
    interface Scenario { id: string; title: string; profile: string; difficulty: string; origin: string }
    interface Variant { title: string; profile: string; difficulty: string }
    const customers: [string, string][] = [['New', 'a new subscriber'], ['Premium', 'a premium client'],
      ['Unsatisfied', 'a long-time client who is unhappy'], ['Anxious', 'an anxious first-time caller']];
    const problems = ['is charged twice on the monthly bill', 'cannot use the roaming bundle abroad', 'wants to cancel and disputes the fee',
      'sees data limits that do not match the plan', 'was transferred twice and lost the context'];
    const goals = ['wants an immediate refund', 'wants a written confirmation', 'wants a lower price on the same plan', 'asks for a supervisor'];
    const levels = ['Easy', 'Medium', 'Hard'];
    const pick = <T>(a: T[]): T => a[Math.floor(Math.random() * a.length)];
    const cap = (s: string) => s[0].toUpperCase() + s.slice(1);

    const card = (s: Scenario) => {
      const li = make('li', { className: 'scn fresh' });
      Object.assign(li.dataset, { id: s.id, title: s.title, profile: s.profile, difficulty: s.difficulty });
      const top = li.appendChild(make('div', { className: 'scn-top' }));
      top.append(make('span', { className: 'case-id', textContent: s.id }));
      const diff = top.appendChild(make('span', { className: 'diff', ariaLabel: `Difficulty ${s.difficulty}` }));
      for (let k = 0; k < 3; k++) diff.append(make('i', { className: k <= levels.indexOf(s.difficulty) ? 'on' : '' }));
      li.append(make('h3', { textContent: s.title }));
      const chips = li.appendChild(make('p', { className: 'chips' }));
      [s.profile, s.difficulty].forEach((t) => chips.append(make('span', { className: 'chip', textContent: t })));
      li.append(make('p', { className: 'origin muted small', textContent: s.origin }));
      const act = li.appendChild(make('div', { className: 'actions' }));
      const replay = make('button', { type: 'button', className: 'btn', textContent: 'Replay' });
      replay.dataset.act = 'replay';
      const whatIf = make('button', { type: 'button', className: 'btn-line', textContent: 'What-if' });
      whatIf.dataset.act = 'whatif';
      act.append(replay, whatIf);
      return li;
    };

    byId('generate')!.addEventListener('click', () => {
      const [profile, who] = pick(customers);
      const wanted = byId<HTMLSelectElement>('gen-diff')!.value;
      const n = Math.max(0, ...([...deck.children] as HTMLElement[]).map((c) => parseInt((c.dataset.id ?? '').replace(/\D/g, ''), 10) || 0)) + 1;
      const s: Scenario = { id: `SC-${n}`, profile, difficulty: wanted || pick(levels), origin: 'Template library',
        title: cap(`${who} ${pick(problems)} and ${pick(goals)}`) };
      deck.prepend(card(s));
      toast(`Generated ${s.id}`);
    });

    deck.addEventListener('click', (e) => {
      const btn = hit(e, '[data-act]');
      if (!btn) return;
      const li = btn.closest<HTMLElement>('.scn')!;
      const { id, title, profile, difficulty } = li.dataset as Record<string, string>;
      if (btn.dataset.act === 'replay') { toast(`Replaying ${id}: same client, same events`); return; }

      // what-if: change exactly one parameter, then compare
      const kind = pick(['difficulty', 'profile', 'event']);
      const after: Variant = { title, profile, difficulty };
      let note: string;
      if (kind === 'difficulty') {
        const i = levels.indexOf(difficulty);
        after.difficulty = levels[i === 2 ? 1 : i + 1];
        note = `Difficulty ${difficulty} to ${after.difficulty}. Same client and problem, so any change in handling is down to the pressure.`;
      } else if (kind === 'profile') {
        after.profile = pick(customers.map((c) => c[0]).filter((p) => p !== profile));
        note = `Client profile ${profile} to ${after.profile}. Same problem, a different personality.`;
      } else {
        after.title = `${title} The client is calling for the third time.`;
        note = 'Added one event: a repeat contact. Compare how memory changes the call.';
      }
      const show = (box: HTMLElement, v: Variant, changed: string | null) => {
        box.replaceChildren();
        box.append(`${v.title} `);
        [['profile', v.profile], ['difficulty', v.difficulty]].forEach(([k, val], idx) => {
          if (idx) box.append(' · ');
          const el = changed === k ? document.createElement('mark') : document.createElement('span');
          el.textContent = `${k}: ${val}`; box.append(el);
        });
      };
      show(byId('wi-before')!, { title, profile, difficulty }, null);
      show(byId('wi-after')!, after, kind);
      byId('wi-note')!.textContent = note;
      const panel = byId('whatif')!;
      panel.hidden = false;
      panel.scrollIntoView({ behavior: calm ? 'auto' : 'smooth', block: 'nearest' });
    });
  }

  // Workforce: scrub through the day. Moves a marker on the chart and highlights the hour in the heat strip.
  // Wait and SLA are estimates from the mock model (240 s and 71% at the 72 calls/h peak).
  const scrub = byId<HTMLInputElement>('hour');
  if (scrub) {
    const cells = $$('.heat li');
    const marker = byId('marker') as unknown as SVGElement | null;
    const read = byId('scrub-read')!;
    const peak = cells.reduce((best, c, i) => (+c.dataset.forecast! > +cells[best].dataset.forecast! ? i : best), 0);
    const show = () => {
      const c = cells[+scrub.value];
      cells.forEach((x) => x.classList.toggle('on', x === c));
      marker?.setAttribute('x1', c.dataset.x ?? ''); marker?.setAttribute('x2', c.dataset.x ?? '');
      const f = +c.dataset.forecast!, wait = Math.round(f * 3.3), sla = Math.max(40, Math.round(100 - f * 0.4));
      const load = f >= 60 ? 'overloaded' : f >= 40 ? 'busy' : 'calm';
      const actual = c.dataset.actual ? `, actual ${c.dataset.actual}` : '';
      read.textContent = `${c.dataset.hour}: forecast ${f} calls/h${actual} · est. wait ${Math.floor(wait / 60)} min ${wait % 60} s · est. SLA ${sla}% · ${load}`;
    };
    scrub.value = String(peak);
    scrub.addEventListener('input', show);
    show();
  }

  // Quality: pins on the call timeline reveal the evidence and highlight the criterion row
  $$('.review').forEach((review) => {
    const read = $('.pin-read', review)!;
    const pins = $$<SVGElement>('.pin', review);
    const rows = $$<HTMLTableRowElement>('tbody tr', review);
    const pick = (pin: SVGElement) => {
      pins.forEach((p) => p.classList.toggle('active', p === pin));
      rows.forEach((r) => r.classList.toggle('hl', r.dataset.index === pin.dataset.index));
      const row = rows.find((r) => r.dataset.index === pin.dataset.index)!;
      const cell = (i: number) => row.cells[i].textContent!.trim();
      read.textContent = `${cell(3)} · ${cell(0)}, ${cell(1)}: ${cell(2)}`;
    };
    pins.forEach((p) => {
      p.addEventListener('click', () => pick(p));
      p.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); pick(p); } });
    });
    const radius = (p: SVGElement) => +($('circle', p)?.getAttribute('r') ?? 0);
    const worst = pins.reduce<SVGElement | null>((w, p) => (w && radius(w) >= radius(p) ? w : p), null);
    if (worst) pick(worst);
  });

  // Command palette (Ctrl/Cmd+K): jump to any page the user can open
  const links = $$<HTMLAnchorElement>('.sidebar a.nav, .sidebar a.brand');
  if (links.length) {
    const dlg = document.body.appendChild(make('dialog', { className: 'palette', ariaLabel: 'Jump to a page' }));
    const input = dlg.appendChild(make('input', { type: 'search', placeholder: 'Jump to a page', ariaLabel: 'Search pages' }));
    const list = dlg.appendChild(document.createElement('ul'));
    let sel = 0, shown: HTMLAnchorElement[] = [];
    const render = () => {
      const q = input.value.trim().toLowerCase();
      shown = links.filter((a) => a.textContent!.trim().toLowerCase().includes(q));
      sel = Math.min(sel, Math.max(0, shown.length - 1));
      list.replaceChildren(...(shown.length ? shown.map((a, i) => {
        const li = document.createElement('li');
        li.setAttribute('aria-selected', String(i === sel));
        const row = make('a', { href: a.href, textContent: a.textContent!.trim() });
        const persona = [...a.classList].find((c) => /^p-/.test(c));
        if (persona) row.classList.add(persona);
        row.addEventListener('click', (e) => { e.preventDefault(); dlg.close(); a.click(); });
        li.append(row); return li;
      }) : [make('li', { className: 'empty', textContent: 'No page matches.' })]));
    };
    const open = () => { input.value = ''; sel = 0; render(); dlg.showModal(); input.focus(); };
    $('.palette-open')?.addEventListener('click', open);
    addEventListener('keydown', (e) => { if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); if (dlg.open) dlg.close(); else open(); } });
    input.addEventListener('input', () => { sel = 0; render(); });
    input.addEventListener('keydown', (e) => {
      if (e.key === 'ArrowDown') { e.preventDefault(); sel = Math.min(sel + 1, shown.length - 1); render(); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); sel = Math.max(sel - 1, 0); render(); }
      else if (e.key === 'Enter' && shown[sel]) { e.preventDefault(); dlg.close(); shown[sel].click(); }
    });
    dlg.addEventListener('click', (e) => { if (e.target === dlg) dlg.close(); });
  }

  // Presentation mode: one slide at a time, arrow keys, hash links, full screen
  const stage = byId('stage');
  if (stage) {
    document.documentElement.classList.add('slides');
    const slides = $$('.slide', stage);
    const bar = byId<HTMLProgressElement>('pprog')!, count = byId('pcount')!;
    let at = Math.min(Math.max((parseInt(location.hash.slice(1), 10) || 1) - 1, 0), slides.length - 1);
    const go = (n: number) => {
      at = Math.min(Math.max(n, 0), slides.length - 1);
      slides.forEach((s, i) => { s.classList.toggle('on', i === at); s.classList.toggle('past', i < at); });
      bar.value = slides.length > 1 ? at / (slides.length - 1) : 1;
      count.textContent = `${at + 1} / ${slides.length}`;
      history.replaceState(null, '', `#${at + 1}`);
    };
    addEventListener('keydown', (e) => {
      if (['ArrowRight', 'PageDown', ' '].includes(e.key)) { e.preventDefault(); go(at + 1); }
      else if (['ArrowLeft', 'PageUp'].includes(e.key)) { e.preventDefault(); go(at - 1); }
      else if (e.key === 'Home') go(0);
      else if (e.key === 'End') go(slides.length - 1);
      else if (e.key.toLowerCase() === 'f') byId('pfs')!.click();
    });
    stage.addEventListener('click', (e) => { if (!hit(e, 'a, button')) go(at + 1); });
    byId('pfs')!.addEventListener('click', () => {
      if (document.fullscreenElement) document.exitFullscreen(); else document.documentElement.requestFullscreen?.();
    });
    go(at);
  }

  // Rail: icons only by default; the menu button expands it to show names (remembered per browser)
  const rail = $('.nav-toggle');
  if (rail) {
    const root = document.documentElement;
    const label = $('.nav-label', rail)!;
    const apply = (open: boolean) => {
      root.classList.toggle('nav-open', open);
      rail.setAttribute('aria-expanded', String(open));
      rail.setAttribute('aria-label', open ? 'Hide names' : 'Show names');
      label.textContent = open ? 'Hide names' : 'Show names';
    };
    apply(store.get('cv-nav') === 'open');
    rail.addEventListener('click', () => {
      const open = !root.classList.contains('nav-open');
      apply(open);
      store.set('cv-nav', open ? 'open' : 'closed');
    });
  }

  // Save as PDF: the print stylesheet lays slides and pages out for paper
  document.addEventListener('click', (e) => { if (hit(e, '[data-print]')) print(); });

  // Dark mode: follows the system until the user picks, then remembers the choice
  const themeBtn = $('.theme-toggle');
  const setTheme = (t: string) => {
    document.documentElement.dataset.theme = t;
    if (themeBtn) {
      themeBtn.setAttribute('aria-label', t === 'dark' ? 'Switch to light mode' : 'Switch to dark mode');
      $('.nav-label', themeBtn)!.textContent = t === 'dark' ? 'Light mode' : 'Dark mode';
    }
  };
  setTheme(store.get('cv-theme') ?? (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'));
  themeBtn?.addEventListener('click', () => {
    const t = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
    setTheme(t); store.set('cv-theme', t);
  });

  // Simulator: remember the last five finished calls in this browser
  interface Call { key: string; persona: string; difficulty: string; verdict: string; churn: number; met: boolean }
  const outcome = $('.outcome[data-key]');
  const histBox = byId('history');
  if (histBox) {
    const read = (): Call[] => { try { return JSON.parse(store.get('cv-calls') ?? '[]'); } catch { return []; } };
    let calls = read();
    if (outcome && !calls.some((c) => c.key === outcome.dataset.key)) {
      const d = outcome.dataset as Record<string, string>;
      calls = [{ key: d.key, persona: d.persona, difficulty: d.difficulty, verdict: d.verdict, churn: +d.churn, met: d.met === 'true' }, ...calls].slice(0, 5);
      store.set('cv-calls', JSON.stringify(calls));
    }
    const draw = () => {
      histBox.hidden = calls.length === 0;
      byId('history-list')!.replaceChildren(...calls.map((c) => {
        const li = document.createElement('li');
        if (!c.met) li.className = 'bad';
        li.append(make('i', { className: 'dot' }));
        const mid = document.createElement('div');
        mid.append(make('strong', { textContent: `${c.persona} · ${c.difficulty}` }), make('span', { className: 'muted', textContent: c.verdict }));
        li.append(mid, make('span', { className: 'churn', textContent: `${c.churn}% churn` }));
        return li;
      }));
    };
    byId('history-clear')!.addEventListener('click', () => { calls = []; store.set('cv-calls', '[]'); draw(); toast('History cleared'); });
    draw();
  }

  // Complaints: drag a card to another lane, or press Escalate to move it up one
  const lanes = $$('.lane[data-lane]');
  if (lanes.length) {
    const order = lanes.map((l) => l.dataset.lane);
    const refresh = () => {
      lanes.forEach((l) => {
        const n = $$('.case', l).length;
        $('.count', l)!.textContent = String(n);
        const empty = $('.lane-empty', l) ?? l.insertBefore(make('p', { className: 'lane-empty muted', textContent: 'Nothing here.' }), $('.case', l));
        empty.hidden = n > 0;
      });
      const crit = $('.stat.prod strong');
      if (crit) crit.textContent = String($$('.case', $('.lane[data-lane="critical"]')!).length);
    };
    const move = (card: HTMLElement, lane: HTMLElement, how: string) => {
      if (card.closest('.lane') === lane) return;
      lane.append(card); card.classList.add('landed'); setTimeout(() => card.classList.remove('landed'), 700);
      refresh();
      toast(`${card.dataset.id} ${how} ${lane.dataset.lane} (demo, not saved)`);
    };
    let dragged: HTMLElement | null = null;
    document.addEventListener('dragstart', (e) => {
      const c = hit(e, '.case');
      if (c && e.dataTransfer) { dragged = c; c.classList.add('dragging'); e.dataTransfer.effectAllowed = 'move'; e.dataTransfer.setData('text/plain', c.dataset.id ?? ''); }
    });
    document.addEventListener('dragend', () => { dragged?.classList.remove('dragging'); dragged = null; lanes.forEach((l) => l.classList.remove('over')); });
    lanes.forEach((l) => {
      l.addEventListener('dragover', (e) => { if (dragged) { e.preventDefault(); l.classList.add('over'); } });
      l.addEventListener('dragleave', (e) => { if (!l.contains(e.relatedTarget as Node | null)) l.classList.remove('over'); });
      l.addEventListener('drop', (e) => { e.preventDefault(); l.classList.remove('over'); if (dragged) move(dragged, l, 'moved to'); });
    });
    document.addEventListener('click', (e) => {
      const b = hit(e, '[data-escalate]');
      if (!b) return;
      const card = b.closest<HTMLElement>('.case')!, i = order.indexOf(card.closest<HTMLElement>('.lane')!.dataset.lane);
      if (i === 0) toast(`${card.dataset.id} is already critical`);
      else move(card, lanes[i - 1], 'escalated to');
    });
    refresh();
  }

  // Presentation: speaker notes (N)
  const notesBox = byId('notes');
  if (notesBox) {
    const btn = byId('pnotes')!;
    const show = () => { notesBox.textContent = $('.slide.on')?.dataset.notes ?? 'No notes for this slide.'; };
    const flip = () => { notesBox.hidden = !notesBox.hidden; btn.setAttribute('aria-pressed', String(!notesBox.hidden)); show(); };
    btn.addEventListener('click', flip);
    addEventListener('keydown', (e) => { if (e.key.toLowerCase() === 'n' && !e.ctrlKey && !e.metaKey) flip(); });
    new MutationObserver(show).observe(byId('stage')!, { subtree: true, attributes: true, attributeFilter: ['class'] });
  }

  // Demo tour: one customer story across the workspaces. The step is kept in sessionStorage.
  const STEPS: [path: string, title: string, text: string][] = [
    ['/', 'Welcome', 'CallVerse is a digital twin of a contact center: seven personas, seven agents. This tour follows one customer story, page by page.'],
    ['/client', 'Yasmine calls', 'Play the advisor. Pick replies and watch her mood and patience move. Try asking her to repeat herself and see the call go wrong.'],
    ['/advisor', 'Karim finds the answer', 'One screen: the customer 360° and a sourced answer. No more five open tabs.'],
    ['/workforce', 'Sana sees the spike coming', 'Drag the slider to scrub through the day, then run the what-if to test a fix before applying it.'],
    ['/quality', 'Nour scores every call', 'Every call is scored. Click a pin on the timeline to see the exact moment points were lost.'],
    ['/training', 'Rim trains from the gaps', 'Generate a scenario, then try What-if to change one parameter and compare.'],
    ['/complaints', 'Amine catches the critical case', 'The early warning flags the riskiest case. Drag a card to another lane, or press Escalate.'],
    ['/sales', 'Leila gets a fitting offer', 'Offers tied to what the client just said, each with a relevance score.'],
    ['/ideas', 'Every idea, rated', 'All 28 ideas with tech, data and impact ratings, and what the app already lets you try.'],
    ['/present', 'Present it', 'Presentation mode: arrow keys to move, N for speaker notes, F for full screen.'],
  ];
  // Click the page's real sidebar link so the transition sheet gets its name and colour
  const go = (path: string) => {
    const real = $(`.sidebar a[href="${path}"]`);
    if (real) { real.click(); return; }
    const a = document.body.appendChild(make('a', { href: path }));
    a.click(); a.remove();
  };
  const tourAt = () => { const v = store.sget('cv-tour'); return v === null ? -1 : +v; };
  const endTour = (msg?: string) => { store.sdel('cv-tour'); $('.tour')?.remove(); if (msg) toast(msg); };
  const drawTour = () => {
    $('.tour')?.remove();
    const i = tourAt();
    if (i < 0 || i >= STEPS.length) return;
    const [path, title, text] = STEPS[i];
    if (i === STEPS.length - 1 && location.pathname === path) { endTour('Tour complete. Use the arrow keys to present.'); return; }
    const card = document.body.appendChild(make('aside', { className: 'tour', role: 'dialog', ariaLabel: 'Demo tour' }));
    const top = card.appendChild(make('div', { className: 'tour-top' }));
    const dots = top.appendChild(make('div', { className: 'tour-dots' }));
    STEPS.forEach((_, k) => dots.append(make('i', { className: k < i ? 'done' : k === i ? 'now' : '' })));
    top.append(make('span', { className: 'tour-step', textContent: `Step ${i + 1} of ${STEPS.length}` }));
    card.append(make('h2', { textContent: title }));
    const here = location.pathname === path;
    card.append(make('p', { textContent: here ? text : 'You left the tour path. Jump back to carry on.' }));
    const act = card.appendChild(make('div', { className: 'tour-actions' }));
    const mk = (cls: string, label: string, fn: () => void) => act.append(make('button', { type: 'button', className: cls, textContent: label, onclick: fn }));
    if (i > 0) mk('btn-quiet', 'Back', () => { store.sset('cv-tour', String(i - 1)); go(STEPS[i - 1][0]); });
    act.append(make('span', { className: 'grow' }));
    mk('btn-quiet', 'End tour', () => endTour());
    if (here) mk('btn', 'Next', () => { store.sset('cv-tour', String(i + 1)); go(STEPS[i + 1][0]); });
    else mk('btn', 'Go to this step', () => go(path));
  };
  document.addEventListener('click', (e) => {
    if (!hit(e, '[data-tour="start"]')) return;
    store.sset('cv-tour', '0'); drawTour();
  });
  drawTour();
})();
