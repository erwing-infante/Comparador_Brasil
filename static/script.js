let allData = {};
let allDataNoPA = {};
let noPaByEventId = {};
let currentLeague = null;
let dateFilter = "all";

// ================================
// SNAPSHOT (BETWATCH)
// ================================
let snapshotByEventId = {};

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

// Icono SVG de calculadora
const CALC_ICON_SVG = `
<svg viewBox="0 0 24 24">
  <rect x="4" y="3" width="16" height="18" rx="2" ry="2" />
  <rect x="7" y="6" width="10" height="3" />
  <rect x="7" y="11" width="3" height="3" />
  <rect x="11" y="11" width="3" height="3" />
  <rect x="15" y="11" width="3" height="3" />
  <rect x="7" y="15" width="3" height="3" />
  <rect x="11" y="15" width="7" height="3" />
</svg>
`;

// Evita que dos actualizaciones se ejecuten al mismo tiempo
let fetchEnCurso = false;

// ================================
// SNAPSHOT (BETWATCH)
// ================================
async function fetchSnapshot() {
    try {
        const res = await fetch(
            "/static/data/snapshot.json?_=" + Date.now(),
            {
                cache: "no-store"
            }
        );

        if (!res.ok) return;

        const snap = await res.json();

        snapshotByEventId = {};

        const markets = Array.isArray(snap?.markets)
            ? snap.markets
            : [];

        for (const m of markets) {
            if (m?.eventId) {
                snapshotByEventId[String(m.eventId)] = m;
            }
        }

    } catch (e) {
        console.error("snapshot error:", e);
    }
}

function getSnapshotBackOdd(match, side) {

    const m =
        snapshotByEventId[String(match?.eventId || "")];

    if (!m?.runners) return null;

    for (const k of Object.keys(m.runners)) {

        const r = m.runners[k];

        if (r?.selection === side) {
            return r.best_back_odds ?? null;
        }
    }

    return null;
}


// ================================
// EventId
// ================================
function getEventId(match) {

    return String(
        match?.eventId ??
        match?.EventId ??
        match?.event_id ??
        ""
    ).trim();
}


// ================================
// ÍNDICE NoPA
// ================================
function buildNoPaIndex(data) {

    noPaByEventId = {};

    if (!data || typeof data !== "object") return;

    for (const [league, matches] of Object.entries(data)) {

        if (
            league === "metadata" ||
            !Array.isArray(matches)
        ) {
            continue;
        }

        for (const match of matches) {

            const id = getEventId(match);

            if (id) {
                noPaByEventId[id] = match;
            }
        }
    }
}


// ================================
// CARGAR CUOTAS NoPA
// ================================
async function fetchCuotasNoPA() {

    try {

        const res = await fetch(
            "/api/cuotas-nopa?_=" + Date.now(),
            {
                credentials: "include",
                cache: "no-store"
            }
        );

        if (!res.ok) return;

        const data = await res.json();

        if (data?.error) return;

        allDataNoPA = data;

        buildNoPaIndex(data);

    } catch (e) {

        console.error("Error NoPA:", e);
    }
}


// ================================
// CARGAR CUOTAS PRINCIPALES
// ================================
async function fetchCuotas() {

    // Si la actualización anterior todavía no terminó,
    // no iniciar otra encima.
    if (fetchEnCurso) return;

    fetchEnCurso = true;

    try {

        const res = await fetch(
            "/api/cuotas?_=" + Date.now(),
            {
                credentials: "include",
                cache: "no-store"
            }
        );

        if (!res.ok) return;

        const data = await res.json();

        if (data?.error) return;

        allData = data;

        // NoPA independiente
        await fetchCuotasNoPA();

        renderMetadata();

        renderLeagues();

        const ligas = Object.keys(allData)
            .filter(k => k !== "metadata");

        if (!currentLeague && ligas.length > 0) {
            currentLeague = ligas[0];
        }

        // Snapshot OrbitX / Betwatch
        await fetchSnapshot();

        renderMatches(currentLeague);

    } catch (e) {

        console.error("Error:", e);

    } finally {

        fetchEnCurso = false;
    }
}


// ================================
// METADATOS
// ================================
function renderMetadata() {

    const meta = allData.metadata;

    if (!meta) return;

    document.getElementById("last-updated").textContent =
        meta.updated || "---";

    document.getElementById("fuentes-ok").textContent =
        meta.fuentes_ok?.join(", ") || "---";

    document.getElementById("fuentes-error").textContent =
        meta.fuentes_error?.join(", ") || "---";
}


