const BOOKMAKER_LOGOS = {
    "Apuesta Total": "/static/img/bookmakers/apuestatotal.png",
    "Atlantic City": "/static/img/bookmakers/atlantic.png",
    "DoradoBet": "/static/img/bookmakers/doradobet.png",
    "1xbet": "/static/img/bookmakers/1xbet.png",
    "Betcris": "/static/img/bookmakers/betcris.png",
    "Bet365": "/static/img/bookmakers/bet365.png",
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

function getSortScore(row) {
    const vals = [parseFloat(row.home), parseFloat(row.draw), parseFloat(row.away)]
        .filter(v => Number.isFinite(v));
    if (!vals.length) return -999999;
    return Math.max(...vals);
}

function renderBookmakerCell(bookmaker) {
    const logo = BOOKMAKER_LOGOS[bookmaker] || null;
    if (logo) {
        return `
            <div class="bookmaker-cell">
                <img src="${logo}" alt="${bookmaker}">
                <span>${bookmaker}</span>
            </div>
        `;
    }
    return `
        <div class="bookmaker-cell">
            <span>${bookmaker || "-"}</span>
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
            tbody.innerHTML = `<tr><td colspan="5" class="empty-state">No se pudo cargar /api/cuotas</td></tr>`;
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
            tbody.innerHTML = `<tr><td colspan="5" class="empty-state">No se encontró el partido</td></tr>`;
            return;
        }

        let rows = Array.isArray(match.all_odds) ? [...match.all_odds] : [];

        if (!rows.length) {
            tbody.innerHTML = `<tr><td colspan="5" class="empty-state">Este partido no tiene detalle de cuotas</td></tr>`;
            return;
        }

        rows.sort((a, b) => getSortScore(b) - getSortScore(a));

        const bestHome = parseFloat(match.best_home?.odd || 0);
        const bestDraw = parseFloat(match.best_draw?.odd || 0);
        const bestAway = parseFloat(match.best_away?.odd || 0);

        tbody.innerHTML = "";

        rows.forEach((r, idx) => {
            const tr = document.createElement("tr");

            const homeVal = parseFloat(r.home);
            const drawVal = parseFloat(r.draw);
            const awayVal = parseFloat(r.away);

            tr.innerHTML = `
                <td><span class="rank-badge">${idx + 1}</span></td>
                <td>${renderBookmakerCell(r.bookmaker || "-")}</td>
                <td class="${homeVal === bestHome ? 'best-cell' : ''}">${fmtOdd(r.home)}</td>
                <td class="${drawVal === bestDraw ? 'best-cell' : ''}">${fmtOdd(r.draw)}</td>
                <td class="${awayVal === bestAway ? 'best-cell' : ''}">${fmtOdd(r.away)}</td>
            `;

            tbody.appendChild(tr);
        });

    } catch (e) {
        console.error(e);
        tbody.innerHTML = `<tr><td colspan="5" class="empty-state">Error cargando detalle</td></tr>`;
    }
}

document.addEventListener("DOMContentLoaded", loadDetail);