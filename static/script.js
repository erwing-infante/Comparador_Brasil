let allData = {};
let currentLeague = null;
let showOnlySurebets = false;
let dateFilter = "all";

const BOOKMAKER_LOGOS = {
    "Apuesta Total": "/static/img/bookmakers/apuestatotal.png",
    "Atlantic City": "/static/img/bookmakers/atlantic.png",
    "DoradoBet": "/static/img/bookmakers/doradobet.png",
    "1xbet": "/static/img/bookmakers/1xbet.png",
    "Betcris": "/static/img/bookmakers/betcris.png",
    "Bet365": "/static/img/bookmakers/bet365.png",
    "Betsson": "/static/img/bookmakers/betsson.png",
    "Olimpobet": "/static/img/bookmakers/olimpobet.png",
    "Pinnacle": "/static/img/bookmakers/pinnacle.png"
};

// ================================
// 🟦 Cargar JSON desde backend
// ================================
async function fetchCuotas() {
    try {
        const res = await fetch('/api/cuotas', { credentials: "include" });
        if (!res.ok) {
            console.error("Error HTTP:", res.status);
            return;
        }

        allData = await res.json();

        if (allData.error) {
            console.warn("Sesión no autorizada o expirada.");
            return;
        }

        const ligas = Object.keys(allData).filter(k => k !== "metadata");
        console.log("🔍 Ligas detectadas:", ligas);

        renderMetadata();
        renderLeagues();

        if (!currentLeague && ligas.length > 0) {
            currentLeague = ligas[0];
            renderMatches(currentLeague);
        } else if (currentLeague) {
            renderMatches(currentLeague);
        }

    } catch (e) {
        console.error("Error al cargar cuotas:", e);
    }
}

// ================================
// METADATA
// ================================
function renderMetadata() {
    const meta = allData.metadata;
    if (!meta) return;

    document.getElementById("last-updated").textContent = meta.updated || "---";
    document.getElementById("fuentes-ok").textContent = meta.fuentes_ok?.join(", ") || "---";
    document.getElementById("fuentes-error").textContent = meta.fuentes_error?.join(", ") || "---";
}

// ================================
// Renderizar ligas
// ================================
function renderLeagues() {
    const leagueList = document.getElementById('league-list');
    leagueList.innerHTML = '';

    const leagueNames = Object.keys(allData).filter(key => key !== "metadata");

    if (leagueNames.length === 0) {
        leagueList.innerHTML = '<li>No hay ligas disponibles</li>';
        return;
    }

    leagueNames.forEach(leagueName => {
        const li = document.createElement('li');
        li.textContent = leagueName;

        if (leagueName === currentLeague) {
            li.classList.add('active');
        }

        li.addEventListener('click', () => {
            currentLeague = leagueName;
            renderMatches(leagueName);
            renderLeagues();
        });

        leagueList.appendChild(li);
    });
}

