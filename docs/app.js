(() => {
  const $ = (id) => document.getElementById(id);
  const KEYS = ["kont", "stadt", "firma", "von", "bis", "dauer", "datum", "q", "sf"];
  const LISTS = ["land", "fach"];
  const FLAGS = ["ohneVisum", "erasmus", "ausland", "neu"];
  const state = { tab: "alle", ohneStart: true };
  KEYS.forEach((k) => (state[k] = ""));
  LISTS.forEach((k) => (state[k] = []));
  FLAGS.forEach((k) => (state[k] = false));
  let jobs = [], byLink = new Map(), L = { laender: {}, foerderungen: {}, allgemein: [], kontinente: [] }, pflicht = 720;

  // ---------------------------------------------------------------- Speicher (nur im Browser)
  const store = {
    get(k, fallback, area = localStorage) {
      try { const v = JSON.parse(area.getItem(k)); return v ?? fallback; } catch { return fallback; }
    },
    set(k, v, area = localStorage) { try { area.setItem(k, JSON.stringify(v)); } catch { /* gesperrt oder voll */ } },
  };
  const FAV_KEY = "praktikum-ws27-favoriten";
  const SNAP_KEY = "praktikum-ws27-merkliste";   // Titel/Firma/Ort der gemerkten Stellen, falls die Anzeige verschwindet
  const STATUS_KEY = "praktikum-ws27-status";
  const SEEN_KEY = "praktikum-ws27-gesehen";
  const BASE_KEY = "praktikum-ws27-basis";       // sessionStorage: Stand beim Öffnen, damit „Neu“ beim Neuladen bleibt

  const loadFavs = () => {
    const raw = store.get(FAV_KEY, []);
    return new Set(Array.isArray(raw) ? raw.filter((x) => typeof x === "string") : []);
  };
  const obj = (k) => { const v = store.get(k, {}); return v && typeof v === "object" && !Array.isArray(v) ? v : {}; };
  const favs = loadFavs();
  let snaps = obj(SNAP_KEY);
  let status = obj(STATUS_KEY);
  const saveFavs = () => store.set(FAV_KEY, [...favs]);
  const saveSnaps = () => store.set(SNAP_KEY, snaps);
  const saveStatus = () => store.set(STATUS_KEY, status);
  let neuSet = new Set(), ersterBesuch = true;

  const STATUS = [
    ["", "Kein Status"],
    ["beworben", "Beworben"],
    ["gespraech", "Im Gespräch"],
    ["zusage", "Zusage"],
    ["absage", "Absage"],
  ];
  const statusName = (s) => (STATUS.find(([k]) => k === s) || ["", ""])[1];

  // ---------------------------------------------------------------- Hilfen
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const fmtDate = (iso) => {
    if (!iso) return "";
    const d = new Date(iso + "T00:00:00");
    return isNaN(d) ? iso : d.toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit", year: "numeric" });
  };
  const today = () => new Date().toISOString().slice(0, 10);
  const daysAgo = (iso) => (Date.now() - new Date(iso + "T00:00:00").getTime()) / 864e5;
  const ka = '<span class="ka">k. A.</span>';
  const val = (v) => (!v || v === "k. A." ? ka : esc(v));
  const land = (c) => L.laender[c] || { name: c, kontinent: "", visum: true, erasmus: false };
  const ortText = (o) => (o.stadt && o.stadt !== "k. A." && o.stadt !== land(o.land).name ? `${o.stadt}, ${land(o.land).name}` : land(o.land).name);
  const orteText = (j) => (j.offline ? j.ortFallback || "" : j.orte.map(ortText).join(" / "));
  const erasmusOk = (c) => land(c).erasmus === true || land(c).erasmus === "2027";
  const MONATE = ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"];
  const monthLabel = (ym) => { const [y, m] = ym.split("-"); return `${MONATE[+m - 1]} ${y}`; };
  const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;

  // ---------------------------------------------------------------- Mehrfachauswahl
  function multiSelect(el, { allLabel, searchLabel, onChange }) {
    const labelId = el.dataset.label;
    el.innerHTML = `
      <button type="button" class="ms-btn" aria-haspopup="true" aria-expanded="false" aria-labelledby="${labelId} ${el.id}-val">
        <span class="ms-val" id="${el.id}-val"></span>
        <svg aria-hidden="true" viewBox="0 0 24 24"><path d="m6 9 6 6 6-6"/></svg>
      </button>
      <div class="ms-pop" hidden>
        ${searchLabel ? `<input type="search" class="ms-q" placeholder="${esc(searchLabel)}" aria-label="${esc(searchLabel)}" autocomplete="off">` : ""}
        <div class="ms-list" role="group" aria-labelledby="${labelId}"></div>
        <div class="ms-foot"><button type="button" class="ghost ms-clear">Auswahl löschen</button><button type="button" class="cta ms-done">Fertig</button></div>
      </div>`;
    const btn = el.querySelector(".ms-btn"), pop = el.querySelector(".ms-pop"), list = el.querySelector(".ms-list"), q = el.querySelector(".ms-q");
    let items = [], selected = [];
    const labelOf = (v) => (items.find((i) => i.v === v) || { label: v }).label;
    function paintValue() {
      const v = el.querySelector(".ms-val");
      if (!selected.length) { v.textContent = allLabel; el.classList.remove("on"); return; }
      el.classList.add("on");
      v.textContent = selected.length <= 2 ? selected.map(labelOf).join(", ") : `${labelOf(selected[0])} +${selected.length - 1}`;
      btn.title = selected.map(labelOf).join(", ");
    }
    function paintList() {
      const term = q ? q.value.trim().toLowerCase() : "";
      let group = null, html = "";
      items.filter((i) => !term || i.label.toLowerCase().includes(term)).forEach((i) => {
        if (i.group && i.group !== group) { group = i.group; html += `<div class="ms-group">${esc(group)}</div>`; }
        html += `<label class="ms-opt"><input type="checkbox" value="${esc(i.v)}"${selected.includes(i.v) ? " checked" : ""}><span>${esc(i.label)}</span><span class="ms-n">${i.n ?? ""}</span></label>`;
      });
      list.innerHTML = html || '<p class="ms-none">Nichts gefunden</p>';
    }
    const open = () => { pop.hidden = false; btn.setAttribute("aria-expanded", "true"); paintList(); (q || list.querySelector("input"))?.focus(); };
    const close = (focus) => { if (pop.hidden) return; pop.hidden = true; btn.setAttribute("aria-expanded", "false"); if (q) q.value = ""; if (focus) btn.focus(); };
    btn.addEventListener("click", () => (pop.hidden ? open() : close()));
    list.addEventListener("change", (e) => {
      const v = e.target.value;
      selected = e.target.checked ? [...selected, v] : selected.filter((x) => x !== v);
      paintValue();
      onChange([...selected]);
    });
    q && q.addEventListener("input", paintList);
    el.querySelector(".ms-clear").addEventListener("click", () => { selected = []; paintValue(); paintList(); onChange([]); });
    el.querySelector(".ms-done").addEventListener("click", () => close(true));
    document.addEventListener("click", (e) => { if (!el.contains(e.target)) close(); });
    el.addEventListener("keydown", (e) => { if (e.key === "Escape") { e.stopPropagation(); close(true); } });
    return {
      set(newItems, sel) { items = newItems; selected = sel.filter((v) => items.some((i) => i.v === v)); paintValue(); if (!pop.hidden) paintList(); return selected; },
    };
  }
  let msLand, msFach;

  // ---------------------------------------------------------------- Filter
  function ortePassend(j, st = state) {
    return j.orte.filter((o) =>
      (!st.kont || land(o.land).kontinent === st.kont) &&
      (!st.land.length || st.land.includes(o.land)) &&
      (!st.stadt || o.stadt === st.stadt) &&
      (!st.ausland || o.land !== "DE") &&
      (!st.ohneVisum || !land(o.land).visum) &&
      (!st.erasmus || erasmusOk(o.land)));
  }

  function matches(j, st = state) {
    if (!ortePassend(j, st).length) return false;
    if (st.firma && j.firma !== st.firma) return false;
    if (st.fach.length && !st.fach.includes(j.fachbereich)) return false;
    if (st.neu && !neuSet.has(j.link)) return false;
    if (st.von || st.bis) {
      if (!j.start_monat) { if (!st.ohneStart) return false; }
      else if ((st.von && j.start_monat < st.von) || (st.bis && j.start_monat > st.bis)) return false;
    }
    if (st.dauer === "min" && j.dauer_wochen != null && j.dauer_wochen < 20) return false;
    if (st.dauer === "streng" && (j.dauer_wochen == null || j.dauer_wochen < 20)) return false;
    if (st.datum && daysAgo(j.veroeffentlicht) > Number(st.datum)) return false;
    if (st.q) {
      const hay = `${j.titel} ${j.firma} ${j.fachbereich} ${orteText(j)}`.toLowerCase();
      if (!st.q.toLowerCase().split(/\s+/).every((w) => hay.includes(w))) return false;
    }
    return true;
  }

  // ---------------------------------------------------------------- URL
  function readUrl() {
    const p = new URLSearchParams(location.hash.slice(1));
    state.tab = ["fav", "info"].includes(p.get("tab")) ? p.get("tab") : "alle";
    KEYS.forEach((k) => (state[k] = p.get(k) || ""));
    LISTS.forEach((k) => (state[k] = (p.get(k) || "").split(",").filter(Boolean)));
    FLAGS.forEach((k) => (state[k] = p.get(k) === "1"));
    state.ohneStart = p.get("ohneStart") !== "0";
  }
  function writeUrl() {
    const p = new URLSearchParams();
    if (state.tab !== "alle") p.set("tab", state.tab);
    KEYS.forEach((k) => state[k] && p.set(k, state[k]));
    LISTS.forEach((k) => state[k].length && p.set(k, state[k].join(",")));
    FLAGS.forEach((k) => state[k] && p.set(k, "1"));
    if (!state.ohneStart) p.set("ohneStart", "0");
    history.replaceState(null, "", p.toString() ? "#" + p : location.pathname + location.search);
  }

  function fillSelect(el, items, allLabel, current) {
    el.innerHTML = `<option value="">${allLabel}</option>` + items.map(([v, label]) =>
      `<option value="${esc(v)}"${v === current ? " selected" : ""}>${esc(label)}</option>`).join("");
    if (current && !items.some(([v]) => v === current)) el.value = "";
  }

  function refreshGeoSelects() {
    const all = jobs.flatMap((j) => j.orte);
    const kontinente = (L.kontinente || []).filter((k) => all.some((o) => land(o.land).kontinent === k));
    if (state.kont && !kontinente.includes(state.kont)) state.kont = "";
    fillSelect($("f-kont"), kontinente.map((k) => [k, k]), "Alle Kontinente", state.kont);
    const inKont = (o) => (!state.kont || land(o.land).kontinent === state.kont) && (!state.ausland || o.land !== "DE");
    const perLand = {};
    jobs.forEach((j) => new Set(j.orte.filter(inKont).map((o) => o.land)).forEach((c) => (perLand[c] = (perLand[c] || 0) + 1)));
    const order = L.kontinente || [];
    const lc = Object.keys(perLand).sort((a, b) =>
      (order.indexOf(land(a).kontinent) - order.indexOf(land(b).kontinent)) || land(a).name.localeCompare(land(b).name, "de"));
    state.land = msLand.set(lc.map((c) => ({ v: c, label: land(c).name, n: perLand[c], group: state.kont ? "" : land(c).kontinent })), state.land);
    const st = [...new Set(all.filter((o) => inKont(o) && (!state.land.length || state.land.includes(o.land)) && o.stadt !== "k. A.")
      .map((o) => o.stadt))].sort((a, b) => a.localeCompare(b, "de"));
    if (state.stadt && !st.includes(state.stadt)) state.stadt = "";
    fillSelect($("f-stadt"), st.map((s) => [s, s]), "Alle Städte", state.stadt);
  }

  function refreshFach() {
    const per = {};
    jobs.forEach((j) => (per[j.fachbereich] = (per[j.fachbereich] || 0) + 1));
    const names = Object.keys(per).sort((a, b) => a.localeCompare(b, "de"));
    state.fach = msFach.set(names.map((f) => ({ v: f, label: f, n: per[f] })), state.fach);
  }

  // ---------------------------------------------------------------- Favoriten & Bewerbungsstatus
  function snapshot(j) {
    snaps[j.link] = { t: j.titel, f: j.firma, o: j.orte.map(ortText).join(" / "), d: j.veroeffentlicht };
  }
  // alle gemerkten Stellen, auch solche, deren Anzeige inzwischen offline ist
  function favEntries() {
    const links = new Set([...favs, ...Object.keys(status)]);
    return [...links].map((link) => {
      const j = byLink.get(link);
      if (j) return j;
      const s = snaps[link];
      if (!s) return null;
      return { titel: s.t, firma: s.f, orte: [], ortFallback: s.o, fachbereich: "k. A.", start: "k. A.", dauer: "k. A.",
        stunden: "k. A.", arbeitsmodell: "k. A.", veroeffentlicht: s.d || "", link, offline: true };
    }).filter(Boolean);
  }
  const favFilter = (j) => {
    const s = (status[j.link] || {}).s || "";
    return !state.sf || (state.sf === "ohne" ? !s : s === state.sf);
  };

  function renderStatusbar(entries) {
    const bar = $("statusbar");
    bar.hidden = state.tab !== "fav" || !entries.length;
    if (bar.hidden) return;
    const n = (k) => entries.filter((j) => ((status[j.link] || {}).s || "") === k).length;
    const opts = [["", "Alle", entries.length], ["ohne", "Ohne Status", n("")], ...STATUS.slice(1).map(([k, l]) => [k, l, n(k)])];
    if (!opts.some(([k]) => k === state.sf)) state.sf = "";
    bar.innerHTML = opts.filter(([k, , c]) => c > 0 || k === "" || k === state.sf).map(([k, l, c]) =>
      `<button type="button" class="chip st-chip${k ? " st-" + k : ""}" data-sf="${k}" aria-pressed="${state.sf === k}">${esc(l)} <span class="n">${c}</span></button>`).join("");
  }

  // ---------------------------------------------------------------- Darstellung
  function badges(code) {
    const l = land(code);
    let b = l.visum ? '<span class="tag tag-visa">Visum nötig</span>' : '<span class="tag tag-free">kein Visum</span>';
    if (l.erasmus === true) b += '<span class="tag tag-eras">Erasmus+</span>';
    else if (l.erasmus === "2027") b += '<span class="tag tag-eras" title="voraussichtlich ab Studienjahr 2027/28">Erasmus+ ab 27/28</span>';
    return b;
  }

  function ortCell(j) {
    if (j.offline) return `<div class="ort">${esc(j.ortFallback || "")}</div>`;
    const show = j.orte.slice(0, 3);
    const more = j.orte.length - show.length;
    return show.map((o) => `<div class="ort"><button type="button" class="land-link" data-land="${esc(o.land)}" title="Visa- und Förderinfos zu ${esc(land(o.land).name)}">${esc(ortText(o))}</button><span class="tags">${badges(o.land)}</span></div>`).join("")
      + (more > 0 ? `<div class="ka">+ ${more} weitere Orte</div>` : "");
  }

  function stundenCell(j) {
    if (j.stunden_num) {
      const w = Math.ceil(pflicht / j.stunden_num);
      return `${esc(j.stunden)}<div class="hint">≈ ${w} Wochen für ${pflicht} h</div>`;
    }
    if (j.stunden === "Vollzeit") return `Vollzeit<div class="hint">≈ 18–21 Wochen für ${pflicht} h</div>`;
    return val(j.stunden);
  }

  function statusCell(j) {
    const cur = status[j.link] || {};
    const opts = STATUS.map(([k, l]) => `<option value="${k}"${(cur.s || "") === k ? " selected" : ""}>${esc(l)}</option>`).join("");
    return `<div class="st-row"><label class="sr" for="st-${esc(j.link)}">Bewerbungsstatus</label>
      <select class="status${cur.s ? " st-" + cur.s : ""}" id="st-${esc(j.link)}" data-link="${esc(j.link)}">${opts}</select>
      ${cur.s && cur.d ? `<span class="hint">seit ${fmtDate(cur.d)}</span>` : ""}</div>`;
  }

  function row(j) {
    const on = favs.has(j.link) || !!status[j.link];
    const label = on ? "Aus Favoriten entfernen" : "Als Favorit markieren";
    const tags = (neuSet.has(j.link) ? '<span class="tag tag-new">Neu</span>' : "")
      + (j.offline ? '<span class="tag tag-off" title="Die Anzeige ist auf der Karriereseite nicht mehr zu finden">nicht mehr online</span>' : "");
    return `
      <tr${j.offline ? ' class="offline"' : ""}>
        <td class="c-title"><div class="c-row">
          <button type="button" class="fav" data-link="${esc(j.link)}" aria-pressed="${on}" aria-label="${label}: ${esc(j.titel)}" title="${label}">${on ? "★" : "☆"}</button>
          <div class="c-text"><div class="title">${esc(j.titel)}${tags ? ` <span class="tags tags-inline">${tags}</span>` : ""}</div><div class="company">${esc(j.firma)}${j.arbeitsmodell && j.arbeitsmodell !== "k. A." ? " · " + esc(j.arbeitsmodell) : ""}</div>${on ? statusCell(j) : ""}</div>
        </div></td>
        <td class="c-ort" data-l="Ort">${ortCell(j)}</td>
        <td data-l="Fachbereich">${val(j.fachbereich)}</td>
        <td data-l="Start">${val(j.start)}</td>
        <td data-l="Gesamtdauer">${val(j.dauer)}</td>
        <td data-l="Wochenstunden">${stundenCell(j)}</td>
        <td class="c-date" data-l="Veröffentlicht" title="${j.datum_geschaetzt ? "Zuerst erfasst am" : "Veröffentlicht am"}">${j.datum_geschaetzt ? "≈ " : ""}${fmtDate(j.veroeffentlicht)}</td>
        <td class="c-link"><a class="go" href="${esc(j.link)}" target="_blank" rel="noopener noreferrer">Zur Stelle ↗</a></td>
      </tr>`;
  }

  function renderTabs(entries) {
    ["alle", "fav", "info"].forEach((t) => $("tab-" + t).setAttribute("aria-selected", String(state.tab === t)));
    $("fav-n").textContent = entries.length;
    $("filters").hidden = state.tab !== "alle";
    $("mailbox").hidden = state.tab !== "fav" || !entries.length;
    $("info").hidden = state.tab !== "info";
    $("sources").hidden = state.tab === "info";
    const chipKey = { "c-ohnevisum": "ohneVisum", "c-erasmus": "erasmus", "c-ohnestart": "ohneStart", "c-ausland": "ausland", "c-neu": "neu" };
    Object.entries(chipKey).forEach(([id, k]) => $(id).setAttribute("aria-pressed", String(state[k])));
    $("c-ohnestart").hidden = !(state.von || state.bis);
    $("c-neu").hidden = !neuSet.size;
    $("neu-n").textContent = neuSet.size;
  }

  // ---------------------------------------------------------------- Leere Ergebnisse erklären
  function activeFilters() {
    const out = [];
    const add = (label, clear) => out.push({ label, clear });
    const names = (arr, fn) => arr.map(fn).join(", ");
    if (state.q) add(`Suche: ${state.q}`, (s) => (s.q = ""));
    if (state.kont) add(`Kontinent: ${state.kont}`, (s) => (s.kont = ""));
    if (state.land.length) add(`Land: ${names(state.land, (c) => land(c).name)}`, (s) => (s.land = []));
    if (state.stadt) add(`Stadt: ${state.stadt}`, (s) => (s.stadt = ""));
    if (state.firma) add(`Firma: ${state.firma}`, (s) => (s.firma = ""));
    if (state.fach.length) add(`Fachbereich: ${state.fach.join(", ")}`, (s) => (s.fach = []));
    if (state.von || state.bis) add(`Start ${state.von ? "ab " + monthLabel(state.von) : ""}${state.von && state.bis ? " " : ""}${state.bis ? "bis " + monthLabel(state.bis) : ""}`, (s) => (s.von = s.bis = ""));
    if (state.dauer) add(state.dauer === "streng" ? "Gesamtdauer mind. 20 Wochen" : "Gesamtdauer mind. 20 Wochen (inkl. k. A.)", (s) => (s.dauer = ""));
    if (state.datum) add(`Veröffentlicht: letzte ${state.datum} Tage`, (s) => (s.datum = ""));
    if (state.ausland) add("Nur Ausland", (s) => (s.ausland = false));
    if (state.neu) add("Neu seit letztem Besuch", (s) => (s.neu = false));
    if (state.ohneVisum) add("Kein Visum nötig", (s) => (s.ohneVisum = false));
    if (state.erasmus) add("Erasmus+-förderfähig", (s) => (s.erasmus = false));
    if ((state.von || state.bis) && !state.ohneStart) add("Stellen ohne Startangabe ausgeblendet", (s) => (s.ohneStart = true));
    return out;
  }
  let suggestions = [];
  function renderEmptyHelp() {
    const act = activeFilters();
    suggestions = act.map((f) => {
      const s = structuredClone(state);
      f.clear(s);
      return { ...f, n: jobs.filter((j) => matches(j, s)).length };
    }).filter((f) => f.n > 0).sort((a, b) => b.n - a.n).slice(0, 4);
    const tips = suggestions.map((f, i) =>
      `<li><button type="button" class="ghost sugg" data-i="${i}"><span>„${esc(f.label)}“ entfernen</span><strong>${plural(f.n, "Praktikum", "Praktika")}</strong></button></li>`).join("");
    $("empty-help").innerHTML = (tips
      ? `<p>Diese Filter schränken am stärksten ein. Ohne einen davon findest du:</p><ul class="sugg-list">${tips}</ul>`
      : act.length > 1 ? "<p>Erst mehrere Filter zusammen schließen alles aus.</p>" : "")
      + (act.length ? '<p><button type="button" class="cta reset-all">Alle Filter zurücksetzen</button></p>' : "");
  }

  function render() {
    const entries = favEntries();
    renderTabs(entries);
    renderStatusbar(entries);
    const isInfo = state.tab === "info", isFav = state.tab === "fav";
    const list = isInfo ? [] : isFav ? entries.filter(favFilter) : jobs.filter((j) => matches(j));
    $("rows").innerHTML = list.map(row).join("");
    $("count").hidden = isInfo;
    $("count").textContent = isFav
      ? (state.sf ? `${list.length} von ${plural(entries.length, "Favorit", "Favoriten")}` : plural(list.length, "Favorit", "Favoriten"))
      : `${list.length} von ${jobs.length} Praktika`;
    const empty = !isInfo && !isFav && list.length === 0 && jobs.length > 0;
    $("empty").hidden = !empty;
    if (empty) renderEmptyHelp();
    $("empty-fav").hidden = !isFav || entries.length > 0;
    document.querySelector(".table-wrap").hidden = isInfo || list.length === 0;
    if (isInfo && !$("info").dataset.done) renderInfo();
    writeUrl();
  }

  // ---------------------------------------------------------------- Visa & Förderung
  function links(arr) {
    return (arr || []).map((l) => `<li><a href="${esc(l.u)}" target="_blank" rel="noopener noreferrer">${esc(l.t)} ↗</a></li>`).join("");
  }
  function landHtml(code, withJobs) {
    const l = land(code);
    const n = jobs.filter((j) => j.orte.some((o) => o.land === code)).length;
    const f = (l.foerderung || []).map((k) => L.foerderungen[k]).filter(Boolean);
    return `
      <div class="land-head"><h3 id="${withJobs ? "" : "dlg-title"}">${esc(l.name)}</h3><span class="tags">${badges(code)}</span></div>
      ${l.hubs && l.hubs.length ? `<p class="ka">Berücksichtigte Städte: ${esc(l.hubs.join(", "))}</p>` : ""}
      <p>${esc(l.visum_text)}</p>
      ${l.links && l.links.length ? `<h4>Offizielle Infos</h4><ul class="links">${links(l.links)}</ul>` : ""}
      ${f.length ? `<h4>Förderung</h4><ul class="foerder">${f.map((x) => `<li><strong>${esc(x.name)}</strong><span>${esc(x.text)}</span><ul class="links">${links(x.links)}</ul></li>`).join("")}</ul>` : ""}
      ${withJobs && n ? `<p><button type="button" class="ghost show-land" data-land="${esc(code)}">${n} ${n === 1 ? "Praktikum" : "Praktika"} in ${esc(l.name)} anzeigen</button></p>` : ""}`;
  }
  function renderInfo() {
    const byK = {};
    Object.keys(L.laender).forEach((c) => (byK[land(c).kontinent] ||= []).push(c));
    const sections = (L.kontinente || []).map((k) => {
      const codes = (byK[k] || []).sort((a, b) => land(a).name.localeCompare(land(b).name, "de"));
      const eu = codes.filter((c) => !land(c).visum && land(c).erasmus === true && c !== "DE");
      const rest = codes.filter((c) => !eu.includes(c));
      const euBlock = eu.length ? `<details class="land"><summary><span>EU &amp; EWR (${eu.length} Länder)</span><span class="tags">${badges(eu[0])}</span></summary><div class="land-body">${landHtml(eu[0], false).replace(/<h3[^>]*>.*?<\/h3>/, "<h3>EU- und EWR-Länder</h3>")}<p class="ka">${esc(eu.map((c) => land(c).name).join(", "))}</p></div></details>` : "";
      return `<h2>${esc(k)}</h2>${euBlock}` + rest.map((c) =>
        `<details class="land" id="land-${c}"><summary><span>${esc(land(c).name)}</span><span class="tags">${badges(c)}</span></summary><div class="land-body">${landHtml(c, true)}</div></details>`).join("");
    }).join("");
    const allg = (L.allgemein || []).map((a) => `<li><strong>${esc(a.name)}</strong><span>${esc(a.text)}</span><ul class="links">${links(a.links)}</ul></li>`).join("");
    const glob = Object.values(L.foerderungen || {}).map((x) => `<li><strong>${esc(x.name)}</strong><span>${esc(x.text)}</span><ul class="links">${links(x.links)}</ul></li>`).join("");
    $("info").innerHTML = `
      <p class="info-lead">Kurzinfos für deutsche Staatsangehörige und ein Pflichtpraktikum von 20–22 Wochen (Stand ${esc(L.stand || "")}). Die verlinkten Behördenseiten sind maßgeblich; Bedingungen ändern sich, deshalb vor der Bewerbung dort nachlesen und früh mit dem International Office der OTH sprechen.</p>
      <div class="info-grid"><div>${sections}</div>
      <aside><h2>Förderung</h2><ul class="foerder">${glob}${allg}</ul></aside></div>`;
    $("info").dataset.done = "1";
  }
  function openLand(code) {
    $("dlg-body").innerHTML = landHtml(code, false);
    const d = $("land-dialog");
    if (typeof d.showModal === "function") d.showModal(); else { state.tab = "info"; render(); }
  }

  // ---------------------------------------------------------------- Mail (mailto, nichts wird gespeichert)
  function favList() { return favEntries(); }
  function siteUrl() { return location.origin + location.pathname; }
  const NL = "\r\n"; // mailto verlangt CRLF, sonst ziehen manche Mailprogramme alles zu Fließtext zusammen
  const known = (v) => v && v !== "k. A.";
  function entryInfo(j) {
    const info = [`${j.firma} · ${orteText(j)}`];
    const extra = [known(j.fachbereich) ? j.fachbereich : "", known(j.start) ? `Start ${j.start}` : "", known(j.dauer) ? j.dauer : "",
      known(j.arbeitsmodell) ? j.arbeitsmodell : ""].filter(Boolean);
    if (extra.length) info.push(extra.join(" · "));
    const st = status[j.link];
    if (st && st.s) info.push(`Status: ${statusName(st.s)}${st.d ? " (seit " + fmtDate(st.d) + ")" : ""}`);
    if (j.offline) info.push("Anzeige nicht mehr online");
    return info;
  }
  // Klartext (Mail): Titel in Großbuchstaben als Überschrift, Link direkt darunter, dann Infos, 2 Leerzeilen Abstand
  function entryText(j) {
    return [`▶ ${j.titel.toLocaleUpperCase("de-DE")}`, j.link, ...entryInfo(j)].join(NL);
  }
  const SEP = NL + NL + NL;
  function listBody(entries, heading) {
    return `${heading}${NL}${"=".repeat(heading.length)}${SEP}${entries.join(SEP)}${SEP}Alle Praktika: ${siteUrl()}${NL}`;
  }
  function plainList() { return listBody(favList().map(entryText), "Meine Praktikums-Favoriten"); }
  // HTML (Zwischenablage): echte größere Überschrift je Stelle
  function htmlList() {
    const items = favList().map((j) =>
      `<p style="margin:0;font-size:17px;font-weight:bold">${esc(j.titel)}</p>` +
      `<p style="margin:2px 0 0"><a href="${esc(j.link)}">${esc(j.link)}</a></p>` +
      entryInfo(j).map((t) => `<p style="margin:2px 0 0;color:#555">${esc(t)}</p>`).join("")).join("<br><br>");
    return `<h2>Meine Praktikums-Favoriten</h2>${items}<br><br><p>Alle Praktika: <a href="${esc(siteUrl())}">${esc(siteUrl())}</a></p>`;
  }
  function mailParts() {
    const list = favList(), parts = [];
    let cur = [];
    const size = (arr) => encodeURIComponent(listBody(arr, "Meine Praktikums-Favoriten (Teil 10/10)")).length;
    list.forEach((j) => {
      const e = entryText(j);
      if (cur.length && size([...cur, e]) > 1900) { parts.push(cur); cur = []; }
      cur.push(e);
    });
    if (cur.length) parts.push(cur);
    return parts.map((p, i) => {
      const suffix = parts.length > 1 ? ` (Teil ${i + 1}/${parts.length})` : "";
      return { subject: `Praktikum WS27: meine Favoriten${suffix}`, body: listBody(p, `Meine Praktikums-Favoriten${suffix}`) };
    });
  }
  function mailto(addr, m) {
    return `mailto:${encodeURIComponent(addr).replace(/%40/g, "@")}?subject=${encodeURIComponent(m.subject)}&body=${encodeURIComponent(m.body)}`;
  }

  // ---------------------------------------------------------------- Quellen
  function renderSources(data) {
    const items = data.firmen.map((f) =>
      `<li><a href="${esc(f.career_url)}" target="_blank" rel="noopener noreferrer">${esc(f.name)}</a> (${f.stellen})` +
      (f.aktiv === false ? ` <span class="ka">· ${esc(f.note || "nicht abrufbar")}</span>`
        : f.ok ? "" : ` <span class="warn" title="${esc(f.note)}">· Abruf fehlgeschlagen</span>`) + "</li>").join("");
    $("sources").innerHTML = data.firmen.length ? `<h2>Berücksichtigte Unternehmen</h2><ul>${items}</ul>` : "";
  }

  // ---------------------------------------------------------------- Neu seit dem letzten Besuch
  function initNeu() {
    const current = jobs.map((j) => j.link);
    let base = store.get(BASE_KEY, null, sessionStorage);
    if (!Array.isArray(base)) {
      base = store.get(SEEN_KEY, null);
      store.set(BASE_KEY, Array.isArray(base) ? base : [], sessionStorage);
    }
    ersterBesuch = !Array.isArray(base) || !base.length;
    const known = new Set(Array.isArray(base) ? base : []);
    neuSet = ersterBesuch ? new Set() : new Set(current.filter((l) => !known.has(l)));
    if (current.length) store.set(SEEN_KEY, current);
    if (!neuSet.size) state.neu = false;
  }

  // ---------------------------------------------------------------- Start
  function init(data, laender) {
    jobs = data.stellen || [];
    byLink = new Map(jobs.map((j) => [j.link, j]));
    L = laender;
    pflicht = laender.pflichtstunden || 720;
    readUrl();
    initNeu();
    // Merkliste mit aktuellen Daten auffrischen
    jobs.forEach((j) => { if (favs.has(j.link) || status[j.link]) snapshot(j); });
    saveSnaps();
    $("stand").textContent = L.stand || "";
    $("n-stunden").textContent = `${pflicht} Std.`;
    const uniq = (arr) => [...new Set(arr)].sort((a, b) => a.localeCompare(b, "de"));
    msLand = multiSelect($("f-land"), { allLabel: "Alle Länder", searchLabel: "Land suchen", onChange: (v) => { state.land = v; refreshGeoSelects(); render(); } });
    msFach = multiSelect($("f-fach"), { allLabel: "Alle Fachbereiche", onChange: (v) => { state.fach = v; render(); } });
    refreshGeoSelects();
    refreshFach();
    const firmen = uniq([...data.firmen.map((f) => f.name), ...jobs.map((j) => j.firma)]);
    fillSelect($("f-firma"), firmen.map((n) => [n, `${n} (${jobs.filter((j) => j.firma === n).length})`]), "Alle Firmen", state.firma);
    const now = new Date(), months = [];
    for (let i = 0; i < 30; i++) {
      const d = new Date(now.getFullYear(), now.getMonth() + i, 1);
      months.push(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`);
    }
    fillSelect($("f-von"), months.map((m) => [m, monthLabel(m)]), "Beliebig", state.von);
    fillSelect($("f-bis"), months.map((m) => [m, monthLabel(m)]), "Beliebig", state.bis);
    $("f-dauer").value = state.dauer;
    $("f-datum").value = state.datum;
    $("q").value = state.q;
    const upd = new Date(data.aktualisiert);
    $("meta").textContent = jobs.length || data.firmen.length
      ? `${jobs.length} Praktika · zuletzt aktualisiert am ${upd.toLocaleDateString("de-DE", { day: "2-digit", month: "long", year: "numeric" })}`
        + (neuSet.size ? ` · ${neuSet.size} neu seit deinem letzten Besuch` : "")
      : "Noch keine Daten: Der erste automatische Abruf läuft nach dem Eintragen der Firmen.";
    renderSources(data);
    const named = data.firmen.filter((f) => f.aktiv !== false && f.stellen > 0).slice(0, 3).map((f) => f.name).join(", ");
    const aktiv = data.firmen.filter((f) => f.aktiv !== false).length;
    $("n-firmen").textContent = aktiv ? `${aktiv} Arbeitgeber${named ? ", z. B. " + named : ""}` : "folgt";

    function syncInputs() {
      refreshGeoSelects();
      refreshFach();
      ["firma", "von", "bis", "dauer", "datum"].forEach((k) => ($("f-" + k).value = state[k]));
      $("q").value = state.q;
    }
    function resetFilters() {
      KEYS.filter((k) => k !== "sf").forEach((k) => (state[k] = ""));
      LISTS.forEach((k) => (state[k] = []));
      FLAGS.forEach((k) => (state[k] = false));
      state.ohneStart = true;
      syncInputs();
      render();
    }

    document.body.addEventListener("click", (e) => {
      const fav = e.target.closest(".fav");
      if (fav) {
        const link = fav.dataset.link;
        const on = favs.has(link) || status[link];
        if (on) {
          const st = status[link];
          if (st && st.s && !confirm(`Diese Stelle hat den Status „${statusName(st.s)}“. Aus den Favoriten entfernen und den Status löschen?`)) return;
          favs.delete(link); delete status[link]; delete snaps[link];
        } else {
          favs.add(link);
          const j = byLink.get(link);
          if (j) snapshot(j);
        }
        saveFavs(); saveStatus(); saveSnaps();
        render();
        return;
      }
      const ll = e.target.closest(".land-link");
      if (ll) { openLand(ll.dataset.land); return; }
      const sl = e.target.closest(".show-land");
      if (sl) {
        KEYS.filter((k) => k !== "sf").forEach((k) => (state[k] = ""));
        LISTS.forEach((k) => (state[k] = []));
        state.land = [sl.dataset.land];
        state.tab = "alle";
        $("land-dialog").open && $("land-dialog").close();
        syncInputs();
        render();
        window.scrollTo({ top: 0 });
        return;
      }
      const sg = e.target.closest(".sugg");
      if (sg) { suggestions[+sg.dataset.i].clear(state); syncInputs(); render(); return; }
      if (e.target.closest(".reset-all")) { resetFilters(); return; }
      const sf = e.target.closest(".st-chip");
      if (sf) { state.sf = state.sf === sf.dataset.sf ? "" : sf.dataset.sf; render(); }
    });
    document.body.addEventListener("change", (e) => {
      const sel = e.target.closest("select.status");
      if (!sel) return;
      const link = sel.dataset.link;
      if (sel.value) status[link] = { s: sel.value, d: today() };
      else delete status[link];
      favs.add(link);
      const j = byLink.get(link);
      if (j) snapshot(j);
      saveStatus(); saveFavs(); saveSnaps();
      render();
    });
    document.querySelector(".tabs").addEventListener("click", (e) => {
      const t = e.target.closest(".tab");
      if (!t) return;
      state.tab = t.dataset.tab;
      render();
    });
    window.addEventListener("storage", (e) => {
      if (![FAV_KEY, STATUS_KEY, SNAP_KEY].includes(e.key)) return;
      favs.clear();
      loadFavs().forEach((l) => favs.add(l));
      status = obj(STATUS_KEY);
      snaps = obj(SNAP_KEY);
      render();
    });

    const bind = (id, key, geo) => $(id).addEventListener("input", (e) => {
      state[key] = e.target.value;
      if (geo) refreshGeoSelects();
      render();
    });
    bind("f-kont", "kont", true); bind("f-stadt", "stadt");
    bind("f-firma", "firma"); bind("f-von", "von"); bind("f-bis", "bis");
    bind("f-dauer", "dauer"); bind("f-datum", "datum");
    let qTimer;
    $("q").addEventListener("input", (e) => { clearTimeout(qTimer); qTimer = setTimeout(() => { state.q = e.target.value; render(); }, 150); });
    const toggle = (id, key, geo) => $(id).addEventListener("click", () => { state[key] = !state[key]; if (geo) refreshGeoSelects(); render(); });
    toggle("c-ohnevisum", "ohneVisum"); toggle("c-erasmus", "erasmus"); toggle("c-ohnestart", "ohneStart");
    toggle("c-ausland", "ausland", true); toggle("c-neu", "neu");
    $("reset").addEventListener("click", resetFilters);

    $("mailform").addEventListener("submit", (e) => {
      e.preventDefault();
      const addr = $("mail").value.trim();
      if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(addr)) {
        $("mail-msg").textContent = "Bitte eine gültige E-Mail-Adresse eingeben.";
        $("mail").focus();
        return;
      }
      const parts = mailParts();
      if (parts.length === 1) {
        $("mail-parts").innerHTML = "";
        $("mail-msg").textContent = "Dein Mailprogramm öffnet sich mit der fertigen Mail. Nur noch auf „Senden“ klicken.";
        location.href = mailto(addr, parts[0]);
      } else {
        $("mail-msg").textContent = `Viele Favoriten: Die Liste wird auf ${parts.length} Mails aufgeteilt, damit kein Mailprogramm sie abschneidet. Bitte nacheinander öffnen.`;
        $("mail-parts").innerHTML = parts.map((p, i) => `<a class="cta" href="${esc(mailto(addr, p))}">Mail ${i + 1} von ${parts.length} öffnen</a>`).join("");
      }
    });
    $("copy").addEventListener("click", async () => {
      try {
        if (window.ClipboardItem && navigator.clipboard.write) {
          await navigator.clipboard.write([new ClipboardItem({
            "text/html": new Blob([htmlList()], { type: "text/html" }),
            "text/plain": new Blob([plainList()], { type: "text/plain" }),
          })]);
        } else {
          await navigator.clipboard.writeText(plainList());
        }
        $("mail-msg").textContent = "Liste kopiert. Du kannst sie in jede Mail oder Notiz einfügen.";
      } catch {
        $("mail-msg").textContent = "Kopieren hat nicht geklappt. Bitte „Mail erstellen“ nutzen.";
      }
    });
    render();
  }

  Promise.all([
    fetch("data/jobs.json", { cache: "no-cache" }).then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); }),
    fetch("data/laender.json", { cache: "no-cache" }).then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); }),
  ]).then(([d, l]) => init(d, l)).catch((err) => {
    console.error(err);
    $("meta").textContent = "Die Praktika konnten nicht geladen werden. Bitte später erneut versuchen.";
    document.querySelector(".table-wrap").hidden = true;
  });
})();
