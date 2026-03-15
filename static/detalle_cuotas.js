const BOOKMAKER_LOGOS = {
    "Apuesta Total": "/static/img/bookmakers/apuestatotal.png",
    "Atlantic City": "/static/img/bookmakers/atlantic.png",
    "DoradoBet": "/static/img/bookmakers/doradobet.png",
    "1xbet": "/static/img/bookmakers/1xbet.png",
    "Betcris": "/static/img/bookmakers/betcris.png",
    "Bet365": "/static/img/bookmakers/bet365.png",
    "Bet365 (no latency)": "/static/img/bookmakers/bet365.png",
    "Betsson": "/static/img/bookmakers/betsson.png",
    "Olimpobet": "/static/img/bookmakers/olimpobet.png",
    "Pinnacle": "/static/img/bookmakers/pinnacle.png",
    "GangaBet": "/static/img/bookmakers/gangabet.png",
    "TeApuesto": "/static/img/bookmakers/teapuesto.png",
    "Stake": "/static/img/bookmakers/stake.png",
    "Tinbet": "/static/img/bookmakers/tinbet.png",
    "Betano": "/static/img/bookmakers/betano.png"
};

function parseQuery() {
    const params = {};
    const query = new URLSearchParams(window.location.search);
    for (const [k, v] of query.entries()) {
        params[k] = v;
    }
    return params;
}

function fmtOdd(v) {
    const n = parseFloat(v);
    return Number.isFinite(n) ? n.toFixed(2) : "-";
}

function buildColumnRanking(rows, key) {
    const out = [];

    rows.forEach(r => {
        const odd = parseFloat(r[key]);
        if (!Number.isFinite(odd)) return;

        out.push({
            bookmaker: r.bookmaker || "-",
            odd: odd
        });
    });

    out.sort((a, b) => b.odd - a.odd);
    return out;
}

function renderCellContent(item, isBest = false) {
    const logo = BOOKMAKER_LOGOS[item.bookmaker] || null;

    return `
        <div class="ranked-col-item">
            <span class="ranked-col-odd ${isBest ? 'best-cell' : ''}">${fmtOdd(item.odd)}</span>
            ${
                logo
                    ? `<img class="ranked-col-logo" src="${logo}" alt="${item.bookmaker}" title="${item.bookmaker}">`
                    : `<span class="ranked-col-book">${item.bookmaker}</span>`
            }
        </div>
    `;
}

async function loadDetail() {
    const qs = parseQuery();

    const title = document.getElementById("match-title");
    const meta = document.getElementById("match-meta");
    const tbody = document.getElementById("odds-detail-body");

    title.textContent = qs.name || "Detalle de cuotas";
    meta.textContent = `${qs.league || ""} · ${qs.date || ""}`;

    try {
        const res = await fetch("/api/cuotas", { credentials: "include", cache: "no-store" });
        if (!res.ok) {
            tbody.innerHTML = `<tr><td colspan="3" class="empty-state">No se pudo cargar /api/cuotas</td></tr>`;
            return;
        }

        const data = await res.json();
        const leagueMatches = data[qs.league] || [];

        const match = leagueMatches.find(m =>
            (m.name || "") === (qs.name || "") &&
            (m.date || "") === (qs.date || "") &&
            (m.home || "") === (qs.home || "") &&
            (m.away || "") === (qs.away || "")
        );

        if (!match) {
            tbody.innerHTML = `<tr><td colspan="3" class="empty-state">No se encontró el partido</td></tr>`;
            return;
        }

        const rows = Array.isArray(match.all_odds) ? [...match.all_odds] : [];

        if (!rows.length) {
            tbody.innerHTML = `<tr><td colspan="3" class="empty-state">Este partido no tiene detalle de cuotas</td></tr>`;
            return;
        }

        const rankedHome = buildColumnRanking(rows, "home");
        const rankedDraw = buildColumnRanking(rows, "draw");
        const rankedAway = buildColumnRanking(rows, "away");

        const maxLen = Math.max(rankedHome.length, rankedDraw.length, rankedAway.length);

        if (!maxLen) {
            tbody.innerHTML = `<tr><td colspan="3" class="empty-state">No hay cuotas válidas</td></tr>`;
            return;
        }

        tbody.innerHTML = "";

        for (let i = 0; i < maxLen; i++) {
            const tr = document.createElement("tr");

            const tdHome = document.createElement("td");
            const tdDraw = document.createElement("td");
            const tdAway = document.createElement("td");

            if (rankedHome[i]) {
                tdHome.innerHTML = renderCellContent(rankedHome[i], i === 0);
            } else {
                tdHome.innerHTML = `<span class="empty-state">-</span>`;
            }

            if (rankedDraw[i]) {
                tdDraw.innerHTML = renderCellContent(rankedDraw[i], i === 0);
            } else {
                tdDraw.innerHTML = `<span class="empty-state">-</span>`;
            }

            if (rankedAway[i]) {
                tdAway.innerHTML = renderCellContent(rankedAway[i], i === 0);
            } else {
                tdAway.innerHTML = `<span class="empty-state">-</span>`;
            }

            tr.appendChild(tdHome);
            tr.appendChild(tdDraw);
            tr.appendChild(tdAway);

            tbody.appendChild(tr);
        }

    } catch (e) {
        console.error(e);
        tbody.innerHTML = `<tr><td colspan="3" class="empty-state">Error cargando detalle</td></tr>`;
    }
}

document.addEventListener("DOMContentLoaded", loadDetail);