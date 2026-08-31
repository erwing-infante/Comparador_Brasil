const BOOKMAKER_LOGOS = {
    "Apuesta Total": "/static/img/bookmakers/apuestatotal.png",
    "Atlantic City": "/static/img/bookmakers/atlantic.png",
    "DoradoBet": "/static/img/bookmakers/doradobet.png",
    "1xbet": "/static/img/bookmakers/1xbet.png",
    "Betcris": "/static/img/bookmakers/betcris.png",
    "Bet365": "/static/img/bookmakers/bet365.png",
    "Betsson": "/static/img/bookmakers/betsson1.png",
    "Betsafe": "/static/img/bookmakers/betsafe.png",
    "Inkabet": "/static/img/bookmakers/inkabet1.png",
    "Coolbet": "/static/img/bookmakers/coolbet.png",
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

function buildRanking(rows, key) {
    const out = [];

    for (const r of rows) {
        const odd = parseFloat(r[key]);
        if (!Number.isFinite(odd)) continue;

        out.push({
            odd,
            bookmaker: r.bookmaker || "-"
        });
    }

    out.sort((a, b) => b.odd - a.odd);
    return out;
}

function renderCell(item, isBest) {
    const logo = getLogo(item.bookmaker);

    return `
        <div class="ranked-col-item">
            <span class="ranked-col-odd ${isBest ? 'best-cell' : ''}">${fmtOdd(item.odd)}</span>
            ${
                logo
                    ? `<img class="ranked-col-logo" src="${logo}" alt="${item.bookmaker}" title="${item.bookmaker}">`
                    : `<span class="ranked-col-book" title="${item.bookmaker}">${item.bookmaker}</span>`
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
        const res = await fetch("/api/cuotas-nopa", {
            credentials: "include",
            cache: "no-store"
        });

        if (!res.ok) {
            tbody.innerHTML = `<tr><td colspan="3" class="empty-state">No se pudo cargar /api/cuotas-nopa</td></tr>`;
            return;
        }

        const data = await res.json();
        const leagueMatches = data[qs.league] || [];

        const wantedId = String(qs.eventId || "").trim();
        const match = leagueMatches.find(m => {
            const id = String(m.eventId ?? m.EventId ?? m.event_id ?? "").trim();
            if (wantedId && id) return id === wantedId;
            return (m.name || "") === (qs.name || "") &&
                   (m.date || "") === (qs.date || "") &&
                   (m.home || "") === (qs.home || "") &&
                   (m.away || "") === (qs.away || "");
        });

        if (!match) {
            tbody.innerHTML = `<tr><td colspan="3" class="empty-state">No se encontró el partido</td></tr>`;
            return;
        }

        const rows = Array.isArray(match.all_odds) ? match.all_odds : [];

        if (!rows.length) {
            tbody.innerHTML = `<tr><td colspan="3" class="empty-state">Este partido no tiene detalle de cuotas</td></tr>`;
            return;
        }

        const homeRank = buildRanking(rows, "home");
        const drawRank = buildRanking(rows, "draw");
        const awayRank = buildRanking(rows, "away");

        const maxRows = Math.max(homeRank.length, drawRank.length, awayRank.length);

        tbody.innerHTML = "";

        for (let i = 0; i < maxRows; i++) {
            const tr = document.createElement("tr");

            const tdHome = document.createElement("td");
            const tdDraw = document.createElement("td");
            const tdAway = document.createElement("td");

            tdHome.innerHTML = homeRank[i]
                ? renderCell(homeRank[i], i === 0)
                : `<span class="empty-state">-</span>`;

            tdDraw.innerHTML = drawRank[i]
                ? renderCell(drawRank[i], i === 0)
                : `<span class="empty-state">-</span>`;

            tdAway.innerHTML = awayRank[i]
                ? renderCell(awayRank[i], i === 0)
                : `<span class="empty-state">-</span>`;

            tr.appendChild(tdHome);
            tr.appendChild(tdDraw);
            tr.appendChild(tdAway);

            tbody.appendChild(tr);
        }

    } catch (err) {
        console.error(err);
        tbody.innerHTML = `<tr><td colspan="3" class="empty-state">Error cargando detalle</td></tr>`;
    }
}

document.addEventListener("DOMContentLoaded", loadDetail);