// ================================
// LIGAS
// ================================
function renderLeagues() {

    const list =
        document.getElementById("league-list");

    list.innerHTML = "";

    Object.keys(allData)
        .filter(k => k !== "metadata")
        .forEach(liga => {

            const li =
                document.createElement("li");

            li.textContent = liga;

            if (liga === currentLeague) {
                li.classList.add("active");
            }

            li.onclick = () => {

                currentLeague = liga;

                renderMatches(liga);

                renderLeagues();
            };

            list.appendChild(li);
        });
}


// ================================
// TABLA DE PARTIDOS
// ================================
function renderMatches(leagueName) {

    const tbody =
        document.querySelector("#matches-table tbody");

    tbody.innerHTML = "";

    document.getElementById("league-title").textContent =
        leagueName;

    const matches =
        allData[leagueName] || [];

    matches.forEach(match => {

        if (!isMatchInRange(match.date)) return;

        const h =
            parseFloat(match.best_home?.odd || 0);

        const d =
            parseFloat(match.best_draw?.odd || 0);

        const a =
            parseFloat(match.best_away?.odd || 0);

        let marginSure = null;

        if (h && d && a) {

            marginSure =
                100 -
                (
                    (1 / h + 1 / d + 1 / a) *
                    100
                );
        }

        const tr =
            document.createElement("tr");

        // Surebet
        if (marginSure > 0) {
            tr.classList.add("surebet-row");
        }

        tr.appendChild(
            createCell(formatLocalDate(match.date))
        );

        tr.appendChild(
            createCell(match.name)
        );

        tr.appendChild(
            createOddCell(
                match,
                match.best_home,
                "HOME"
            )
        );

        tr.appendChild(
            createOddCell(
                match,
                match.best_draw,
                "DRAW"
            )
        );

        tr.appendChild(
            createOddCell(
                match,
                match.best_away,
                "AWAY"
            )
        );


        // ================================
        // MARGEN
        // ================================
        const lossCell =
            document.createElement("td");

        if (marginSure !== null) {

            const span =
                document.createElement("span");

            span.style.color =
                marginSure > 0
                    ? "green"
                    : "red";

            span.style.fontWeight =
                "bold";

            span.textContent =
                marginSure.toFixed(3) + "%";

            lossCell.appendChild(span);

        } else {

            lossCell.textContent = "-";
        }


        // ================================
        // CALCULADORA
        // ================================
        const btn =
            document.createElement("button");

        btn.className = "calc-btn";

        btn.innerHTML =
            CALC_ICON_SVG;

        btn.title =
            "Abrir calculadora";

        btn.addEventListener(
            "click",
            () =>
                openCalculator(
                    match,
                    marginSure
                )
        );

        lossCell.appendChild(btn);


        // ================================
        // BETWATCH
        // ================================
        const btnBW =
            document.createElement("button");

        btnBW.className = "bw-btn";

        btnBW.textContent = "BW";

        btnBW.title =
            "Ver en Betwatch";

        btnBW.addEventListener(
            "click",
            () => openBetwatch(match)
        );

        lossCell.appendChild(btnBW);


        // ================================
        // ALL
        // ================================
        const btnALL =
            document.createElement("button");

        btnALL.className = "all-btn";

        btnALL.textContent = "ALL";

        btnALL.title =
            "Ver todas las cuotas";

        btnALL.addEventListener(
            "click",
            () => openAllOdds(match)
        );

        lossCell.appendChild(btnALL);


        tr.appendChild(lossCell);

        tbody.appendChild(tr);


        // ================================
        // FILA NoPA
        // ================================
        const eventId =
            getEventId(match);

        const noPaMatch =
            eventId
                ? noPaByEventId[eventId]
                : null;

        if (noPaMatch) {

            tbody.appendChild(
                createNoPaRow(
                    match,
                    noPaMatch
                )
            );
        }
    });
}


