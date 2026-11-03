(() => {
  const $ = (id) => document.getElementById(id);
  const KEYS = ["kont", "land", "stadt", "firma", "fach", "von", "bis", "dauer", "datum", "q"];
  const FLAGS = ["ohneVisum", "erasmus"];
  const state = { tab: "alle", ohneStart: true, ohneVisum: false, erasmus: false };
  KEYS.forEach((k) => (state[k] = ""));
  let jobs = [], L = { laender: {}, foerderungen: {}, allgemein: [], kontinente: [] }, pflicht = 720;

  // ---------------------------------------------------------------- Favoriten (nur im Browser)
  const FAV_KEY = "praktikum-ws27-favoriten";
  const loadFavs = () => {
    try {
      const raw = JSON.parse(localStorage.getItem(FAV_KEY) || "[]");
      return new Set(Array.isArray(raw) ? raw.filter((x) => typeof x === "string") : []);
    } catch { return new Set(); }
  };
  const saveFavs = () => { try { localStorage.setItem(FAV_KEY, JSON.stringify([...favs])); } catch { /* gesperrt */ } };
  const favs = loadFavs();

  // ---------------------------------------------------------------- Hilfen
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const fmtDate = (iso) => {
    const d = new Date(iso + "T00:00:00");
    return isNaN(d) ? iso : d.toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit", year: "numeric" });
  };
  const daysAgo = (iso) => (Date.now() - new Date(iso + "T00:00:00").getTime()) / 864e5;
  const ka = '<span class="ka">k. A.</span>';
  const val = (v) => (!v || v === "k. A." ? ka : esc(v));
  const land = (c) => L.laender[c] || { name: c, kontinent: "", visum: true, erasmus: false };
  const ortText = (o) => (o.stadt && o.stadt !== "k. A." && o.stadt !== land(o.land).name ? `${o.stadt}, ${land(o.land).name}` : land(o.land).name);
  const erasmusOk = (c) => land(c).erasmus === true || land(c).erasmus === "2027";
  const MONATE = ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"];
  const monthLabel = (ym) => { const [y, m] = ym.split("-"); return `${MONATE[+m - 1]} ${y}`; };

  function ortePassend(j) {
    return j.orte.filter((o) =>
      (!state.kont || land(o.land).kontinent === state.kont) &&
      (!state.land || o.land === state.land) &&
      (!state.stadt || o.stadt === state.stadt) &&
      (!state.ohneVisum || !land(o.land).visum) &&
      (!state.erasmus || erasmusOk(o.land)));
  }

  // ---------------------------------------------------------------- URL
  function readUrl() {
    const p = new URLSearchParams(location.hash.slice(1));
    state.tab = ["fav", "info"].includes(p.get("tab")) ? p.get("tab") : "alle";
    KEYS.forEach((k) => (state[k] = p.get(k) || ""));
    FLAGS.forEach((k) => (state[k] = p.get(k) === "1"));
    state.ohneStart = p.get("ohneStart") !== "0";
  }
  function writeUrl() {
    const p = new URLSearchParams();
    if (state.tab !== "alle") p.set("tab", state.tab);
    KEYS.forEach((k) => state[k] && p.set(k, state[k]));
    FLAGS.forEach((k) => state[k] && p.set(k, "1"));
    if (!state.ohneStart) p.set("ohneStart", "0");
    history.replaceState(null, "", p.toString() ? "#" + p : location.pathname + location.search);
  }

  // ---------------------------------------------------------------- Filter
  function matches(j) {
    if (!ortePassend(j).length) return false;
    if (state.firma && j.firma !== state.firma) return false;
    if (state.fach && j.fachbereich !== state.fach) return false;
    if (state.von || state.bis) {
      if (!j.start_monat) { if (!state.ohneStart) return false; }
      else if ((state.von && j.start_monat < state.von) || (state.bis && j.start_monat > state.bis)) return false;
    }
    if (state.dauer === "min" && j.dauer_wochen != null && j.dauer_wochen < 20) return false;
    if (state.dauer === "streng" && (j.dauer_wochen == null || j.dauer_wochen < 20)) return false;
    if (state.datum && daysAgo(j.veroeffentlicht) > Number(state.datum)) return false;
    if (state.q) {
      const hay = `${j.titel} ${j.firma} ${j.fachbereich} ${j.orte.map(ortText).join(" ")}`.toLowerCase();
      if (!state.q.toLowerCase().split(/\s+/).every((w) => hay.includes(w))) return false;
    }
    return true;
  }

  function fillSelect(el, items, allLabel, current) {
    el.innerHTML = `<option value="">${allLabel}</option>` + items.map(([v, label]) =>
      `<option value="${esc(v)}"${v === current ? " selected" : ""}>${esc(label)}</option>`).join("");
    if (current && !items.some(([v]) => v === current)) el.value = "";
  }

  function refreshGeoSelects() {
    const all = jobs.flatMap((j) => j.orte);
    const kontinente = (L.kontinente || []).filter((k) => all.some((o) => land(o.land).kontinent === k));
    fillSelect($("f-kont"), kontinente.map((k) => [k, k]), "Alle Kontinente", state.kont);
    const lc = [...new Set(all.filter((o) => !state.kont || land(o.land).kontinent === state.kont).map((o) => o.land))]
      .sort((a, b) => land(a).name.localeCompare(land(b).name, "de"));
    if (state.land && !lc.includes(state.land)) state.land = "";
    fillSelect($("f-land"), lc.map((c) => [c, land(c).name]), "Alle Länder", state.land);
    const st = [...new Set(all.filter((o) => (!state.kont || land(o.land).kontinent === state.kont) &&
      (!state.land || o.land === state.land) && o.stadt !== "k. A.").map((o) => o.stadt))].sort((a, b) => a.localeCompare(b, "de"));
    if (state.stadt && !st.includes(state.stadt)) state.stadt = "";
    fillSelect($("f-stadt"), st.map((s) => [s, s]), state.land ? "Alle Städte" : "Alle Städte", state.stadt);
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

  function row(j) {
    const on = favs.has(j.link);
    const label = on ? "Aus Favoriten entfernen" : "Als Favorit markieren";
    return `
      <tr>
        <td class="c-title"><div class="c-row">
          <button type="button" class="fav" data-link="${esc(j.link)}" aria-pressed="${on}" aria-label="${label}: ${esc(j.titel)}" title="${label}">${on ? "★" : "☆"}</button>
          <div class="c-text"><div class="title">${esc(j.titel)}</div><div class="company">${esc(j.firma)}${j.arbeitsmodell && j.arbeitsmodell !== "k. A." ? " · " + esc(j.arbeitsmodell) : ""}</div></div>
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

  function renderTabs() {
    ["alle", "fav", "info"].forEach((t) => $("tab-" + t).setAttribute("aria-selected", String(state.tab === t)));
    $("fav-n").textContent = jobs.filter((j) => favs.has(j.link)).length;
    $("filters").hidden = state.tab !== "alle";
    $("mailbox").hidden = state.tab !== "fav" || !jobs.some((j) => favs.has(j.link));
    $("info").hidden = state.tab !== "info";
    $("sources").hidden = state.tab === "info";
    ["c-ohnevisum", "c-erasmus", "c-ohnestart"].forEach((id) => {
      const k = { "c-ohnevisum": "ohneVisum", "c-erasmus": "erasmus", "c-ohnestart": "ohneStart" }[id];
      $(id).setAttribute("aria-pressed", String(state[k]));
    });
    $("c-ohnestart").hidden = !(state.von || state.bis);
  }

  function render() {
    renderTabs();
    const isInfo = state.tab === "info", isFav = state.tab === "fav";
    const list = isInfo ? [] : isFav ? jobs.filter((j) => favs.has(j.link)) : jobs.filter(matches);
    $("rows").innerHTML = list.map(row).join("");
    $("count").hidden = isInfo;
    $("count").textContent = isFav ? `${list.length} ${list.length === 1 ? "Favorit" : "Favoriten"}` : `${list.length} von ${jobs.length} Praktika`;
    $("empty").hidden = isInfo || isFav || list.length > 0;
    $("empty-fav").hidden = !isFav || list.length > 0;
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
  function favList() { return jobs.filter((j) => favs.has(j.link)); }
  function siteUrl() { return location.origin + location.pathname; }
  function entryText(j, i) {
    return `${i + 1}) ${j.titel}\n   ${j.firma} · ${j.orte.map(ortText).join(" / ")}\n   ${j.link}\n`;
  }
  function plainList() {
    return `Meine Praktikums-Favoriten\n\n${favList().map(entryText).join("\n")}\nPraktikum WS27: ${siteUrl()}\n`;
  }
  function mailParts() {
    const list = favList(), parts = [];
    const foot = `\nAlle Praktika: ${siteUrl()}\n`;
    let cur = [];
    const size = (arr) => encodeURIComponent(`Meine Praktikums-Favoriten\n\n${arr.join("\n")}${foot}`).length;
    list.forEach((j, i) => {
      const e = entryText(j, i);
      if (cur.length && size([...cur, e]) > 1700) { parts.push(cur); cur = []; }
      cur.push(e);
    });
    if (cur.length) parts.push(cur);
    return parts.map((p, i) => ({
      subject: `Praktikum WS27: meine Favoriten${parts.length > 1 ? ` (Teil ${i + 1}/${parts.length})` : ""}`,
      body: `Meine Praktikums-Favoriten${parts.length > 1 ? ` (Teil ${i + 1}/${parts.length})` : ""}\n\n${p.join("\n")}${foot}`,
    }));
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

  // ---------------------------------------------------------------- Start
  function init(data, laender) {
    jobs = data.stellen || [];
    L = laender;
    pflicht = laender.pflichtstunden || 720;
    readUrl();
    $("stand").textContent = L.stand || "";
    $("n-stunden").textContent = `${pflicht} Std.`;
    const uniq = (arr) => [...new Set(arr)].sort((a, b) => a.localeCompare(b, "de"));
    refreshGeoSelects();
    const firmen = uniq([...data.firmen.map((f) => f.name), ...jobs.map((j) => j.firma)]);
    fillSelect($("f-firma"), firmen.map((n) => [n, `${n} (${jobs.filter((j) => j.firma === n).length})`]), "Alle Firmen", state.firma);
    fillSelect($("f-fach"), uniq(jobs.map((j) => j.fachbereich)).map((f) => [f, f]), "Alle Fachbereiche", state.fach);
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
      : "Noch keine Daten: Der erste automatische Abruf läuft nach dem Eintragen der Firmen.";
    renderSources(data);
    const named = data.firmen.filter((f) => f.aktiv !== false && f.stellen > 0).slice(0, 3).map((f) => f.name).join(", ");
    const aktiv = data.firmen.filter((f) => f.aktiv !== false).length;
    $("n-firmen").textContent = aktiv ? `${aktiv} Arbeitgeber${named ? ", z. B. " + named : ""}` : "folgt";

    document.body.addEventListener("click", (e) => {
      const fav = e.target.closest(".fav");
      if (fav) {
        const link = fav.dataset.link;
        favs.has(link) ? favs.delete(link) : favs.add(link);
        saveFavs();
        render();
        return;
      }
      const ll = e.target.closest(".land-link");
      if (ll) { openLand(ll.dataset.land); return; }
      const sl = e.target.closest(".show-land");
      if (sl) {
        KEYS.forEach((k) => (state[k] = ""));
        state.land = sl.dataset.land;
        state.tab = "alle";
        $("land-dialog").open && $("land-dialog").close();
        syncInputs();
        render();
        window.scrollTo({ top: 0 });
      }
    });
    document.querySelector(".tabs").addEventListener("click", (e) => {
      const t = e.target.closest(".tab");
      if (!t) return;
      state.tab = t.dataset.tab;
      render();
    });
    window.addEventListener("storage", (e) => {
      if (e.key !== FAV_KEY) return;
      favs.clear();
      loadFavs().forEach((l) => favs.add(l));
      render();
    });

    const bind = (id, key, geo) => $(id).addEventListener("input", (e) => {
      state[key] = e.target.value;
      if (geo) refreshGeoSelects();
      render();
    });
    bind("f-kont", "kont", true); bind("f-land", "land", true); bind("f-stadt", "stadt");
    bind("f-firma", "firma"); bind("f-fach", "fach"); bind("f-von", "von"); bind("f-bis", "bis");
    bind("f-dauer", "dauer"); bind("f-datum", "datum"); bind("q", "q");
    const toggle = (id, key) => $(id).addEventListener("click", () => { state[key] = !state[key]; render(); });
    toggle("c-ohnevisum", "ohneVisum"); toggle("c-erasmus", "erasmus"); toggle("c-ohnestart", "ohneStart");
    function syncInputs() {
      refreshGeoSelects();
      ["firma", "fach", "von", "bis", "dauer", "datum"].forEach((k) => ($("f-" + k).value = state[k]));
      $("q").value = state.q;
    }
    $("reset").addEventListener("click", () => {
      KEYS.forEach((k) => (state[k] = ""));
      state.ohneVisum = state.erasmus = false;
      state.ohneStart = true;
      syncInputs();
      render();
    });

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
        await navigator.clipboard.writeText(plainList());
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
  ]).then(([d, l]) => init(d, l)).catch(() => {
    $("meta").textContent = "Die Praktika konnten nicht geladen werden. Bitte später erneut versuchen.";
    document.querySelector(".table-wrap").hidden = true;
  });
})();
