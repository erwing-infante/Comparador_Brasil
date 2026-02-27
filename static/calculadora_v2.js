function parseQuery() {
    const params = {};
    const q = window.location.search.substring(1).split('&');
    for (const part of q) {
        if (!part) continue;
        const [k, v] = part.split('=');
        const cleaned = (v || '').replace(/\+/g, ' ');
        params[decodeURIComponent(k)] = decodeURIComponent(cleaned);
    }
    return params;
}

function fnum(v) {
    const x = parseFloat(v);
    return Number.isFinite(x) ? x : 0;
}

/* ===========================
   ✅ NORMALIZACIÓN DE CASAS
   =========================== */

function slugifyBook(s) {
    return String(s || "")
        .trim()
        .toLowerCase()
        .normalize("NFD")
        .replace(/[\u0300-\u036f]/g, "")   // quita tildes
        .replace(/[^a-z0-9]+/g, "");      // deja solo a-z0-9
}

// Mapa de nombres "sucios" -> nombre canon
const BOOK_CANON = {
    "apuestatotal": "Apuesta Total",
    "atlanticcity": "Atlantic City",
    "doradobet": "DoradoBet",
    "olimpobet": "OlimpoBet",
    "teapuesto": "Te Apuesto",
    "betano": "Betano",
    "bet365": "Bet365",
    "gangabet": "GangaBet",
    "inkabet": "InkaBet",
    "1xbet": "1xBet",
    "betsson": "Betsson",
    "betsafe": "Betsafe",
    "pinnacle": "Pinnacle",
};

// fuentes que NO son casas (para excluir)
const BOOK_BLOCKLIST = new Set([
    "oddsapi",
    "theoddsapi",
    "odds-api",
    "oddsapio",
    "api",
    "orbitx",
    "betwatch",
]);

function canonicalBook(name) {
    const raw = String(name || "").trim();
    if (!raw) return "";

    const slug = slugifyBook(raw);
    if (!slug) return "";

    if (BOOK_BLOCKLIST.has(slug)) return ""; // ignorar

    // si lo tenemos mapeado, devolvemos canon
    if (BOOK_CANON[slug]) return BOOK_CANON[slug];

    // si no está mapeado, lo devolvemos "bonito" (Title-ish)
    // pero SIN inventar nada raro
    return raw;
}

function uniqueBooks(list) {
    const map = new Map(); // slug -> canon
    for (const item of list || []) {
        const canon = canonicalBook(item);
        if (!canon) continue;
        const slug = slugifyBook(canon);
        if (!slug) continue;
        if (!map.has(slug)) map.set(slug, canon);
    }
    return Array.from(map.values());
}

/* ===========================
   ✅ BOOKS BASE
   =========================== */

let BOOKS = uniqueBooks([
    "Apuesta Total",
    "Atlantic City",
    "DoradoBet",
    "OlimpoBet",
    "Te Apuesto",
    "Betano",
    "Bet365",
    "GangaBet",
    "InkaBet",
    "1xBet",
    "Betsson",
    "Betsafe",
    "Pinnacle",
    "Stake",
    "Orbitx",
]);

async function tryLoadBooksFromApi() {
    try {
        const res = await fetch("/api/cuotas", { cache: "no-store" });
        if (!res.ok) return null;
        const data = await res.json();
        if (!data || typeof data !== "object") return null;

        const md = data.metadata || {};
        const candidates = [
            md.sources_ok,
            md.fuentes_ok,
            md.sources,
            md.fuentes,
            md.bookmakers,
            md.casas,
        ];

        for (const c of candidates) {
            if (Array.isArray(c) && c.length) {
                return c.map(x => String(x || "").trim()).filter(Boolean);
            }
        }
        return null;
    } catch (e) {
        return null;
    }
}

function fillBookSelect(selectEl) {
    selectEl.innerHTML = "";

    const opt0 = document.createElement("option");
    opt0.value = "";
    opt0.textContent = "Selecciona...";
    selectEl.appendChild(opt0);

    // opcional: ordenar alfabético
    const sorted = [...BOOKS].sort((a, b) => a.localeCompare(b, "es"));

    for (const b of sorted) {
        const opt = document.createElement("option");
        opt.value = b;
        opt.textContent = b;
        selectEl.appendChild(opt);
    }
}

