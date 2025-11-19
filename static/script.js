let allData = {};
let currentLeague = null;
let showOnlySurebets = false;
let dateFilter = "all";

// MAPA DE LOGOS
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
// 🟩 CORRECCIÓN DE FECHA INVALIDA
// ================================
function formatLocalDate(dateStr) {
    if (!dateStr) return "-";

    // Convertir "2025-11-18 19:45 UTC" → "2025-11-18T19:45:00Z"
    let cleaned = dateStr
        .replace(" UTC", "")
        .replace(" ", "T") + ":00Z";

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

// ================================
// 🟦 Cargar JSON desde backend
// ================================
async function fetchCuotas() {
    try {
        const res = await fetch('/api/cuotas');
        allData = await res.json();

        renderMetadata();
        renderLeagues();

        if (currentLeague) {
            renderMatches(currentLeague);
        }
    } catch (e) {
        console.error("Error al cargar cuotas:", e);
    }
}

// Mostrar metadata
function renderMetadata() {
    const meta = allData.metadata;
    if (!meta) return;

    document.getElementById("last-updated").textContent = meta.updated || "---";
    document.getElementById("fuentes-ok").textContent = meta.fuentes_ok?.join(", ") || "---";
    document.getElementById("fuentes-error").textContent = meta.fuentes_error?.join(", ") || "---";
}

// ================================
// 🟦 Renderizar ligas
// ================================
function renderLeagues() {
    const leagueList = document.getElementById('league-list');
    leagueList.innerHTML = '';

    Object.keys(allData)
        .filter(key => key !== "metadata")
        .forEach(leagueName => {
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
// 🟩 FILTRO DE FECHAS
// ================================
function isMatchInRange(dateStr) {
    if (dateFilter === "all") return true;

    const date = new Date(
        dateStr.replace(" UTC", "").replace(" ", "T") + ":00Z"
    );
    const now = new Date();

    const diff = (date - now) / (1000 * 60 * 60 * 24); // días

    if (dateFilter === "today") return diff >= 0 && diff < 1;
    if (dateFilter === "tomorrow") return diff >= 1 && diff < 2;
    if (dateFilter === "2d") return diff >= 0 && diff <= 2;
    if (dateFilter === "3d") return diff >= 0 && diff <= 3;

    return true;
}

// ================================
// 🟦 Renderizar partidos
// ================================
function renderMatches(leagueName) {
    const matchesTableBody = document.querySelector('#matches-table tbody');
    matchesTableBody.innerHTML = '';

    const leagueTitle = document.getElementById('league-title');
    leagueTitle.textContent = leagueName;

    const matches = allData[leagueName] || [];

    if (matches.length === 0) {
        matchesTableBody.innerHTML = `<tr><td colspan="6">No hay partidos disponibles</td></tr>`;
        return;
    }

    matches.forEach(match => {

        // 🔵 FILTRO DE FECHA
        if (!isMatchInRange(match.date)) return;

        const row = document.createElement('tr');

        // ===== DETECTAR SUREBET =====
        const h = parseFloat(match.best_home.odd);
        const d = parseFloat(match.best_draw.odd);
        const a = parseFloat(match.best_away.odd);

        let marginSure = null;
        if (h && d && a) {
            marginSure = 100 - ((1/h + 1/d + 1/a) * 100);
        }

        // ⭐ MODO SOLO SUREBETS
        if (showOnlySurebets && !(marginSure > 0)) return;

        if (marginSure !== null && marginSure > 0) {
            row.classList.add("surebet-row");
        }

        // Fecha
        const dateCell = document.createElement('td');
        dateCell.textContent = formatLocalDate(match.date);
        row.appendChild(dateCell);

        // Partido
        const nameCell = document.createElement('td');
        nameCell.textContent = match.name;
        row.appendChild(nameCell);

        // Cuotas
        row.appendChild(createOddCell(match.best_home));
        row.appendChild(createOddCell(match.best_draw));
        row.appendChild(createOddCell(match.best_away));

        // % Margen
        const lossCell = document.createElement('td');

        if (marginSure !== null) {
            const color = marginSure > 0 ? 'green' : 'red';
            lossCell.innerHTML = `<span style="color:${color}; font-weight:bold;">${marginSure.toFixed(3)}%</span>`;
        } else {
            lossCell.textContent = "-";
        }

        row.appendChild(lossCell);
        matchesTableBody.appendChild(row);
    });
}

// Crear celda con cuota + logo
function createOddCell(best) {
    const td = document.createElement('td');

    if (!best.odd) {
        td.textContent = "-";
        return td;
    }

    const logoPath = BOOKMAKER_LOGOS[best.bookmaker] || null;

    td.innerHTML = `
        <span class="best-odd">${best.odd}</span><br>
        ${
            logoPath
                ? `<img src="${logoPath}" class="bm-logo">`
                : `<small>${best.bookmaker}</small>`
        }
    `;

    return td;
}

// 🌙 MODO OSCURO
document.getElementById("dark-toggle").addEventListener("click", () => {
    document.body.classList.toggle("dark-mode");

    const btn = document.getElementById("dark-toggle");
    btn.textContent = document.body.classList.contains("dark-mode")
        ? "Modo Claro"
        : "Modo Oscuro";
});

// ⭐ SOLO SUREBETS
document.getElementById("surebet-toggle").onclick = () => {
    showOnlySurebets = !showOnlySurebets;
    document.getElementById("surebet-toggle").classList.toggle("active");
    renderMatches(currentLeague);
};

// ⭐ FILTRO DE FECHA
document.getElementById("date-filter").onchange = (e) => {
    dateFilter = e.target.value;
    renderMatches(currentLeague);
};

// AUTO UPDATE 2 minutos
setInterval(fetchCuotas, 120000);

// PRIMERA CARGA
fetchCuotas();
