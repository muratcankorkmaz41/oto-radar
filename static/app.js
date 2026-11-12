/* Oto Radar paneli: takip formu, akıllı araç arama, ilan listesi ve otomatik yenileme. */
(function () {
  "use strict";

  const $ = id => document.getElementById(id);
  const carData = window.carData || {};
  const initial = JSON.parse($("initial-data").textContent || "{}");
  const nf = new Intl.NumberFormat("tr-TR");
  const fmt = n => nf.format(Math.round(n || 0));
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  /* ================= Bildirim kutucukları ================= */
  function toast(text, kind = "", action) {
    const el = document.createElement("div");
    el.className = "toast " + kind;
    el.textContent = text;
    if (action) {
      const b = document.createElement("button");
      b.type = "button";
      b.textContent = action.label;
      b.addEventListener("click", () => { action.run(); close(); });
      el.appendChild(b);
    }
    $("toasts").appendChild(el);
    const close = () => { el.classList.add("out"); setTimeout(() => el.remove(), 300); };
    setTimeout(close, action ? 9000 : 5000);
  }
  (initial.flash || []).forEach(m => toast(m, "warn"));

  /* ================= Takip formu ================= */
  const brandSelect = $("brandSelect"), seriesSelect = $("seriesSelect"), modelSelect = $("modelSelect");
  const searchBox = $("searchBox"), searchList = $("searchList"), preview = $("preview"), clearBtn = $("clearCar");
  const opt = (v, t) => `<option value="${esc(v)}">${esc(t ?? v)}</option>`;

  brandSelect.innerHTML = opt("", "Marka seçin…") +
    Object.keys(carData).sort((x, y) => x.localeCompare(y, "tr")).map(b => opt(b)).join("");
  seriesSelect.innerHTML = opt("", "Önce marka seçin");
  modelSelect.innerHTML = opt("", "Önce seri seçin");

  brandSelect.addEventListener("change", () => {
    modelSelect.innerHTML = opt("", "Önce seri seçin");
    modelSelect.disabled = true;
    const series = carData[brandSelect.value];
    seriesSelect.disabled = !series;
    seriesSelect.innerHTML = series ? opt("", "Seri seçin…") + Object.keys(series).map(s => opt(s)).join("") : opt("", "Önce marka seçin");
    syncFromSelects();
  });
  seriesSelect.addEventListener("change", () => {
    const models = (carData[brandSelect.value] || {})[seriesSelect.value];
    modelSelect.disabled = !models;
    modelSelect.innerHTML = models ? models.map(m => opt(m, m === "Tüm Modeller" ? "Tüm alt modeller" : m)).join("") : opt("", "Önce seri seçin");
    syncFromSelects();
  });
  modelSelect.addEventListener("change", syncFromSelects);

  function buildKeyword() {
    let kw = brandSelect.value;
    if (seriesSelect.value) kw += " " + seriesSelect.value;
    if (modelSelect.value && !modelSelect.value.startsWith("Tüm")) kw += " " + modelSelect.value;
    return kw.trim();
  }

  // Listeden seçim yapılınca arama kutusu da seçilen aracı göstersin
  function syncFromSelects() {
    const kw = buildKeyword();
    searchBox.value = kw;
    searchBox.classList.toggle("picked", !!kw);
    clearBtn.hidden = !kw;
    updatePreview();
  }

  function resetCar() {
    brandSelect.value = "";
    brandSelect.dispatchEvent(new Event("change"));
    searchBox.value = "";
    searchBox.classList.remove("picked");
    clearBtn.hidden = true;
    updatePreview();
  }
  clearBtn.addEventListener("click", () => { resetCar(); searchBox.focus(); });

  const flagDefs = [["req_hasarsiz", "ağır hasarsız"], ["req_boyasiz", "boyasız"], ["req_degisensiz", "değişensiz"]];

  function updatePreview() {
    const kw = buildKeyword();
    preview.classList.remove("err");
    if (!kw) { preview.textContent = ""; return; }
    const parts = [kw];
    const price = $("realPrice").value, km = $("realKm").value, year = $("minYear").value;
    if (price) parts.push("≤ " + fmt(price) + " TL");
    if (km) parts.push("≤ " + fmt(km) + " km");
    if (year) parts.push(year + " ve sonrası");
    flagDefs.forEach(([id, label]) => { if ($(id).checked) parts.push(label); });
    preview.textContent = "Takip edilecek: " + parts.join(" · ");
  }
  flagDefs.forEach(([id]) => $(id).addEventListener("change", updatePreview));
  $("minYear").addEventListener("input", updatePreview);

  function formatNumberInput(input, hidden) {
    input.addEventListener("input", () => {
      const raw = input.value.replace(/\D/g, "").slice(0, 12);
      hidden.value = raw;
      input.value = raw ? Number(raw).toLocaleString("tr-TR") : "";
      updatePreview();
    });
  }
  formatNumberInput($("priceDisplay"), $("realPrice"));
  formatNumberInput($("kmDisplay"), $("realKm"));

  $("filterForm").addEventListener("submit", e => {
    const kw = buildKeyword();
    if (!kw) {
      e.preventDefault();
      preview.textContent = searchBox.value.trim()
        ? "Yazdığın aracı açılan listeden seç (veya “Listeden seç”i kullan)."
        : "Önce takip edilecek aracı seç.";
      preview.classList.add("err");
      searchBox.focus();
      return;
    }
    $("finalKeyword").value = kw;
    const btn = $("submitBtn");
    btn.disabled = true;
    btn.lastChild.textContent = " Ekleniyor…";
  });

  /* ---- Akıllı araç arama ---- */
  function norm(t) {
    return t.replace(/İ/g, "i").replace(/I/g, "ı").toLowerCase()
      .replace(/ı/g, "i").replace(/ş/g, "s").replace(/ç/g, "c").replace(/ğ/g, "g")
      .replace(/ö/g, "o").replace(/ü/g, "u").replace(/[-\/]/g, " ");
  }

  const searchIndex = [];
  Object.keys(carData).forEach(brand => {
    Object.keys(carData[brand]).forEach(series => {
      searchIndex.push({ brand, series, model: "Tüm Modeller", key: norm(brand + " " + series) });
      carData[brand][series].forEach(model => {
        if (model === "Tüm Modeller") return;
        searchIndex.push({ brand, series, model, key: norm(brand + " " + series + " " + model) });
      });
    });
  });

  function searchCars(query, limit) {
    const tokens = norm(query).split(/\s+/).filter(Boolean);
    if (!tokens.length) return [];
    const found = [];
    for (const e of searchIndex) {
      let score = 0, ok = true;
      for (const tk of tokens) {
        const at = e.key.indexOf(tk);
        if (at < 0) { ok = false; break; }
        score += (at === 0 || e.key[at - 1] === " ") ? 0 : 1;
      }
      if (ok) found.push({ e, score });
    }
    found.sort((a, b) => a.score - b.score || a.e.key.length - b.e.key.length);
    return found.slice(0, limit).map(f => f.e);
  }

  let activeIdx = -1, shown = [];

  function closeList() {
    searchList.classList.remove("open");
    searchBox.setAttribute("aria-expanded", "false");
    searchBox.removeAttribute("aria-activedescendant");
    activeIdx = -1;
  }

  function setActive(i) {
    const items = searchList.querySelectorAll("li[data-i]");
    items.forEach(li => li.setAttribute("aria-selected", "false"));
    activeIdx = i;
    if (i >= 0 && items[i]) {
      items[i].setAttribute("aria-selected", "true");
      items[i].scrollIntoView({ block: "nearest" });
      searchBox.setAttribute("aria-activedescendant", items[i].id);
    }
  }

  function renderList() {
    const q = searchBox.value.trim();
    if (!q || searchBox.classList.contains("picked")) { closeList(); return; }
    shown = searchCars(q, 10);
    searchList.innerHTML = "";
    if (!shown.length) {
      const li = document.createElement("li");
      li.className = "none";
      li.textContent = "Sonuç yok. Marka, seri veya motoru farklı yazmayı dene.";
      searchList.appendChild(li);
    } else {
      shown.forEach((e, i) => {
        const li = document.createElement("li");
        li.id = "opt-" + i;
        li.setAttribute("role", "option");
        li.setAttribute("data-i", i);
        li.setAttribute("aria-selected", "false");
        li.innerHTML = `<span>${esc(e.brand + " " + e.series)}</span><span class="sub">${esc(e.model === "Tüm Modeller" ? "Tüm modeller" : e.model)}</span>`;
        li.addEventListener("mousedown", ev => { ev.preventDefault(); pickCar(e); });
        searchList.appendChild(li);
      });
    }
    searchList.classList.add("open");
    searchBox.setAttribute("aria-expanded", "true");
    activeIdx = -1;
  }

  function pickCar(e) {
    brandSelect.value = e.brand;
    brandSelect.dispatchEvent(new Event("change"));
    seriesSelect.value = e.series;
    seriesSelect.dispatchEvent(new Event("change"));
    modelSelect.value = e.model;
    modelSelect.dispatchEvent(new Event("change"));
    closeList();
    $("priceDisplay").focus();
  }

  searchBox.addEventListener("input", () => {
    // Seçilmiş araç varken yazmaya başlanırsa seçim bırakılır, yeniden aranır
    if (searchBox.classList.contains("picked")) {
      const typed = searchBox.value;
      brandSelect.value = "";
      brandSelect.dispatchEvent(new Event("change"));
      searchBox.value = typed;
    }
    clearBtn.hidden = !searchBox.value;
    renderList();
  });
  searchBox.addEventListener("focus", renderList);
  searchBox.addEventListener("blur", closeList);
  searchBox.addEventListener("keydown", ev => {
    const open = searchList.classList.contains("open") && shown.length;
    if (ev.key === "ArrowDown" && open) { ev.preventDefault(); setActive((activeIdx + 1) % shown.length); }
    else if (ev.key === "ArrowUp" && open) { ev.preventDefault(); setActive((activeIdx - 1 + shown.length) % shown.length); }
    else if (ev.key === "Enter") {
      ev.preventDefault();
      if (open) pickCar(shown[activeIdx >= 0 ? activeIdx : 0]);
    }
    else if (ev.key === "Escape") closeList();
  });

  /* ================= İlan listesi ================= */
  const PAGE = 15;
  const state = { all: initial.listings || [], view: "all", sort: "new", q: "", limit: PAGE, newIds: new Set() };

  // SQLite CURRENT_TIMESTAMP UTC'dir: "2026-11-12 08:38:43"
  const toDate = s => s ? new Date(s.replace(" ", "T") + "Z") : null;
  const isToday = d => d && d.toDateString() === new Date().toDateString();

  function ago(d) {
    if (!d) return "";
    const s = Math.max(0, (Date.now() - d.getTime()) / 1000);
    if (s < 60) return "az önce";
    if (s < 3600) return Math.floor(s / 60) + " dk önce";
    if (s < 86400) return Math.floor(s / 3600) + " saat önce";
    if (s < 86400 * 7) return Math.floor(s / 86400) + " gün önce";
    return d.toLocaleDateString("tr-TR", { day: "numeric", month: "short", year: "numeric" });
  }

  // damage_info metnini renkli rozetlere çevir
  function damageBadges(info) {
    const t = (info || "").toLocaleLowerCase("tr");
    const out = [];
    const agir = t.match(/ağır hasar:\s*(evet|hayır|belirtilmemiş)/);
    if (agir) {
      if (agir[1] === "evet") out.push(["bad", "Ağır hasar kayıtlı"]);
      else if (agir[1] === "hayır") out.push(["good", "Ağır hasar yok"]);
      else out.push(["", "Ağır hasar belirtilmemiş"]);
    }
    const boya = t.match(/boya-değişen:\s*([^|]+)/);
    if (boya) {
      const v = boya[1].trim();
      if (/tamamı/.test(v)) out.push(["good", "Tamamı orijinal"]);
      else if (/belirtilmemiş/.test(v)) out.push(["", "Boya-değişen belirtilmemiş"]);
      else out.push(["warn", v]);
    }
    if (!out.length) {
      if (/ağır hasarlı/.test(t)) out.push(["bad", "Ağır hasarlı (başlıkta)"]);
      else if (/hatasız|boyasız/.test(t)) out.push(["good", "Hatasız (başlıkta)"]);
      else if (/değişensiz/.test(t)) out.push(["good", "Değişensiz (başlıkta)"]);
      else if (/hasarlı/.test(t)) out.push(["warn", "Hasarlı (başlıkta)"]);
    }
    return out;
  }

  const safeUrl = u => /^https:\/\/(www\.)?arabam\.com\//.test(u || "") ? u : null;
  const ICON = {
    cal: '<svg viewBox="0 0 24 24"><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/></svg>',
    road: '<svg viewBox="0 0 24 24"><path d="M5 21 9 3M19 21 15 3M12 6v2M12 11v2M12 16v2"/></svg>',
    pin: '<svg viewBox="0 0 24 24"><path d="M12 21s7-6.5 7-12a7 7 0 0 0-14 0c0 5.5 7 12 7 12z"/><circle cx="12" cy="9" r="2.5"/></svg>',
    clock: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>',
  };

  function card(ad, i) {
    const url = safeUrl(ad.url);
    const d = toDate(ad.created_at);
    const fresh = d && Date.now() - d.getTime() < 3600e3;
    const tag = url ? "a" : "div";
    const attrs = url ? ` href="${esc(url)}" target="_blank" rel="noopener noreferrer"` : "";
    const badges = [];
    if (ad.is_deal) {
      const pct = ad.avg_price ? Math.round((1 - ad.price / ad.avg_price) * 100) : 0;
      badges.push(`<span class="badge fire">🔥 Fırsat${pct > 0 ? " · %" + pct + " ucuz" : ""}</span>`);
    }
    if (state.newIds.has(ad.id)) badges.push('<span class="badge new">Yeni geldi</span>');
    damageBadges(ad.damage_info).forEach(([k, txt]) => badges.push(`<span class="badge ${k}">${esc(txt)}</span>`));

    const meta = [];
    if (ad.year) meta.push(`<span>${ICON.cal}${ad.year}</span>`);
    if (ad.km) meta.push(`<span>${ICON.road}${fmt(ad.km)} km</span>`);
    if (ad.location && ad.location !== "Belirtilmemiş") meta.push(`<span>${ICON.pin}${esc(ad.location)}</span>`);

    const avgLine = ad.avg_price ? `<small>ort. ${fmt(ad.avg_price)} TL</small>` : "";
    return `<${tag} class="ad${ad.is_deal ? " deal" : ""}${fresh ? " fresh" : ""}"${attrs} style="animation-delay:${Math.min(i, 14) * 30}ms">
      <div class="ad-title">${esc(ad.title)}</div>
      <div class="ad-price"><b>${ad.price ? fmt(ad.price) + " TL" : "—"}</b>${avgLine}<small>${ICON.clock.replace("<svg", '<svg style="width:11px;height:11px;vertical-align:-1px"')} ${esc(ago(d))}</small></div>
      <div class="ad-meta">${meta.join("")}</div>
      ${badges.length ? `<div class="ad-badges">${badges.join("")}</div>` : ""}
    </${tag}>`;
  }

  const sorters = {
    new: (a, b) => (b.created_at || "").localeCompare(a.created_at || ""),
    cheap: (a, b) => (a.price || Infinity) - (b.price || Infinity),
    exp: (a, b) => (b.price || 0) - (a.price || 0),
    km: (a, b) => (a.km || Infinity) - (b.km || Infinity),
    year: (a, b) => (b.year || 0) - (a.year || 0),
  };

  function filtered() {
    const q = norm(state.q.trim());
    return state.all
      .filter(ad => state.view !== "deal" || ad.is_deal)
      .filter(ad => state.view !== "today" || isToday(toDate(ad.created_at)))
      .filter(ad => !q || norm([ad.title, ad.location, ad.damage_info, ad.year].join(" ")).includes(q))
      .sort(sorters[state.sort]);
  }

  function render() {
    const list = filtered();
    const box = $("listings");
    if (!state.all.length) {
      box.innerHTML = `<div class="empty"><div class="radar mini" aria-hidden="true"></div>Radar henüz ilan yakalamadı. Takip ekleyip botu (python main.py) çalıştır, uygun ilanlar burada belirir.</div>`;
    } else if (!list.length) {
      box.innerHTML = `<div class="empty">Bu süzgece uyan ilan yok.</div>`;
    } else {
      box.innerHTML = list.slice(0, state.limit).map(card).join("");
    }
    $("resultInfo").textContent = state.all.length
      ? `${fmt(Math.min(list.length, state.limit))} / ${fmt(list.length)} ilan gösteriliyor`
      : "";
    const more = $("moreBtn");
    more.hidden = list.length <= state.limit;
    more.textContent = `Daha fazla göster (${fmt(list.length - state.limit)} kaldı)`;
    updateHeader();
  }

  function updateHeader() {
    $("stToday").textContent = fmt(state.all.filter(a => isToday(toDate(a.created_at))).length);
    const newest = state.all.map(a => toDate(a.created_at)).filter(Boolean).sort((a, b) => b - a)[0];
    $("lastSeen").textContent = "Son ilan: " + (newest ? ago(newest) : "—");
  }

  let qTimer;
  $("q").addEventListener("input", e => {
    clearTimeout(qTimer);
    qTimer = setTimeout(() => { state.q = e.target.value; state.limit = PAGE; render(); }, 120);
  });
  $("sort").addEventListener("change", e => { state.sort = e.target.value; state.limit = PAGE; render(); });
  document.querySelectorAll(".seg button").forEach(b => b.addEventListener("click", () => {
    document.querySelectorAll(".seg button").forEach(x => { x.classList.toggle("on", x === b); x.setAttribute("aria-selected", x === b); });
    state.view = b.dataset.view; state.limit = PAGE; render();
  }));
  $("moreBtn").addEventListener("click", () => { state.limit += PAGE; render(); });

  /* ---- Sayaçlar 0'dan yükselsin ---- */
  function countUp(el, target, suffix = "") {
    if (matchMedia("(prefers-reduced-motion: reduce)").matches) { el.textContent = fmt(target) + suffix; return; }
    const t0 = performance.now(), dur = 900;
    (function step(now) {
      const p = Math.min((now - t0) / dur, 1);
      el.textContent = fmt(target * (1 - Math.pow(1 - p, 3))) + suffix;
      if (p < 1) requestAnimationFrame(step);
    })(t0);
  }
  const numOf = el => Number(el.textContent.replace(/\D/g, "")) || 0;
  countUp($("stTotal"), numOf($("stTotal")));
  countUp($("stDeals"), numOf($("stDeals")));
  countUp($("stAvg"), numOf($("stAvg")), " TL");

  /* ---- Dakikada bir yeni ilanları çek (sayfa yenilemeden) ---- */
  function setStat(id, value, suffix = "") {
    const el = $(id), text = fmt(value) + suffix;
    if (el.textContent !== text) { el.textContent = text; el.classList.remove("bump"); void el.offsetWidth; el.classList.add("bump"); }
  }

  async function refresh() {
    try {
      const r = await fetch("/api/listings", { headers: { Accept: "application/json" }, cache: "no-store" });
      if (!r.ok) return;
      const data = await r.json();
      const known = new Set(state.all.map(a => a.id));
      const fresh = data.listings.filter(a => !known.has(a.id));
      state.all = data.listings;
      setStat("stTotal", data.stats.total);
      setStat("stDeals", data.stats.deals);
      setStat("stAvg", data.stats.avg_price, " TL");
      if (fresh.length) {
        fresh.forEach(a => state.newIds.add(a.id));
        const deals = fresh.filter(a => a.is_deal).length;
        toast(`${fresh.length} yeni ilan yakalandı${deals ? ` (${deals} fırsat)` : ""}`, "good", {
          label: "Göster",
          run: () => { $("listings").scrollIntoView({ behavior: "smooth", block: "start" }); },
        });
        document.title = `(${state.newIds.size}) Oto Radar`;
      }
      render();
    } catch (_) { /* panel kapalıysa sessizce geç */ }
  }
  setInterval(refresh, 60000);
  setInterval(updateHeader, 30000);
  window.addEventListener("focus", () => { document.title = "Oto Radar"; });

  render();
})();