function setupBookPicker(side) {
    const sel = document.getElementById(`${side}-book-select`);
    fillBookSelect(sel);

    sel.addEventListener("change", () => window.__MB_RECALC && window.__MB_RECALC());

    return {
        getValue: () => (sel.value || "").trim(),
        setValue: (v) => {
            const canon = canonicalBook(v);
            if (!canon) {
                sel.value = "";
                return;
            }
            // si no existe, lo agregamos pero canonicalizado y dedupe
            const merged = uniqueBooks([...BOOKS, canon]);
            BOOKS = merged;
            fillBookSelect(sel);
            sel.value = canon;
        }
    };
}

function parseUtcDateFromString(dateStr) {
    const s = (dateStr || "").trim();
    if (!s) return null;

    const cleaned = s.replace("UTC", "").trim();
    const parts = cleaned.split(" ");
    if (parts.length >= 2) {
        const yyyy_mm_dd = parts[0];
        const hh_mm = parts[1];
        const ss = (hh_mm.split(":").length === 2) ? ":00" : "";
        const iso = `${yyyy_mm_dd}T${hh_mm}${ss}Z`;
        const d = new Date(iso);
        return isNaN(d.getTime()) ? null : d;
    }
    return null;
}

function formatGMTMinus5(utcDate) {
    const ms = utcDate.getTime() - (5 * 60 * 60 * 1000);
    const d = new Date(ms);

    const yyyy = d.getUTCFullYear();
    const mm = String(d.getUTCMonth() + 1).padStart(2, "0");
    const dd = String(d.getUTCDate()).padStart(2, "0");
    const hh = String(d.getUTCHours()).padStart(2, "0");
    const mi = String(d.getUTCMinutes()).padStart(2, "0");

    return `${yyyy}-${mm}-${dd} ${hh}:${mi} (GMT-5)`;
}

function createExtraRow() {
    const rowWrap = document.createElement("div");
    rowWrap.style.marginTop = "6px";
    rowWrap.style.marginBottom = "10px";
    rowWrap.style.padding = "6px";
    rowWrap.style.border = "1px solid #ddd";
    rowWrap.style.borderRadius = "6px";
    rowWrap.style.background = "#fff";

    // Casa
    const r1 = document.createElement("div");
    r1.className = "calc-row";
    const l1 = document.createElement("label");
    l1.textContent = "Casa";

    const pickerBox = document.createElement("div");
    pickerBox.className = "book-picker";

    const sel = document.createElement("select");
    fillBookSelect(sel);

    pickerBox.appendChild(sel);

    r1.appendChild(l1);
    r1.appendChild(pickerBox);

    // Cuota
    const r2 = document.createElement("div");
    r2.className = "calc-row";
    const l2 = document.createElement("label");
    l2.textContent = "Cuota";
    const inOdd = document.createElement("input");
    inOdd.type = "number";
    inOdd.step = "0.0001";
    inOdd.min = "1";
    r2.appendChild(l2);
    r2.appendChild(inOdd);

    // Apuesta
    const r3 = document.createElement("div");
    r3.className = "calc-row";
    const l3 = document.createElement("label");
    l3.textContent = "Apuesta";
    const inStake = document.createElement("input");
    inStake.type = "number";
    inStake.step = "0.01";
    inStake.min = "0";
    inStake.value = "0";
    inStake.className = "stake-input";

    const delBtn = document.createElement("button");
    delBtn.type = "button";
    delBtn.textContent = "×";
    delBtn.style.marginLeft = "8px";
    delBtn.style.border = "1px solid #ccc";
    delBtn.style.borderRadius = "4px";
    delBtn.style.padding = "2px 10px";
    delBtn.style.cursor = "pointer";
    delBtn.style.background = "#f3f3f3";

    r3.appendChild(l3);
    r3.appendChild(inStake);
    r3.appendChild(delBtn);

    rowWrap.appendChild(r1);
    rowWrap.appendChild(r2);
    rowWrap.appendChild(r3);

    rowWrap._get = () => ({
        book: canonicalBook(sel.value || ""),
        odd: fnum(inOdd.value),
        stake: fnum(inStake.value),
    });

    rowWrap._setStake = (v) => {
        inStake.value = (Number.isFinite(v) ? v : 0).toFixed(2);
    };

    [inOdd, inStake].forEach(el => {
        el.addEventListener("input", () => window.__MB_RECALC && window.__MB_RECALC());
        el.addEventListener("change", () => window.__MB_RECALC && window.__MB_RECALC());
        el.addEventListener("blur", () => window.__MB_RECALC && window.__MB_RECALC());
    });

    sel.addEventListener("change", () => window.__MB_RECALC && window.__MB_RECALC());

    delBtn.addEventListener("click", () => {
        rowWrap.remove();
        window.__MB_RECALC && window.__MB_RECALC();
    });

    return rowWrap;
}