// ================================
// Renderizar partidos
// ================================
function renderMatches(leagueName) {
    const matchesTableBody = document.querySelector('#matches-table tbody');
    matchesTableBody.innerHTML = '';

    const leagueTitle = document.getElementById('league-title');
    leagueTitle.textContent = leagueName;

    const matches = allData[leagueName] || [];
    console.log(`📊 Partidos en ${leagueName}:`, matches);

    if (matches.length === 0) {
        matchesTableBody.innerHTML = `<tr><td colspan="7">No hay partidos disponibles</td></tr>`;
        return;
    }

    matches.forEach(match => {
        if (!isMatchInRange(match.date)) return;

        const h = parseFloat(match.best_home?.odd || 0);
        const d = parseFloat(match.best_draw?.odd || 0);
        const a = parseFloat(match.best_away?.odd || 0);

        let marginSure = null;
        if (h && d && a) {
            marginSure = 100 - ((1/h + 1/d + 1/a) * 100);
        }

        if (showOnlySurebets && !(marginSure > 0)) return;

        const row = document.createElement('tr');
        if (marginSure !== null && marginSure > 0) {
            row.classList.add("surebet-row");
        }

        row.appendChild(createCell(formatLocalDate(match.date)));
        row.appendChild(createCell(match.name));
        row.appendChild(createOddCell(match.best_home));
        row.appendChild(createOddCell(match.best_draw));
        row.appendChild(createOddCell(match.best_away));

        // Celda de calculadora
        const calcCell = document.createElement('td');
        const calcBtn = document.createElement('button');
        calcBtn.className = "calc-btn";
        calcBtn.title = "Calculadora de arbitraje";
        calcBtn.textContent = "🧮";
        calcBtn.addEventListener('click', (ev) => {
            ev.stopPropagation();
            openArb(match);
        });
        calcCell.appendChild(calcBtn);
        row.appendChild(calcCell);

        const lossCell = document.createElement('td');
        if (marginSure !== null) {
            lossCell.innerHTML = `<span style="color:${marginSure > 0 ? 'green' : 'red'}; font-weight:bold;">${marginSure.toFixed(3)}%</span>`;
        } else {
            lossCell.textContent = "-";
        }
        row.appendChild(lossCell);

        matchesTableBody.appendChild(row);
    });
}

function createCell(text) {
    const td = document.createElement('td');
    td.textContent = text || "-";
    return td;
}

function createOddCell(best) {
    const td = document.createElement('td');
    if (!best?.odd) {
        td.textContent = "-";
        return td;
    }

    const logoPath = BOOKMAKER_LOGOS[best.bookmaker] || null;
    td.innerHTML = `
        <span class="best-odd">${best.odd}</span><br>
        ${logoPath ? `<img src="${logoPath}" class="bm-logo">` : `<small>${best.bookmaker}</small>`}
    `;
    return td;
}

function formatLocalDate(dateStr) {
    if (!dateStr) return "-";
    let cleaned = dateStr.replace(" UTC", "").replace(" ", "T") + ":00Z";
    const date = new Date(cleaned);
    if (isNaN(date)) return "-";
    return date.toLocaleString("es-PE", {
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        hour: "numeric",
        minute: "2-digit",
        hour12: true
    });
}

function isMatchInRange(dateStr) {
    if (dateFilter === "all") return true;
    const date = new Date(dateStr.replace(" UTC", "").replace(" ", "T") + ":00Z");
    const now = new Date();
    const diff = (date - now) / (1000 * 60 * 60 * 24);
    if (dateFilter === "today") return diff >= 0 && diff < 1;
    if (dateFilter === "tomorrow") return diff >= 1 && diff < 2;
    if (dateFilter === "2d") return diff >= 0 && diff <= 2;
    if (dateFilter === "3d") return diff >= 0 && diff <= 3;
    return true;
}

// ================================
// MODO OSCURO
// ================================
const darkBtn = document.getElementById("dark-toggle");
if (darkBtn) {
    darkBtn.addEventListener("click", () => {
        document.body.classList.toggle("dark-mode");
        darkBtn.textContent = document.body.classList.contains("dark-mode")
            ? "Modo Claro"
            : "Modo Oscuro";
    });
}

// ================================
// SOLO SUREBETS
// ================================
const surebetBtn = document.getElementById("surebet-toggle");
if (surebetBtn) {
    surebetBtn.addEventListener("click", () => {
        showOnlySurebets = !showOnlySurebets;
        surebetBtn.classList.toggle("active");
        renderMatches(currentLeague);
    });
}

// ================================
// FILTRO DE FECHA
// ================================
const dateFilterSelect = document.getElementById("date-filter");
if (dateFilterSelect) {
    dateFilterSelect.addEventListener("change", (e) => {
        dateFilter = e.target.value;
        renderMatches(currentLeague);
    });
}