// ================================
// FILA NoPA
// ================================
function createNoPaRow(
    paMatch,
    noPaMatch
) {

    const h =
        parseFloat(
            noPaMatch.best_home?.odd || 0
        );

    const d =
        parseFloat(
            noPaMatch.best_draw?.odd || 0
        );

    const a =
        parseFloat(
            noPaMatch.best_away?.odd || 0
        );

    let marginSure = null;

    if (h && d && a) {

        marginSure =
            100 -
            (
                (1 / h + 1 / d + 1 / a) *
                100
            );
    }

    const tr =
        document.createElement("tr");

    tr.classList.add("nopa-row");

    if (marginSure > 0) {
        tr.classList.add("surebet-row");
    }


    tr.appendChild(
        createCell("")
    );

    tr.appendChild(
        createCell("")
    );

    tr.appendChild(
        createSimpleOddCell(
            noPaMatch.best_home
        )
    );

    tr.appendChild(
        createSimpleOddCell(
            noPaMatch.best_draw
        )
    );

    tr.appendChild(
        createSimpleOddCell(
            noPaMatch.best_away
        )
    );


    const lossCell =
        document.createElement("td");


    if (marginSure !== null) {

        const span =
            document.createElement("span");

        span.style.color =
            marginSure > 0
                ? "green"
                : "red";

        span.style.fontWeight =
            "bold";

        span.textContent =
            marginSure.toFixed(3) + "%";

        lossCell.appendChild(span);

    } else {

        lossCell.appendChild(
            document.createTextNode("-")
        );
    }


    // Calculadora NoPA
    const btn =
        document.createElement("button");

    btn.className =
        "calc-btn";

    btn.innerHTML =
        CALC_ICON_SVG;

    btn.title =
        "Abrir calculadora";

    btn.addEventListener(
        "click",
        () =>
            openCalculatorNoPA(
                paMatch,
                noPaMatch,
                marginSure
            )
    );

    lossCell.appendChild(btn);


    // ALL NoPA
    const btnALL =
        document.createElement("button");

    btnALL.className =
        "all-btn";

    btnALL.textContent =
        "ALL";

    btnALL.title =
        "Ver todas las cuotas NoPA";

    btnALL.addEventListener(
        "click",
        () =>
            openAllOddsNoPA(
                paMatch,
                noPaMatch
            )
    );

    lossCell.appendChild(btnALL);


    tr.appendChild(lossCell);

    return tr;
}


// ================================
// CELDA SIMPLE NoPA
// ================================
function createSimpleOddCell(best) {

    const td =
        document.createElement("td");

    if (!best?.odd) {

        td.textContent = "-";

        return td;
    }

    const logo =
        BOOKMAKER_LOGOS[
            best.bookmaker
        ] || null;

    td.innerHTML = `
        <span class="best-odd">
            ${best.odd}
        </span><br>
        ${
            logo
                ? `<img class="bm-logo"
                        src="${logo}"
                        alt="${best.bookmaker}"
                        title="${best.bookmaker}">`
                : best.bookmaker
        }
    `;

    return td;
}


// ================================
// CELDA NORMAL
// ================================
function createCell(text) {

    const td =
        document.createElement("td");

    td.textContent =
        text || "-";

    return td;
}


// ================================
// CELDA CUOTA + BETWATCH
// ================================
function createOddCell(
    match,
    best,
    side
) {

    const td =
        document.createElement("td");

    if (!best?.odd) {

        td.textContent = "-";

        return td;
    }

    const logo =
        BOOKMAKER_LOGOS[
            best.bookmaker
        ] || null;


    const bw =
        getSnapshotBackOdd(
            match,
            side
        );

    const bwHtml =
        (
            bw !== null &&
            bw !== undefined
        )
            ? `<span class="bw-odd-red">
                ${Number(bw).toFixed(2)}
               </span>`
            : "";


    td.innerHTML = `
        <span class="best-odd">
            ${best.odd}
        </span>
        ${bwHtml}
        <br>

        ${
            logo
                ? `<img
                    class="bm-logo"
                    src="${logo}"
                    alt="${best.bookmaker}"
                    title="${best.bookmaker}">
                  `
                : best.bookmaker
        }
    `;

    return td;
}


// ================================
// CALCULADORA PA
// ================================
function openCalculator(
    match,
    marginSure
) {

    const params =
        new URLSearchParams({

            name:
                match.name || "",

            date:
                match.date || "",

            league:
                match.Liga || "",

            homeOdd:
                match.best_home?.odd || "",

            homeBook:
                match.best_home?.bookmaker || "",

            drawOdd:
                match.best_draw?.odd || "",

            drawBook:
                match.best_draw?.bookmaker || "",

            awayOdd:
                match.best_away?.odd || "",

            awayBook:
                match.best_away?.bookmaker || "",

            margin:
                marginSure !== null
                    ? marginSure.toFixed(3)
                    : ""
        });


    window.open(
        "/calculadora?" +
        params.toString(),
        "_blank"
    );
}


// ================================
// TODAS LAS CUOTAS PA
// ================================
function openAllOdds(match) {

    const params =
        new URLSearchParams({

            league:
                match.Liga || "",

            name:
                match.name || "",

            date:
                match.date || "",

            home:
                match.home || "",

            away:
                match.away || "",

            eventId:
                getEventId(match)
        });


    window.open(
        "/detalle-cuotas?" +
        params.toString(),
        "_blank"
    );
}