function getExtraRows(side) {
    const box = document.getElementById(`${side}-extra`);
    if (!box) return [];
    return Array.from(box.children).filter(x => typeof x._get === "function");
}

function sidePayout(baseOdd, baseStake, extraRows) {
    let P = (baseOdd > 0 ? baseOdd * baseStake : 0);
    for (const r of extraRows) {
        const g = r._get();
        if (g.odd > 0) P += g.odd * g.stake;
    }
    return P;
}

function sideStakeTotal(baseStake, extraRows) {
    let T = baseStake;
    for (const r of extraRows) T += r._get().stake;
    return T;
}

function distributeSideToTarget(Pside, baseOdd, baseStakeEl, extraRows) {
    const bets = [];

    if (baseOdd > 0) {
        bets.push({ odd: baseOdd, setStake: (v) => baseStakeEl.value = v.toFixed(2) });
    } else {
        baseStakeEl.value = "0.00";
    }

    for (const r of extraRows) {
        const g = r._get();
        if (g.odd > 0) bets.push({ odd: g.odd, setStake: (v) => r._setStake(v) });
        else r._setStake(0);
    }

    const N = bets.length || 1;
    for (const b of bets) {
        const st = (Pside / N) / b.odd;
        b.setStake(st);
    }
}

async function postJson(url, payload) {
    const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
    });
    const data = await res.json().catch(() => ({}));
    return { ok: res.ok, status: res.status, data };
}

