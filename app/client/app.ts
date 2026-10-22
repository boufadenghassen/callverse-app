/* orqestra browser script (TypeScript, compiled to public/js/app.js by `npm run build`).
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

  // Voice: agents read their answers out loud. The neural voice of the Python agents is tried first (a voice per persona,
  // faster when the customer is upset); when it is not available the browser's own speech takes over. Text is read sentence
  // by sentence so the first words start early. `speak(text, role, mood, persona)` stops whatever was being said.
  const synth = 'speechSynthesis' in window ? window.speechSynthesis : null;
  const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') ?? '';
  let neural = true;                         // set to false once the server says it has no neural voice
  let player: HTMLAudioElement | null = null;
  let turn = 0;                              // each speak() takes a new number, so older playback stops itself
  let speaking: HTMLElement | null = null;   // the Listen button whose text is being read
  const stopSpeaking = () => {
    turn++; synth?.cancel(); player?.pause(); player = null;
    if (speaking) { speaking.classList.remove('speaking'); speaking.textContent = 'Listen'; }
    speaking = null;
  };
  const sentences = (t: string) => (t.match(/[^.!?]+[.!?]*/g) ?? [t]).map((s) => s.trim()).filter(Boolean);
  const neuralClip = async (text: string, role: string, mood: number, persona: string | null): Promise<string | null> => {
    try {
      const res = await fetch('/voice/speak', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken }, body: JSON.stringify({ text, role, mood, persona }) });
      if (res.status === 503) neural = false;
      return res.ok ? URL.createObjectURL(await res.blob()) : null;
    } catch { return null; }
  };
  const browserSpeak = (text: string, role: string, mood: number, mine: number) => new Promise<void>((done) => {
    if (!synth || mine !== turn) return done();
    const en = synth.getVoices().filter((v) => /^en/i.test(v.lang));
    const female = /(aria|jenny|zira|samantha|female|susan|hazel)/i, male = /(guy|davis|david|mark|male|ryan|george)/i;
    const shift = (50 - Math.max(0, Math.min(100, mood))) / 250;
    const u = new SpeechSynthesisUtterance(text);
    u.lang = 'en-US'; u.rate = 1 + shift; u.pitch = 1 + shift;
    u.voice = en.find((v) => (role === 'customer' ? female : male).test(v.name)) ?? (en.length ? en[role === 'customer' ? 0 : en.length - 1] : null);
    u.onend = u.onerror = () => done();
    synth.speak(u);
  });
  const speak = async (text: string, role: 'advisor' | 'customer' = 'advisor', mood = 50, persona: string | null = null, onEnd?: () => void) => {
    if (!text) return;
    stopSpeaking();
    const mine = turn;
    if (neural) {
      // fetch the sentences one after the other in the background while the earlier ones play
      let chain: Promise<unknown> = Promise.resolve();
      const clips = sentences(text).map((s) => { const p = chain.then(() => neuralClip(s, role, mood, persona)) as Promise<string | null>; chain = p; return { s, p }; });
      for (const [i, { s, p }] of clips.entries()) {
        const url = await p;
        if (mine !== turn) return;
        if (!url && !neural) { await browserSpeak(clips.slice(i).map((c) => c.s).join(' '), role, mood, mine); break; }   // no neural voice: the browser reads the rest
        if (!url) { await browserSpeak(s, role, mood, mine); continue; }
        const a = player = new Audio(url);
        await new Promise<void>((done) => { a.onended = a.onerror = () => done(); a.play().catch(() => done()); });
        URL.revokeObjectURL(url);
        if (mine !== turn) return;
      }
    } else {
      await browserSpeak(text, role, mood, mine);
    }
    if (mine === turn) onEnd?.();
  };
  // every element marked data-speak gets a Listen button next to it
  $$('[data-speak]').forEach((el) => {
    const btn = make('button', { type: 'button', className: 'btn-quiet listen', textContent: 'Listen' });
    btn.addEventListener('click', () => {
      if (speaking === btn) return stopSpeaking();
      stopSpeaking();
      speaking = btn; btn.classList.add('speaking'); btn.textContent = 'Stop';
      const words = [...el.childNodes].filter((n) => n !== btn).map((n) => n.textContent).join('');
      void speak(words, 'advisor', 50, null, () => { if (speaking === btn) stopSpeaking(); });
    });
    if (el.tagName === 'LI') el.append(btn); else el.after(btn);   // a button cannot sit directly inside a list
  });
  addEventListener('pagehide', stopSpeaking);

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

  // Scroll reveal: panels and cards below the fold fade up as they come into view, a few milliseconds apart.
  // Everything stays visible without JavaScript or when the system asks for reduced motion.
  if (!calm && 'IntersectionObserver' in window) {
    const SEL = '.panel, .ws, .stat, .persona, .idea, .opp, .scn, .case, .quad, .lane';
    const below = $$(SEL).filter((el) => !el.parentElement?.closest(SEL) && el.getBoundingClientRect().top > innerHeight * 0.92);
    below.forEach((el) => el.classList.add('pre'));
    const seen = new IntersectionObserver((entries) => {
      entries.filter((e) => e.isIntersecting).forEach((e, i) => {
        const el = e.target as HTMLElement;
        el.style.transitionDelay = `${Math.min(i, 5) * 70}ms`;
        el.classList.add('in');
        seen.unobserve(el);
        setTimeout(() => { el.classList.add('seen'); el.classList.remove('pre', 'in'); el.style.transitionDelay = ''; }, 1400 + i * 70);   // back to normal hover behaviour (and no replay of the entrance animation)
      });
    }, { rootMargin: '0px 0px -6% 0px', threshold: 0.04 });
    below.forEach((el) => seen.observe(el));
  }

  // Numbers in the summary tiles count up once, when they are first seen.
  if (!calm && 'IntersectionObserver' in window) {
    const counter = new IntersectionObserver((entries) => entries.forEach((e) => {
      if (!e.isIntersecting) return;
      counter.unobserve(e.target);
      const node = e.target.firstChild;
      const m = node?.nodeType === Node.TEXT_NODE ? /^(\d+(?:\.\d+)?)([^]*)$/.exec(node.nodeValue ?? '') : null;
      if (!node || !m) return;
      const end = +m[1], decimals = (m[1].split('.')[1] ?? '').length, t0 = performance.now();
      const tick = (t: number) => {
        const k = Math.min((t - t0) / 900, 1);
        node.nodeValue = `${(end * (1 - Math.pow(1 - k, 3))).toFixed(decimals)}${m[2]}`;
        if (k < 1) requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
    }), { threshold: 0.6 });
    $$('.stat strong').forEach((el) => counter.observe(el));
  }

  // Back/forward cache can restore a page mid-spinner
  addEventListener('pageshow', () => $$('.is-loading').forEach((b) => b.classList.remove('is-loading')));

  // Submit feedback: spinner in the button while the server works
  $$<HTMLFormElement>('form').forEach((f) => f.addEventListener('submit', (e) => {
    const b = $('button.btn[type="submit"]', f);
    if (!b) return;
    b.classList.add('is-loading'); b.setAttribute('aria-busy', 'true');
    // forms handled by script (fetch) call preventDefault later: no page change is coming, so stop the spinner
    setTimeout(() => { if (e.defaultPrevented) { b.classList.remove('is-loading'); b.removeAttribute('aria-busy'); } });
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
    '/call-review': 'M12 3a3 3 0 00-3 3v6a3 3 0 006 0V6a3 3 0 00-3-3zM6 11a6 6 0 0012 0M12 17v4',
    '/complaints': 'M12 4l9 16H3L12 4zm0 6v4m0 3v.01',
    '/training': 'M3 9l9-5 9 5-9 5-9-5zm4 3v4c0 1.5 2.2 3 5 3s5-1.5 5-3v-4',
    '/sales': 'M20 12l-8 8-9-9V4h7l10 8zM7.5 7.5h.01',
    '/personas': 'M16 19v-1a4 4 0 00-4-4H8a4 4 0 00-4 4v1M10 11a3 3 0 100-6 3 3 0 000 6zm9 8v-1a3 3 0 00-2-2.8M15 5.2a3 3 0 010 5.6',
    '/ideas': 'M9 18h6m-5 3h4M12 3a6 6 0 00-3.5 10.9V16h7v-2.1A6 6 0 0012 3z',
    '/insights': 'M12 3a9 9 0 109 9h-9V3zm3 .5A9 9 0 0120.5 9H15V3.5z',
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

  // Call review: send the recording to the emotion model and draw the answer
  const reviewForm = byId<HTMLFormElement>('review-form');
  if (reviewForm) {
    const file = byId<HTMLInputElement>('audio')!, player = byId<HTMLAudioElement>('player')!, status = byId('review-status')!, out = byId('review-result')!;
    file.addEventListener('change', () => {
      const f = file.files?.[0];
      player.hidden = !f;
      if (f) player.src = URL.createObjectURL(f);
    });
    reviewForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const f = file.files?.[0];
      if (!f) return;
      status.textContent = 'Listening… the first run can take a few seconds.';
      out.hidden = true;
      try {
        const res = await fetch('/call-review/analyze', { method: 'POST', body: f, headers: { 'Content-Type': 'application/octet-stream', 'X-CSRF-Token': reviewForm.dataset.csrf! } });
        const d = await res.json();
        if (!res.ok) { status.textContent = d.error ?? 'Something went wrong.'; return; }
        status.textContent = '';
        byId('r-emotion')!.textContent = d.emotion;
        byId('r-detail')!.textContent = `mood ${d.mood}/100 · ${d.durationSec}s of speech`;
        byId('r-timeline')!.replaceChildren(...d.timeline.map((t: { startSec: number; emotion: string }) =>
          make('li', { textContent: `${t.startSec}s ${t.emotion}`, className: ['anger', 'disgust', 'fear', 'sad'].includes(t.emotion) ? 'bad' : '' })));
        // why: which blocks of the recording the model leaned on (occlusion, see models/src/explain.py)
        const why = d.explanation as { target: string; blockSec: number; blocks: { startSec: number; endSec: number; drop: number; rel: number }[]; top: { startSec: number; endSec: number; drop: number }[] } | null;
        byId('r-why-box')!.hidden = !why;
        if (why) {
          byId('r-why-lead')!.textContent = `Each block is ${why.blockSec} s of the recording. The darker the block, the more it mattered to the answer “${why.target}”.`;
          byId('r-why')!.replaceChildren(...why.blocks.map((b) => {
            const li = make('li', { className: b.drop > 0 ? 'for' : b.drop < 0 ? 'against' : '' }), bar = make('span', { className: 'bar' });
            bar.style.opacity = String(0.25 + 0.75 * Math.abs(b.rel));
            li.setAttribute('aria-label', `${b.startSec} to ${b.endSec} s: ${b.drop > 0 ? 'supports' : b.drop < 0 ? 'argues against' : 'no effect on'} ${why.target}`);
            li.append(bar);
            return li;
          }));
          byId('r-why-end')!.textContent = `${d.durationSec} s`;
          byId('r-why-top')!.textContent = why.top.length
            ? `Most influential: ${why.top.map((t) => `${t.startSec} to ${t.endSec} s`).join(', ')}.`
            : 'No single part of the recording stands out.';
        }
        out.hidden = false;
      } catch { status.textContent = 'The app could not be reached. Try again.'; }
    });
  }

  // The reasons of a score, one line each with its points (sales offers and churn risk)
  interface Factor { name: string; points: number; why: string }
  const sign = (n: number) => (n > 0 ? `+${n}` : n < 0 ? `−${-n}` : '0');
  const factorList = (factors: Factor[]) => {
    const ul = make('ul', { className: 'driver-list' });
    for (const f of factors) {
      const li = make('li'), body = make('span');
      body.append(make('strong', { textContent: f.name }), `: ${f.why}`);
      li.append(make('span', { className: `eff ${f.points >= 0 ? 'pos' : 'neg'}`, textContent: sign(f.points) }), body);
      ul.append(li);
    }
    return ul;
  };

  // Sales: read a conversation, and record what the customer did with an offer
  const sales = byId('sales');
  if (sales) {
    const csrf = sales.dataset.csrf!;
    const post = async (path: string, body: object) => {
      const res = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf }, body: JSON.stringify(body) });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.error ?? 'Something went wrong.');
      return data;
    };
    interface Offer {
      offerId: string; offer: string; price: string; relevance: number; timing: { cue: string; why: string }; factors: Factor[]; counterfactual: string | null; need: { key: string };
      acceptance?: { probability: number; basis: string } | null; expected?: { ifYes: number; tnd: number | null; how: string };
    }
    interface Policy { label: string; offers: number; accepted: number; declined: number; rate: number | null; revenue: number }
    sales.addEventListener('click', async (e) => {
      const s = hit<HTMLButtonElement>(e, '[data-sample]');
      if (s) {
        byId<HTMLTextAreaElement>('sales-text')!.value = s.dataset.sample!;
        byId<HTMLSelectElement>('sales-customer')!.value = s.dataset.sampleCustomer ?? '';
        return;
      }
      const b = hit<HTMLButtonElement>(e, '[data-outcome]');
      if (!b) return;
      const group = b.parentElement!.querySelectorAll<HTMLButtonElement>('[data-outcome]');
      group.forEach((x) => { x.disabled = true; });
      try {
        await post('/sales/outcome', { customerId: b.dataset.customer || null, offerId: b.dataset.offer, outcome: b.dataset.outcome, relevance: Number(b.dataset.relevance), cue: b.dataset.cue, need: b.dataset.need ?? '' });
        toast(`Recorded: ${b.dataset.outcome}. It counts in the track record.`);
      } catch (err) { group.forEach((x) => { x.disabled = false; }); toast((err as Error).message); }
    });
    byId<HTMLFormElement>('sales-form')?.addEventListener('submit', async (e) => {
      e.preventDefault();
      const status = byId('sales-status')!, out = byId('sales-result')!, customer = byId<HTMLSelectElement>('sales-customer')!.value;
      const turns = byId<HTMLTextAreaElement>('sales-text')!.value.split('\n').map((l) => l.trim()).filter(Boolean).map((l) => {
        const m = /^([CA])\s*:\s*(.*)$/i.exec(l);
        return { speaker: m && m[1].toUpperCase() === 'A' ? 'advisor' : 'customer', text: m ? m[2] : l };
      }).filter((t) => t.text);
      status.textContent = 'Reading the conversation…';
      out.hidden = true;
      try {
        const d = await post('/sales/detect', { customerId: customer || null, turns });
        status.textContent = '';
        const churn = d.churn as { score: number; level: string; factors: Factor[] } | undefined;
        byId('sales-churn-box')!.hidden = !churn;
        if (churn) {
          byId('sales-churn')!.textContent = `Risk of losing this customer: ${churn.score} · ${churn.level}`;
          byId('sales-churn-factors')!.replaceChildren(...[...factorList(churn.factors).children]);
        }
        const signals = d.signals as { label: string; quote: string; time: string | null; mentions: number; strength: number; source: string }[];
        byId('sales-signals')!.replaceChildren(...(signals.length ? signals : [null]).map((s) => {
          const li = make('li'), body = make('span');
          if (!s) { body.textContent = 'No need found in this conversation.'; li.append(make('span', { className: 'eff', textContent: '–' }), body); return li; }
          body.append(make('strong', { textContent: s.label }), s.source === 'conversation' ? `: “${s.quote}”${s.time ? ` at ${s.time}` : ''}${s.mentions > 1 ? `, said in ${s.mentions} replies` : ''}` : `: ${s.quote} (from the file)`);
          li.append(make('span', { className: 'eff pos', textContent: `${Math.round(s.strength * 100)}%` }), body);
          return li;
        }));
        byId('sales-offers')!.replaceChildren(...(d.offers as Offer[]).map((o) => {
          const li = make('li'), wait = o.timing.cue === 'after_resolution';
          li.append(make('h4', { textContent: `${o.offer}: ${o.relevance}/100` }), make('p', { className: `timing ${wait ? 'wait' : 'go'}`, textContent: `${wait ? 'Wait: solve the problem first' : 'Good moment to offer'}. ${o.timing.why}` }));
          if (o.acceptance && o.expected) {
            li.append(make('p', { className: 'figures', textContent: `Chance of a yes ${Math.round(o.acceptance.probability * 100)}% · worth ${o.expected.ifYes} TND over 12 months if yes · expected ${o.expected.tnd} TND` }));
          }
          li.append(factorList(o.factors));
          if (o.acceptance && o.expected) li.append(make('p', { className: 'muted small', textContent: `Chance of a yes: ${o.acceptance.basis}. Worth: ${o.expected.how}.` }));
          if (o.counterfactual) li.append(make('p', { className: 'muted small', textContent: o.counterfactual }));
          const actions = make('div', { className: 'actions' });
          for (const outcome of ['accepted', 'declined']) {
            const btn = make('button', { type: 'button', className: outcome === 'accepted' ? 'btn' : 'btn-quiet', textContent: outcome === 'accepted' ? 'Customer accepted' : 'Declined' });
            Object.assign(btn.dataset, { outcome, customer: d.customerId ?? '', offer: o.offerId, relevance: String(o.relevance), cue: o.timing.cue, need: o.need.key });
            actions.append(btn);
          }
          li.append(actions);
          return li;
        }));
        byId('sales-skipped')!.textContent = d.skipped.length ? `Set aside: ${(d.skipped as { offer: string; why: string }[]).map((s) => `${s.offer} (${s.why})`).join('; ')}.` : '';
        if (!d.offers.length) byId('sales-offers')!.replaceChildren(make('li', { textContent: `No offer fits. The customer's mood was read as ${d.mood}/100.` }));
        out.hidden = false;
      } catch (err) { status.textContent = (err as Error).message; }
    });
    // what a selling rule would earn: send the numbers, redraw the table
    byId<HTMLFormElement>('sim-form')?.addEventListener('submit', async (e) => {
      e.preventDefault();
      const num = (id: string) => Number(byId<HTMLInputElement>(id)!.value), status = byId('sim-status')!;
      status.textContent = 'Replaying the history…';
      try {
        const d = await post('/sales/simulate', { calls: num('sim-calls'), share: num('sim-share'), minRelevance: num('sim-min'), goodMomentOnly: byId<HTMLInputElement>('sim-good')!.checked });
        const row = (p: Policy, cls = '') => {
          const tr = make('tr', cls ? { className: cls } : {});
          tr.append(make('th', { scope: 'row', textContent: p.label }), ...[p.offers, p.accepted, p.declined, p.rate === null ? '' : `${Math.round(p.rate * 100)}%`, p.revenue].map((v) => make('td', { textContent: String(v) })));
          return tr;
        };
        byId('sim-body')!.replaceChildren(...(d.policies as Policy[]).map((p) => row(p)), row(d.yours as Policy, 'yours'));
        byId('sim-caption')!.textContent = `One month: ${d.calls} calls, ${d.opportunities} with a chance to offer`;
        status.textContent = '';
      } catch (err) { status.textContent = (err as Error).message; }
    });
  }

  // Advisor live call: talk to the simulated customer, read the advisor agent's suggestion after every message
  const live = byId('live');
  if (live) {
    const csrf = live.dataset.csrf!, sel = (id: string) => byId<HTMLSelectElement>(id)!.value;
    const status = byId('live-status')!, call = byId('live-call')!, log = byId('live-log')!, text = byId<HTMLTextAreaElement>('lv-text')!;
    const useBtn = byId<HTMLButtonElement>('lv-use')!, sendBtn = $<HTMLButtonElement>('#live-say button[type=submit]')!;
    const voiceOn = byId<HTMLInputElement>('lv-voice');
    if (voiceOn) { voiceOn.checked = store.get('cv-voice') !== 'off'; voiceOn.addEventListener('change', () => { store.set('cv-voice', voiceOn.checked ? 'on' : 'off'); if (!voiceOn.checked) stopSpeaking(); }); }
    let callId = '', topic = '', personaKey = '';
    const post = async (path: string, body: object) => {
      const res = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf }, body: JSON.stringify(body) });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.error ?? 'Something went wrong.');
      return data;
    };
    const sayMine = byId<HTMLInputElement>('lv-sayme');
    if (sayMine) { sayMine.checked = store.get('cv-sayme') !== 'off'; sayMine.addEventListener('change', () => store.set('cv-sayme', sayMine.checked ? 'on' : 'off')); }
    const recBtn = byId<HTMLButtonElement>('lv-rec');
    // voice: `after` makes the customer wait until the advisor's own voice has finished; `url` is a recorded voice note
    // the conversation as the sales agent reads it, and the offer worth keeping in mind
    let convo: { speaker: string; text: string; mood?: number }[] = [], offerSeq = 0;
    const offerBox = byId('live-offer')!;
    const showOffers = async () => {
      const mine = ++offerSeq;
      try {
        const d = await post('/advisor/live/offers', { turns: convo });
        if (mine !== offerSeq) return;
        interface Shown { offerId: string; offer: string; price: string; relevance: number; timing: { cue: string; why: string }; factors: Factor[]; need: { key: string };
          acceptance?: { probability: number; basis: string } | null; expected?: { ifYes: number; tnd: number | null; how: string } }
        const offers = d.offers as Shown[], churn = d.churn as { score: number; level: string } | undefined;
        const risk = byId('lv-o-risk')!;
        risk.hidden = !churn;
        if (churn) { risk.textContent = `Risk of losing this customer: ${churn.score} · ${churn.level}`; risk.className = `risk ${churn.level.toLowerCase()}`; }
        const heard = (d.signals as { label: string; source: string }[]).filter((s) => s.source === 'conversation').map((s) => s.label);
        byId('lv-o-heard')!.textContent = heard.length ? `Heard: ${heard.join(', ')}.` : '';
        byId('lv-o-top')!.hidden = !offers.length;
        byId('lv-o-none')!.hidden = !!offers.length;
        if (offers.length) {
          const o = offers[0], wait = o.timing.cue === 'after_resolution';
          byId('lv-o-name')!.textContent = `${o.offer} (${o.relevance}/100)${o.price ? ` · ${o.price}` : ''}`;
          const timing = byId('lv-o-timing')!;
          timing.className = `timing ${wait ? 'wait' : 'go'}`;
          timing.replaceChildren(make('strong', { textContent: wait ? 'Wait: solve the problem first.' : 'Good moment to offer.' }), ` ${o.timing.why}`);
          byId('lv-o-figures')!.textContent = o.acceptance && o.expected ? `Chance of a yes ${Math.round(o.acceptance.probability * 100)}% · worth ${o.expected.ifYes} TND over 12 months if yes · expected ${o.expected.tnd} TND` : '';
          byId('lv-o-why')!.replaceChildren(factorList(o.factors), ...(o.acceptance && o.expected ? [make('p', { className: 'muted small', textContent: `Chance of a yes: ${o.acceptance.basis}. Worth: ${o.expected.how}.` })] : []));
          const actions = byId('lv-o-actions')!;
          actions.querySelectorAll<HTMLButtonElement>('[data-outcome]').forEach((b) => {
            b.disabled = false;
            Object.assign(b.dataset, { customer: d.customerId ?? '', offer: o.offerId, relevance: String(o.relevance), cue: o.timing.cue, need: o.need.key });
          });
        }
        offerBox.hidden = false;
      } catch { if (mine === offerSeq) offerBox.hidden = true; }   // demo mode or no agents: the panel simply stays away
    };
    byId('lv-o-actions')!.addEventListener('click', async (e) => {
      const b = hit<HTMLButtonElement>(e, '[data-outcome]');
      if (!b) return;
      const group = b.parentElement!.querySelectorAll<HTMLButtonElement>('[data-outcome]');
      group.forEach((x) => { x.disabled = true; });
      try {
        await post('/sales/outcome', { customerId: b.dataset.customer || null, offerId: b.dataset.offer, outcome: b.dataset.outcome, relevance: Number(b.dataset.relevance), cue: b.dataset.cue, need: b.dataset.need ?? '' });
        toast(`Recorded: ${b.dataset.outcome}. It counts in the track record.`);
      } catch (err) { group.forEach((x) => { x.disabled = false; }); toast((err as Error).message); }
    });
    const say = (who: string, msg: string, extra = '', mood = 50, voice?: { url?: string; after?: Promise<unknown> }) => {
      convo.push(who === 'client' ? { speaker: 'customer', text: msg, mood } : { speaker: 'advisor', text: msg });
      if (who === 'client' && voiceOn?.checked) void (voice?.after ?? Promise.resolve()).then(() => speak(msg, 'customer', mood, personaKey));
      const li = make('li', { className: `live-msg ${who}` });
      li.append(make('strong', { textContent: who === 'client' ? 'Customer' : voice?.url ? 'You (voice note)' : 'You' }), make('span', { textContent: msg }));
      if (who === 'advisor' && voice?.url) {
        const player = make('audio', { controls: true, src: voice.url });
        player.setAttribute('aria-label', 'Your voice note');
        li.append(player);
      } else if (who === 'advisor') {
        const b = make('button', { type: 'button', className: 'btn-quiet listen', textContent: 'Listen' });
        b.addEventListener('click', () => void speak(msg, 'advisor'));
        li.append(b);
      }
      if (extra) li.append(make('small', { className: 'muted', textContent: extra }));
      log.append(li);
      li.scrollIntoView({ block: 'nearest' });
    };
    const meters = (mood: number, patience: number) => {
      byId<HTMLMeterElement>('lv-mood')!.value = mood; byId('lv-mood-n')!.textContent = String(mood);
      byId<HTMLMeterElement>('lv-pat')!.value = patience; byId('lv-pat-n')!.textContent = String(patience);
    };
    const suggest = (s: { text: string; sources: string[]; confidence: number; intents?: string[]; policyWarning: string | null } | null) => {
      byId('live-suggest')!.hidden = !s;
      useBtn.disabled = !s;
      if (!s) return;
      byId('lv-s-text')!.textContent = s.text;
      byId('lv-s-meta')!.textContent = `Sources: ${s.sources.join(', ') || 'none'}${s.intents?.length ? ` · intents: ${s.intents.join(', ')}` : ''}`;
      const w = byId('lv-s-warn')!;
      w.hidden = !s.policyWarning;
      w.textContent = s.policyWarning ?? '';
    };
    byId('live-setup')!.addEventListener('submit', async (e) => {
      e.preventDefault();
      status.textContent = 'Calling the customer…';
      try {
        const d = await post('/advisor/live/start', { persona: sel('lv-persona'), intent: sel('lv-intent'), difficulty: sel('lv-diff'), memory: byId<HTMLInputElement>('lv-memory')!.checked });
        callId = d.id; topic = d.opening; personaKey = sel('lv-persona'); log.replaceChildren(); byId('live-outcome')!.hidden = true;
        convo = []; offerBox.hidden = true;
        say('client', d.opening, d.persona, d.mood);
        void showOffers();
        meters(d.mood, d.patience); suggest(d.suggestion);
        sendBtn.disabled = false; if (recBtn) recBtn.disabled = false; text.value = ''; call.hidden = false; status.textContent = ''; text.focus();
      } catch (err) { status.textContent = (err as Error).message; }
    });
    useBtn.addEventListener('click', () => { text.value = byId('lv-s-text')!.textContent ?? ''; text.focus(); });
    // one way to answer the customer, whether the words were typed or came from a voice note
    const sendAdvisor = async (msg: string, voiceUrl?: string, tone?: { emotion: string; mood: number } | null) => {
      if (!msg || !callId) return;
      sendBtn.disabled = true; if (recBtn) recBtn.disabled = true;
      // a typed reply can be said out loud in the advisor's voice; the customer then answers after it
      const spoken = !voiceUrl && sayMine?.checked ? speak(msg, 'advisor') : undefined;
      const heard: Record<string, string> = { anger: 'angry', disgust: 'disgusted', fear: 'worried', happy: 'happy', neutral: 'calm', sad: 'sad' };
      say('advisor', msg, tone ? `Your voice sounded ${heard[tone.emotion] ?? tone.emotion}` : '', 50, { url: voiceUrl });
      text.value = '';
      try {
        const d = await post('/advisor/live/say', { id: callId, text: msg, topic, tone: tone ?? null });
        if (d.client) { say('client', d.client, d.moveLabel ? `She read this as: ${d.moveLabel}` : '', d.mood, { after: spoken }); void showOffers(); }
        meters(d.mood, d.patience); suggest(d.suggestion);
        if (d.ended) {
          const o = d.outcome, box = byId('live-outcome')!;
          box.textContent = `${o.verdict} Churn risk ${o.churnRisk}%. ${o.notes.join(' ')}`;
          box.hidden = false; useBtn.disabled = true;
        } else { sendBtn.disabled = false; if (recBtn) recBtn.disabled = false; }
      } catch (err) { status.textContent = (err as Error).message; }
    };
    byId('live-say')!.addEventListener('submit', (e) => { e.preventDefault(); void sendAdvisor(text.value.trim()); });

    // send the call to the quality queue (the quality analyst scores it from the transcript)
    const reviewBtn = byId<HTMLButtonElement>('lv-review');
    reviewBtn?.addEventListener('click', async () => {
      if (!callId) return;
      reviewBtn.disabled = true;
      status.textContent = 'The quality analyst is reading the call…';
      try {
        const d = await post('/advisor/live/review', { id: callId });
        status.textContent = `Sent: ${d.callId} scored ${d.overall}/100. Nour sees it in Quality reviews.`;
      } catch (err) { status.textContent = (err as Error).message; }
      reviewBtn.disabled = false;
    });

    // voice notes: record, turn the recording into a 16 kHz WAV here in the page, let the speech-to-text agent write it down, then send it
    const toWav = async (blob: Blob): Promise<Blob> => {
      const ac = new AudioContext();
      const decoded = await ac.decodeAudioData(await blob.arrayBuffer());
      void ac.close();
      const off = new OfflineAudioContext(1, Math.max(1, Math.ceil(decoded.duration * 16000)), 16000);
      const src = off.createBufferSource();
      src.buffer = decoded; src.connect(off.destination); src.start();
      const pcm = (await off.startRendering()).getChannelData(0);
      const buf = new ArrayBuffer(44 + pcm.length * 2), v = new DataView(buf);
      const str = (o: number, s: string) => [...s].forEach((c, i) => v.setUint8(o + i, c.charCodeAt(0)));
      str(0, 'RIFF'); v.setUint32(4, 36 + pcm.length * 2, true); str(8, 'WAVE'); str(12, 'fmt ');
      v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true); v.setUint32(24, 16000, true);
      v.setUint32(28, 32000, true); v.setUint16(32, 2, true); v.setUint16(34, 16, true); str(36, 'data'); v.setUint32(40, pcm.length * 2, true);
      pcm.forEach((x, i) => v.setInt16(44 + i * 2, Math.max(-1, Math.min(1, x)) * 0x7fff, true));
      return new Blob([buf], { type: 'audio/wav' });
    };
    if (recBtn && navigator.mediaDevices?.getUserMedia && 'MediaRecorder' in window) {
      const clock = byId('lv-rec-time')!;
      let recorder: MediaRecorder | null = null, timer = 0;
      const MAX_SECONDS = 60;
      recBtn.addEventListener('click', async () => {
        if (recorder) { recorder.stop(); return; }
        if (!callId) return;
        stopSpeaking();
        let stream: MediaStream;
        try { stream = await navigator.mediaDevices.getUserMedia({ audio: true }); }
        catch { status.textContent = 'The microphone is blocked. Allow it in the browser, or type your reply.'; return; }
        const chunks: Blob[] = [], started = Date.now();
        const r = recorder = new MediaRecorder(stream);
        r.ondataavailable = (e) => chunks.push(e.data);
        r.onstop = async () => {
          clearInterval(timer); clock.textContent = ''; recorder = null;
          stream.getTracks().forEach((t) => t.stop());
          recBtn.textContent = 'Record voice note'; recBtn.classList.remove('recording');
          const recording = new Blob(chunks, { type: r.mimeType });
          sendBtn.disabled = true; recBtn.disabled = true;
          status.textContent = 'Writing down your voice note…';
          try {
            const wav = await toWav(recording);
            const res = await fetch('/voice/transcribe', { method: 'POST', headers: { 'Content-Type': 'audio/wav', 'X-CSRF-Token': csrf }, body: wav });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) throw new Error(data.error ?? 'Could not read the voice note.');
            status.textContent = '';
            await sendAdvisor(data.text, URL.createObjectURL(recording), data.tone);
          } catch (err) {
            status.textContent = (err as Error).message;
            sendBtn.disabled = false; recBtn.disabled = false;
          }
        };
        r.start();
        recBtn.textContent = 'Stop and send'; recBtn.classList.add('recording');
        timer = window.setInterval(() => {
          const s = Math.floor((Date.now() - started) / 1000);
          clock.textContent = `${s}s`;
          if (s >= MAX_SECONDS) r.stop();
        }, 500);
      });
    } else if (recBtn) recBtn.hidden = true;   // no microphone support: typing still works
  }

  // Ideas: filter by decision
  const filters = $$('[data-filter]');
  filters.forEach((btn) => btn.addEventListener('click', () => {
    filters.forEach((b) => b.setAttribute('aria-pressed', String(b === btn)));
    const f = btn.dataset.filter;
    $$('.idea').forEach((i) => { i.hidden = f !== 'all' && i.dataset.decision !== f; });
    $$('.idea-set').forEach((s) => { s.hidden = !s.querySelector('.idea:not([hidden])'); });
    byId('no-ideas')!.hidden = !!document.querySelector('.idea:not([hidden])');
  }));

  // Training: choosing another advisor reloads the coach plan
  const advisorPicker = byId<HTMLSelectElement>('advisor');
  if (advisorPicker) advisorPicker.addEventListener('change', () => advisorPicker.form?.submit());


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

  // Quality: upload a two-channel recording; the page then opens the new review
  const audioForm = byId<HTMLFormElement>('audio-form');
  if (audioForm) {
    const file = byId<HTMLInputElement>('rec-file')!, who = byId<HTMLInputElement>('rec-advisor')!, status = byId('audio-status')!;
    audioForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const f = file.files?.[0];
      if (!f) return;
      if (f.size > 10_000_000) { status.textContent = 'This recording is larger than 10 MB. Cut it or compress it first.'; return; }
      status.textContent = 'Listening to both sides of the call… a minute of speech takes a few seconds.';
      try {
        const res = await fetch(`/quality/audio?advisor=${encodeURIComponent(who.value.trim())}`, { method: 'POST', body: f, headers: { 'Content-Type': f.type || 'application/octet-stream', 'X-CSRF-Token': audioForm.dataset.csrf! } });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) { status.textContent = data.error ?? 'Something went wrong.'; return; }
        status.textContent = `Scored ${data.overall}/100. Opening the review…`;
        location.href = `/quality?call=${encodeURIComponent(data.callId)}#${data.callId}`;
      } catch { status.textContent = 'The app could not be reached. Try again.'; }
    });
  }

  // Quality: Correct / Not an error on a finding (a second click takes the verdict back); the page reloads so the score and the criteria follow
  const reopen = store.sget('qopen');
  if (reopen) {
    store.sdel('qopen');
    const box = document.getElementById(reopen);
    box?.querySelector('details.lost')?.setAttribute('open', '');
    box?.scrollIntoView();
  }
  document.addEventListener('click', async (e) => {
    const b = hit<HTMLButtonElement>(e, 'button.fb');
    if (!b) return;
    const verdict = b.getAttribute('aria-pressed') === 'true' ? 'clear' : b.dataset.verdict;
    b.disabled = true;
    try {
      const res = await fetch('/quality/feedback', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken },
        body: JSON.stringify({ callId: b.dataset.call, rule: b.dataset.rule, turn: Number(b.dataset.turn), verdict }) });
      if (!res.ok) throw new Error(((await res.json().catch(() => ({}))) as { error?: string }).error ?? 'Could not save the verdict.');
      store.sset('qopen', b.dataset.call!);
      location.reload();
    } catch (err) { b.disabled = false; toast((err as Error).message); }
  });

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

  // Particles: a calm field of drifting dots joined by faint lines, in the page's accent colour. Behind the content, never
  // blocks clicks, pauses when the tab is hidden, off by default for people who ask their system for reduced motion, and
  // the sidebar button turns it off or on (remembered per browser).
  const fx = (() => {
    interface Dot { x: number; y: number; vx: number; vy: number; r: number }
    const canvas = make('canvas', { className: 'fx' });
    canvas.setAttribute('aria-hidden', 'true');
    const ctx = canvas.getContext('2d');
    let dots: Dot[] = [], w = 0, h = 0, frame = 0, rgb = '47,91,234', on = false;
    const pointer = { x: -9999, y: -9999 };
    const LINK = 120, PUSH = 140;

    const refresh = () => { // read the accent colour of the current page and theme
      const m = /^#([0-9a-f]{6})$/i.exec(getComputedStyle(document.body).getPropertyValue('--accent').trim());
      if (m) rgb = [0, 2, 4].map((i) => parseInt(m[1].slice(i, i + 2), 16)).join(',');
    };
    const resize = () => {
      const dpr = Math.min(devicePixelRatio || 1, 2);
      w = innerWidth; h = innerHeight;
      canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr);
      ctx?.setTransform(dpr, 0, 0, dpr, 0, 0);
      const want = Math.max(18, Math.min(70, Math.round((w * h) / 22000)));
      while (dots.length < want) dots.push({ x: Math.random() * w, y: Math.random() * h, vx: (Math.random() - 0.5) * 0.35, vy: (Math.random() - 0.5) * 0.35, r: 1.2 + Math.random() * 1.8 });
      dots.length = want;
    };
    const tick = () => {
      if (!ctx) return;
      ctx.clearRect(0, 0, w, h);
      for (const d of dots) {
        const dx = d.x - pointer.x, dy = d.y - pointer.y, dist = Math.hypot(dx, dy);
        if (dist < PUSH && dist > 0) { d.vx += (dx / dist) * 0.02; d.vy += (dy / dist) * 0.02; } // gently pushed away from the pointer
        d.vx = Math.max(-0.6, Math.min(0.6, d.vx * 0.995)); d.vy = Math.max(-0.6, Math.min(0.6, d.vy * 0.995));
        d.x += d.vx; d.y += d.vy;
        if (d.x < -10) d.x = w + 10; else if (d.x > w + 10) d.x = -10;
        if (d.y < -10) d.y = h + 10; else if (d.y > h + 10) d.y = -10;
      }
      ctx.lineWidth = 1;
      for (let i = 0; i < dots.length; i++) for (let j = i + 1; j < dots.length; j++) {
        const d = Math.hypot(dots[i].x - dots[j].x, dots[i].y - dots[j].y);
        if (d < LINK) { ctx.strokeStyle = `rgba(${rgb},${((1 - d / LINK) * 0.22).toFixed(3)})`; ctx.beginPath(); ctx.moveTo(dots[i].x, dots[i].y); ctx.lineTo(dots[j].x, dots[j].y); ctx.stroke(); }
      }
      ctx.fillStyle = `rgba(${rgb},0.45)`;
      for (const d of dots) { ctx.beginPath(); ctx.arc(d.x, d.y, d.r, 0, Math.PI * 2); ctx.fill(); }
      frame = requestAnimationFrame(tick);
    };
    const run = () => { if (on && !document.hidden && !frame) frame = requestAnimationFrame(tick); };
    const halt = () => { cancelAnimationFrame(frame); frame = 0; };
    addEventListener('mousemove', (e) => { pointer.x = e.clientX; pointer.y = e.clientY; }, { passive: true });
    addEventListener('mouseout', () => { pointer.x = pointer.y = -9999; });
    let resizing = 0;
    addEventListener('resize', () => { clearTimeout(resizing); resizing = window.setTimeout(() => { if (on) resize(); }, 150); });
    document.addEventListener('visibilitychange', () => (document.hidden ? halt() : run()));
    return {
      set(next: boolean) {
        on = next;
        if (on) { refresh(); document.body.append(canvas); resize(); run(); } else { halt(); canvas.remove(); }
      },
      refresh,
    };
  })();
  const fxButton = $('.fx-toggle');
  const fxState = store.get('cv-fx') ?? (calm ? 'off' : 'on');
  const setFx = (on: boolean) => {
    fx.set(on);
    fxButton?.setAttribute('aria-pressed', String(on));
    fxButton?.setAttribute('aria-label', on ? 'Turn particles off' : 'Turn particles on');
    const label = fxButton && $('.nav-label', fxButton);
    if (label) label.textContent = on ? 'Particles on' : 'Particles off';
  };
  setFx(fxState === 'on');
  fxButton?.addEventListener('click', () => { const on = fxButton.getAttribute('aria-pressed') !== 'true'; setFx(on); store.set('cv-fx', on ? 'on' : 'off'); });

  // Keyboard shortcuts window: press ? anywhere (except while typing)
  const help = make('dialog', { className: 'shortcuts', ariaLabel: 'Keyboard shortcuts' });
  const keys: [string, string][] = [['Ctrl K', 'Jump to any page'], ['?', 'Show this list'], ['Esc', 'Close a window'],
    ['← →', 'Previous or next slide (presentation mode)'], ['N', 'Speaker notes (presentation mode)'], ['F', 'Full screen (presentation mode)']];
  help.append(make('h2', { textContent: 'Keyboard shortcuts' }));
  const list = help.appendChild(document.createElement('dl'));
  keys.forEach(([k, what]) => {
    const dt = document.createElement('dt');
    k.split(' ').forEach((part, i) => { if (i) dt.append(' '); dt.append(make('kbd', { textContent: part })); });
    list.append(dt, make('dd', { textContent: what }));
  });
  help.append(make('p', { className: 'shortcuts-foot', textContent: 'Everything in orqestra can also be done with the mouse.' }));
  help.addEventListener('click', (e) => { if (e.target === help) help.close(); });
  document.body.append(help);
  addEventListener('keydown', (e) => {
    const t = e.target as HTMLElement | null;
    if (e.key !== '?' || e.ctrlKey || e.metaKey || e.altKey || t?.closest('input, textarea, select, [contenteditable="true"]')) return;
    e.preventDefault();
    if (help.open) help.close(); else help.showModal();
  });
  // "Try again" on error pages
  document.addEventListener('click', (e) => { if (hit(e, '[data-reload]')) location.reload(); });

  // Save as PDF: the print stylesheet lays slides and pages out for paper
  document.addEventListener('click', (e) => { if (hit(e, '[data-print]')) print(); });

  // Dark mode: follows the system until the user picks, then remembers the choice
  const themeBtn = $('.theme-toggle');
  const setTheme = (t: string) => {
    if (!calm && document.documentElement.dataset.theme) {   // cross-fade the colours instead of snapping
      document.documentElement.classList.add('theme-fade');
      setTimeout(() => document.documentElement.classList.remove('theme-fade'), 520);
    }
    document.documentElement.dataset.theme = t;
    fx.refresh();
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

  // Complaints: read a complaint without saving it (the real complaint agent), then open it as a case with the form's other button
  const triForm = byId<HTMLFormElement>('tri-form');
  if (triForm) {
    const csrf = triForm.dataset.csrf!;
    document.addEventListener('click', (e) => {
      const sample = hit<HTMLButtonElement>(e, '[data-tri-sample]');
      if (!sample) return;
      byId<HTMLTextAreaElement>('tri-text')!.value = sample.dataset.triSample!;
      byId<HTMLSelectElement>('tri-customer')!.value = sample.dataset.triCustomer ?? '';
    });
    byId('tri-read')!.addEventListener('click', async () => {
      const status = byId('tri-status')!, out = byId('tri-result')!, text = byId<HTMLTextAreaElement>('tri-text')!.value.trim(), customer = byId<HTMLSelectElement>('tri-customer')!.value;
      if (text.length < 10) { status.textContent = 'Write the complaint in at least a sentence.'; return; }
      status.textContent = 'Reading the complaint…';
      out.hidden = true;
      try {
        const res = await fetch('/complaints/triage', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf }, body: JSON.stringify({ text, customerId: customer || null }) });
        const d = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(d.error ?? 'Something went wrong.');
        status.textContent = '';
        byId('tri-cluster')!.textContent = d.cluster;
        const level = byId('tri-level')!;
        level.textContent = `${d.severity} · escalation risk ${d.escalationRisk}`;
        level.className = `risk ${d.severity === 'Critical' || d.severity === 'High' ? 'high' : d.severity === 'Medium' ? 'medium' : 'low'}`;
        byId('tri-deadline')!.textContent = `Deadline ${d.deadline.slaHours} h${d.warning ? `. Early warning: ${d.warning.why}.` : ''}`;
        byId('tri-sev-h')!.textContent = `How serious: ${d.severityScore}/100`;
        byId('tri-risk-h')!.textContent = `How likely to escalate: ${d.escalationRisk}/100`;
        byId('tri-sev')!.replaceChildren(...(d.severityFactors.length ? [...factorList(d.severityFactors).children] : [make('li', { textContent: 'Nothing at stake that the agent can see.' })]));
        byId('tri-risk')!.replaceChildren(...[...factorList(d.riskFactors).children]);
        byId('tri-actions')!.replaceChildren(...(d.actions as { action: string; why: string; who: string }[]).map((a) => {
          const li = make('li');
          li.append(make('strong', { textContent: a.action }), ` ${a.why}. ${a.who}.`);
          return li;
        }));
        out.hidden = false;
      } catch (err) { status.textContent = (err as Error).message; }
    });
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
    ['/', 'Welcome', 'orqestra is a digital twin of a contact center: seven personas, seven agents. This tour follows one customer story, page by page.'],
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
