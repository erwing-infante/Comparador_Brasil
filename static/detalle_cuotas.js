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

function getLogo(bookmaker) {
    return BOOKMAKER_LOGOS[bookmaker] || null;
}

function buildRankedList(rows, key) {
    const out = [];

    rows.forEach(r => {
        const value = parseFloat(r[key]);
        if (!Number.isFinite(value)) return;

        out.push({
            bookmaker: r.bookmaker || "-",
            odd: value
        });
    });

    out.sort((a, b) => b.odd - a.odd);
    return out;
}

function renderOddWithLogo(item, isBest = false) {
    const logo = getLogo(item.bookmaker);

    return `
        <div class="ranked-odd-item ${isBest ? 'is-best' : ''}">
            <span class="ranked-odd-value">${fmtOdd(item.odd)}</span>
            ${
                logo
                    ? `<img class="ranked-odd-logo" src="${logo}" alt="${item.bookmaker}" title="${item.bookmaker}">`
                    : `<span class="ranked-odd-text" title="${item.bookmaker}">${item.bookmaker}</span>`
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

        const localRank = buildRankedList(rows, "home");
        const drawRank  = buildRankedList(rows, "draw");
        const awayRank  = buildRankedList(rows, "away");

        const maxRows = Math.max(localRank.length, drawRank.length, awayRank.length);

        if (!maxRows) {
            tbody.innerHTML = `<tr><td colspan="3" class="empty-state">No hay cuotas válidas para mostrar</td></tr>`;
            return;
        }

        tbody.innerHTML = "";

        for (let i = 0; i < maxRows; i++) {
            const tr = document.createElement("tr");

            const localItem = localRank[i];
            const drawItem = drawRank[i];
            const awayItem = awayRank[i];

            const tdLocal = document.createElement("td");
            const tdDraw = document.createElement("td");
            const tdAway = document.createElement("td");

            tdLocal.innerHTML = localItem
                ? renderOddWithLogo(localItem, i === 0)
                : `<span class="empty-state">-</span>`;

            tdDraw.innerHTML = drawItem
                ? renderOddWithLogo(drawItem, i === 0)
                : `<span class="empty-state">-</span>`;

            tdAway.innerHTML = awayItem
                ? renderOddWithLogo(awayItem, i === 0)
                : `<span class="empty-state">-</span>`;

            tr.appendChild(tdLocal);
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