document.addEventListener('DOMContentLoaded', async () => {
    // ✅ Merge books desde API y dedupe canon
    const apiBooks = await tryLoadBooksFromApi();
    if (apiBooks && apiBooks.length) {
        BOOKS = uniqueBooks([...BOOKS, ...apiBooks]);
    }

    const qs = parseQuery();

    const role = (window.MB_ROLE || "viewer").toLowerCase();
    const user = (window.MB_USER || "").trim();

    const badge = document.getElementById("user-badge");
    if (badge) {
        badge.style.display = "";
        badge.textContent = user ? `Logueado como: ${user} (${role})` : `Logueado (${role})`;
    }

    const registerBtn = document.getElementById("register-btn");
    const opsLink = document.getElementById("ops-link");

    if (role === "owner") {
        if (registerBtn) registerBtn.style.display = "";
        if (opsLink) opsLink.style.display = "";
    }

    const matchName = document.getElementById('match-name');
    const leagueDate = document.getElementById('match-league-date');

    const name  = qs.name  || '';
    const date  = qs.date  || '';
    const league = qs.league || '';

    if (matchName) matchName.textContent = name || 'Partido';

    const utcD = parseUtcDateFromString(date);
    const datePe = utcD ? formatGMTMinus5(utcD) : date;
    if (leagueDate) leagueDate.textContent = (league ? league + ' · ' : '') + (datePe || '');

    const homePicker = setupBookPicker("home");
    const drawPicker = setupBookPicker("draw");
    const awayPicker = setupBookPicker("away");

    const homeOddInput = document.getElementById('home-odd');
    const drawOddInput = document.getElementById('draw-odd');
    const awayOddInput = document.getElementById('away-odd');

    const homeStake = document.getElementById('home-stake');
    const drawStake = document.getElementById('draw-stake');
    const awayStake = document.getElementById('away-stake');

    const totalPayoutInput = document.getElementById('total-payout');

    const homeProfitSpan = document.getElementById('home-profit');
    const drawProfitSpan = document.getElementById('draw-profit');
    const awayProfitSpan = document.getElementById('away-profit');

    const guaranteedProfitSpan = document.getElementById('guaranteed-profit');
    const totalInvestSpan = document.getElementById('total-invest');

    const modes = {
        home:  { D: document.getElementById('homeD'),  F: document.getElementById('homeF') },
        draw:  { D: document.getElementById('drawD'),  F: document.getElementById('drawF') },
        away:  { D: document.getElementById('awayD'),  F: document.getElementById('awayF') },
        total: { D: document.getElementById('totalD'), F: document.getElementById('totalF') }
    };

    function setExclusiveF(activeKey) {
        for (const key of Object.keys(modes)) {
            if (!modes[key].F) continue;
            if (key === activeKey) modes[key].F.checked = true;
            else modes[key].D.checked = true;
        }
    }

    for (const [key, pair] of Object.entries(modes)) {
        if (!pair.F || !pair.D) continue;
        pair.F.addEventListener('change', () => {
            if (pair.F.checked) {
                setExclusiveF(key);
                recalc();
            }
        });
        pair.D.addEventListener('change', recalc);
    }

    function currentMode() {
        if (modes.total.F && modes.total.F.checked) return { type: 'total' };
        if (modes.home.F && modes.home.F.checked)  return { type: 'side', side: 'home' };
        if (modes.draw.F && modes.draw.F.checked)  return { type: 'side', side: 'draw' };
        if (modes.away.F && modes.away.F.checked)  return { type: 'side', side: 'away' };
        return { type: 'none' };
    }

    function recalc() {
        const mode = currentMode();

        const oHome = fnum(homeOddInput.value);
        const oDraw = fnum(drawOddInput.value);
        const oAway = fnum(awayOddInput.value);

        const sHome = fnum(homeStake.value);
        const sDraw = fnum(drawStake.value);
        const sAway = fnum(awayStake.value);

        const homeExtras = getExtraRows("home");
        const drawExtras = getExtraRows("draw");
        const awayExtras = getExtraRows("away");

        let P = fnum(totalPayoutInput.value);
        if (mode.type === "none") {
            if (P <= 0) P = 100;
        }

        if (mode.type === "side") {
            if (mode.side === "home") P = sidePayout(oHome, sHome, homeExtras);
            if (mode.side === "draw") P = sidePayout(oDraw, sDraw, drawExtras);
            if (mode.side === "away") P = sidePayout(oAway, sAway, awayExtras);
        }

        if (mode.type === "total") {
            if (P <= 0) return;
        }

        if (!(mode.type === "side" && mode.side === "home")) distributeSideToTarget(P, oHome, homeStake, homeExtras);
        if (!(mode.type === "side" && mode.side === "draw")) distributeSideToTarget(P, oDraw, drawStake, drawExtras);
        if (!(mode.type === "side" && mode.side === "away")) distributeSideToTarget(P, oAway, awayStake, awayExtras);

        const sHome2 = fnum(homeStake.value);
        const sDraw2 = fnum(drawStake.value);
        const sAway2 = fnum(awayStake.value);

        const T = sideStakeTotal(sHome2, homeExtras) + sideStakeTotal(sDraw2, drawExtras) + sideStakeTotal(sAway2, awayExtras);
        const B = P - T;

        totalPayoutInput.value = P.toFixed(2);

        homeProfitSpan.textContent = B.toFixed(2);
        drawProfitSpan.textContent = B.toFixed(2);
        awayProfitSpan.textContent = B.toFixed(2);

        guaranteedProfitSpan.textContent = B.toFixed(2);
        totalInvestSpan.textContent = T.toFixed(2);

        const roi = T > 0 ? (B / T) * 100 : 0;
        document.getElementById("roi-label").textContent = roi.toFixed(3) + "%";
    }

    window.__MB_RECALC = recalc;

    // ✅ Canon al setear desde querystring
    homePicker.setValue(qs.homeBook || "");
    drawPicker.setValue(qs.drawBook || "");
    awayPicker.setValue(qs.awayBook || "");

    homeOddInput.value = qs.homeOdd || "";
    drawOddInput.value = qs.drawOdd || "";
    awayOddInput.value = qs.awayOdd || "";

    document.getElementById("home-add").addEventListener("click", () => {
        document.getElementById("home-extra").appendChild(createExtraRow());
        recalc();
    });
    document.getElementById("draw-add").addEventListener("click", () => {
        document.getElementById("draw-extra").appendChild(createExtraRow());
        recalc();
    });
    document.getElementById("away-add").addEventListener("click", () => {
        document.getElementById("away-extra").appendChild(createExtraRow());
        recalc();
    });

    [
        homeOddInput, drawOddInput, awayOddInput,
        homeStake, drawStake, awayStake,
        totalPayoutInput
    ].forEach(el => {
        if (!el) return;
        el.addEventListener('input', recalc);
        el.addEventListener('change', recalc);
        el.addEventListener('blur', recalc);
    });

    const msg = document.getElementById("register-msg");

    function buildLegList(person, mainBook, mainOdd, mainStake, extras) {
        const out = [];
        const canonMain = canonicalBook(mainBook);

        if (canonMain && fnum(mainOdd) > 1 && fnum(mainStake) > 0) {
            out.push({ person: person || "", book: canonMain, odd: fnum(mainOdd), stake: fnum(mainStake) });
        }

        for (const r of extras) {
            const g = r._get();
            if (g.book && g.odd > 1 && g.stake > 0) {
                out.push({ person: person || "", book: g.book, odd: g.odd, stake: g.stake });
            }
        }
        return out;
    }

    if (registerBtn) {
        registerBtn.addEventListener("click", async () => {
            if (role !== "owner") {
                msg.textContent = "❌ No tienes permisos para registrar (solo owner).";
                return;
            }

            registerBtn.disabled = true;
            msg.textContent = "Registrando...";

            const homePerson = (document.getElementById("home-person").value || "").trim();
            const drawPerson = (document.getElementById("draw-person").value || "").trim();
            const awayPerson = (document.getElementById("away-person").value || "").trim();

            const legs = {
                HOME: buildLegList(homePerson, homePicker.getValue(), homeOddInput.value, homeStake.value, getExtraRows("home")),
                DRAW: buildLegList(drawPerson, drawPicker.getValue(), drawOddInput.value, drawStake.value, getExtraRows("draw")),
                AWAY: buildLegList(awayPerson, awayPicker.getValue(), awayOddInput.value, awayStake.value, getExtraRows("away")),
            };

            for (const k of ["HOME", "DRAW", "AWAY"]) {
                if (!legs[k] || legs[k].length === 0) {
                    msg.textContent = `❌ Falta stake válido en ${k}. (cuota>1 y apuesta>0)`;
                    registerBtn.disabled = false;
                    return;
                }
            }

            const payload = {
                league: (league || "").trim(),
                name: (name || "").trim(),
                date_utc: (date || "").trim(),
                total_payout: fnum(totalPayoutInput.value),
                legs: legs
            };

            const res = await postJson("/admin/api/bets/register", payload);

            if (res.ok && res.data && res.data.ok) {
                msg.textContent = `✅ Operación registrada. ID: #${res.data.bet_id}`;
            } else {
                const err = (res.data && res.data.error) ? res.data.error : `HTTP ${res.status}`;
                msg.textContent = `❌ No se pudo registrar: ${err}`;
            }

            registerBtn.disabled = false;
        });
    }

    recalc();
});