// ================================
// CALCULADORA DE ARBITRAJE
// ================================
function openArb(match) {
    const modal = document.getElementById("arbitrageModal");
    const title = document.getElementById("arbMatchTitle");
    const container = document.getElementById("arbContainer");

    title.textContent = match.name || "Arbitraje";
    container.innerHTML = "";

    const legs = [];

    if (match.best_home?.odd) {
        legs.push({
            market: "Local",
            bookmaker: match.best_home.bookmaker,
            odd: parseFloat(match.best_home.odd)
        });
    }
    if (match.best_draw?.odd) {
        legs.push({
            market: "Empate",
            bookmaker: match.best_draw.bookmaker,
            odd: parseFloat(match.best_draw.odd)
        });
    }
    if (match.best_away?.odd) {
        legs.push({
            market: "Visita",
            bookmaker: match.best_away.bookmaker,
            odd: parseFloat(match.best_away.odd)
        });
    }

    if (!legs.length) {
        container.innerHTML = "<p>No hay cuotas disponibles para este partido.</p>";
    } else {
        legs.forEach(leg => {
            const row = document.createElement("div");
            row.className = "arb-row";
            row.innerHTML = `
                <div>
                    <div class="arb-bm">${leg.bookmaker}</div>
                    <div class="arb-market">${leg.market}</div>
                </div>
                <div>
                    <label>Cuota</label>
                    <input type="number" class="arb-odd" step="0.01" value="${leg.odd.toFixed(3)}">
                </div>
                <div>
                    <label>Apuesta</label>
                    <input type="number" class="arb-stake" step="0.01">
                </div>
                <div>
                    <label>Beneficio</label>
                    <input type="text" class="arb-profit" readonly>
                </div>
            `;
            container.appendChild(row);
        });
    }

    // listeners para recalcular cuando cambien cuotas
    container.querySelectorAll(".arb-odd").forEach(inp => {
        inp.addEventListener("input", recalculateArb);
    });

    const totalInput = document.getElementById("arbTotalStake");
    totalInput.removeEventListener("input", recalculateArb); // por si acaso
    totalInput.addEventListener("input", recalculateArb);

    const currencySelect = document.getElementById("arbCurrency");
    currencySelect.removeEventListener("change", recalculateArb);
    currencySelect.addEventListener("change", recalculateArb);

    modal.style.display = "flex";
    recalculateArb();
}

function closeArb() {
    const modal = document.getElementById("arbitrageModal");
    if (modal) modal.style.display = "none";
}

function getCurrencySymbol() {
    const currency = document.getElementById("arbCurrency")?.value || "USD";
    if (currency === "PEN") return "S/";
    return "$";
}

function recalculateArb() {
    const total = parseFloat(document.getElementById("arbTotalStake").value || 0);
    const rows = document.querySelectorAll("#arbContainer .arb-row");

    if (!rows.length || !total || total <= 0) {
        document.getElementById("arbGuaranteedProfit").textContent = "--";
        return;
    }

    const rowData = [];
    rows.forEach(row => {
        const oddInp = row.querySelector(".arb-odd");
        const odd = parseFloat(oddInp.value || 0);
        if (odd > 0) {
            rowData.push({ row, odd });
        }
    });

    if (!rowData.length) {
        document.getElementById("arbGuaranteedProfit").textContent = "--";
        return;
    }

    const sumInverse = rowData.reduce((acc, item) => acc + (1 / item.odd), 0);
    let guaranteedProfit = null;

    rowData.forEach(item => {
        const stake = (total / item.odd) / sumInverse;
        const profit = stake * item.odd - total;

        item.row.querySelector(".arb-stake").value = stake.toFixed(2);
        item.row.querySelector(".arb-profit").value = profit.toFixed(2);

        if (guaranteedProfit === null) {
            guaranteedProfit = profit;
        }
    });

    if (guaranteedProfit !== null) {
        const symbol = getCurrencySymbol();
        document.getElementById("arbGuaranteedProfit").textContent =
            `${symbol}${guaranteedProfit.toFixed(2)}`;
    }
}

// AUTO UPDATE
setInterval(fetchCuotas, 120000);

// PRIMERA CARGA
fetchCuotas();