// ================================
// CALCULADORA NoPA
// ================================
function openCalculatorNoPA(
    paMatch,
    noPaMatch,
    marginSure
) {

    const params =
        new URLSearchParams({

            name:
                paMatch.name ||
                noPaMatch.name ||
                "",

            date:
                paMatch.date ||
                noPaMatch.date ||
                "",

            league:
                paMatch.Liga ||
                noPaMatch.Liga ||
                "",

            homeOdd:
                noPaMatch.best_home?.odd ||
                "",

            homeBook:
                noPaMatch.best_home?.bookmaker ||
                "",

            drawOdd:
                noPaMatch.best_draw?.odd ||
                "",

            drawBook:
                noPaMatch.best_draw?.bookmaker ||
                "",

            awayOdd:
                noPaMatch.best_away?.odd ||
                "",

            awayBook:
                noPaMatch.best_away?.bookmaker ||
                "",

            margin:
                marginSure !== null
                    ? marginSure.toFixed(3)
                    : ""
        });


    window.open(
        "/calculadora?" +
        params.toString(),
        "_blank"
    );
}


// ================================
// TODAS LAS CUOTAS NoPA
// ================================
function openAllOddsNoPA(
    paMatch,
    noPaMatch
) {

    const params =
        new URLSearchParams({

            eventId:
                getEventId(paMatch) ||
                getEventId(noPaMatch),

            league:
                paMatch.Liga ||
                noPaMatch.Liga ||
                "",

            name:
                paMatch.name ||
                noPaMatch.name ||
                "",

            date:
                paMatch.date ||
                noPaMatch.date ||
                "",

            home:
                paMatch.home ||
                noPaMatch.home ||
                "",

            away:
                paMatch.away ||
                noPaMatch.away ||
                ""
        });


    window.open(
        "/detalle-cuotas-nopa?" +
        params.toString(),
        "_blank"
    );
}


// ================================
// FORMATEAR FECHA
// ================================
function formatLocalDate(dateStr) {

    if (!dateStr) return "-";

    const clean =
        dateStr
            .replace(" UTC", "")
            .replace(" ", "T")
        + ":00Z";

    const d =
        new Date(clean);

    return d.toLocaleString(
        "es-PE",
        {
            year: "numeric",
            month: "2-digit",
            day: "2-digit",
            hour: "numeric",
            minute: "2-digit",
            hour12: true
        }
    );
}


// ================================
// FILTRO FECHAS
// ================================
function isMatchInRange(dateStr) {

    if (dateFilter === "all") {
        return true;
    }

    const clean =
        dateStr
            .replace(" UTC", "")
            .replace(" ", "T")
        + ":00Z";

    const d =
        new Date(clean);

    if (isNaN(d)) {
        return true;
    }


    const peruMatch =
        new Date(
            d.toLocaleString(
                "en-US",
                {
                    timeZone:
                        "America/Lima"
                }
            )
        );


    const peruNow =
        new Date(
            new Date().toLocaleString(
                "en-US",
                {
                    timeZone:
                        "America/Lima"
                }
            )
        );


    peruMatch.setHours(
        0,
        0,
        0,
        0
    );

    peruNow.setHours(
        0,
        0,
        0,
        0
    );


    const diffDays =
        (
            peruMatch -
            peruNow
        ) /
        (
            1000 *
            60 *
            60 *
            24
        );


    if (dateFilter === "today") {
        return diffDays === 0;
    }

    if (dateFilter === "tomorrow") {
        return diffDays === 1;
    }

    if (dateFilter === "2d") {
        return (
            diffDays >= 0 &&
            diffDays <= 2
        );
    }

    if (dateFilter === "3d") {
        return (
            diffDays >= 0 &&
            diffDays <= 3
        );
    }

    return true;
}


// ================================
// BETWATCH
// ================================
function openBetwatch(match) {

    if (!match.eventId) {

        alert(
            "Este partido no tiene eventId para Betwatch"
        );

        return;
    }

    const url =
        `https://betwatch.fr/football/${match.eventId}`;

    window.open(
        url,
        "_blank"
    );
}


// ================================
// EVENTOS
// ================================
document
    .getElementById("date-filter")
    ?.addEventListener(
        "change",
        e => {

            dateFilter =
                e.target.value;

            renderMatches(
                currentLeague
            );
        }
    );


// =====================================================
// AUTO UPDATE
// =====================================================

// Consulta al servidor cada 5 segundos.
// El backend puede seguir regenerando cuotas cada ~35 s.
// Cuando aparezca un JSON nuevo, la web lo verá sin F5.
setInterval(
    fetchCuotas,
    5000
);

// Primera carga inmediatamente.
fetchCuotas();