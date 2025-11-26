// ======== CALCULADORA MANCORABET CON D/F oks ========
function parseQuery() {
    const params = {};
    const q = window.location.search.substring(1).split('&');
    for (const part of q) {
        if (!part) continue;
        const [k, v] = part.split('=');

        // === FIX 1: quitar "+" ===
        const cleaned = (v || '').replace(/\+/g, ' ');

        params[decodeURIComponent(k)] = decodeURIComponent(cleaned);
    }
    return params;
}

document.addEventListener('DOMContentLoaded', () => {
    const qs = parseQuery();

    // Rellenar cabecera
    const matchName = document.getElementById('match-name');
    const leagueDate = document.getElementById('match-league-date');

    const name  = qs.name  || '';
    const date  = qs.date  || '';
    const league = qs.league || '';

    if (matchName) matchName.textContent = name || 'Partido';
    if (leagueDate) leagueDate.textContent = (league ? league + ' · ' : '') + (date || '');

    // Rellenar casas y cuotas desde query
    const homeBook = document.getElementById('home-book');
    const drawBook = document.getElementById('draw-book');
    const awayBook = document.getElementById('away-book');

    const homeOddInput = document.getElementById('home-odd');
    const drawOddInput = document.getElementById('draw-odd');
    const awayOddInput = document.getElementById('away-odd');

    if (homeBook) homeBook.value = qs.homeBook || '';
    if (drawBook) drawBook.value = qs.drawBook || '';
    if (awayBook) awayBook.value = qs.awayBook || '';

    if (homeOddInput) homeOddInput.value = qs.homeOdd || '';
    if (drawOddInput) drawOddInput.value = qs.drawOdd || '';
    if (awayOddInput) awayOddInput.value = qs.awayOdd || '';

    // Referencias a stakes
    const homeStake = document.getElementById('home-stake');
    const drawStake = document.getElementById('draw-stake');
    const awayStake = document.getElementById('away-stake');

    // Totales
    const totalPayoutInput = document.getElementById('total-payout');

    const homeProfitSpan = document.getElementById('home-profit');
    const drawProfitSpan = document.getElementById('draw-profit');
    const awayProfitSpan = document.getElementById('away-profit');

    const guaranteedProfitSpan = document.getElementById('guaranteed-profit');
    const totalInvestSpan = document.getElementById('total-invest');

    const recalcBtn = document.getElementById('recalc-btn');

    // Radios D/F
    const modes = {
        home:  { D: document.getElementById('homeD'),  F: document.getElementById('homeF') },
        draw:  { D: document.getElementById('drawD'),  F: document.getElementById('drawF') },
        away:  { D: document.getElementById('awayD'),  F: document.getElementById('awayF') },
        total: { D: document.getElementById('totalD'), F: document.getElementById('totalF') }
    };

    // Asegurar solo una F
    function setExclusiveF(activeKey) {
        for (const key of Object.keys(modes)) {
            if (!modes[key].F) continue;
            if (key === activeKey) {
                modes[key].F.checked = true;
            } else {
                modes[key].D.checked = true;
            }
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
        if (modes.home.F && modes.home.F.checked)  return { type: 'stake', index: 0 };
        if (modes.draw.F && modes.draw.F.checked)  return { type: 'stake', index: 1 };
        if (modes.away.F && modes.away.F.checked)  return { type: 'stake', index: 2 };
        return { type: 'none' };
    }

    function recalc() {
        const odds = [
            parseFloat(homeOddInput.value) || 0,
            parseFloat(drawOddInput.value) || 0,
            parseFloat(awayOddInput.value) || 0
        ];

        let stakes = [
            parseFloat(homeStake.value) || 0,
            parseFloat(drawStake.value) || 0,
            parseFloat(awayStake.value) || 0
        ];

        let P = parseFloat(totalPayoutInput.value) || 0; // payout objetivo
        const mode = currentMode();

        // Si F en una apuesta: payout se define por esa apuesta fija
        if (mode.type === 'stake') {
            const i = mode.index;
            const fixedStake = stakes[i];
            if (fixedStake <= 0 || odds[i] <= 0) return;
            P = fixedStake * odds[i];
        }

        // Si F en total: P ya viene del input
        if (mode.type === 'total') {
            if (P <= 0) return;
        }

        // Si ninguno es F: usamos P pero si no vale, ponemos 100
        if (mode.type === 'none') {
            if (P <= 0) P = 100;
        }

        // Calcular stakes según payout P
        for (let i = 0; i < 3; i++) {
            if (mode.type === 'stake' && i === mode.index) continue;
            if (odds[i] > 0) {
                stakes[i] = P / odds[i];
            } else {
                stakes[i] = 0;
            }
        }

        // Actualizar stakes
        homeStake.value = stakes[0].toFixed(2);
        drawStake.value = stakes[1].toFixed(2);
        awayStake.value = stakes[2].toFixed(2);

        const T = stakes[0] + stakes[1] + stakes[2]; // inversión total
        const B = P - T; // beneficio garantizado

        totalPayoutInput.value = P.toFixed(2);

        homeProfitSpan.textContent = B.toFixed(2);
        drawProfitSpan.textContent = B.toFixed(2);
        awayProfitSpan.textContent = B.toFixed(2);

        guaranteedProfitSpan.textContent = B.toFixed(2);
        totalInvestSpan.textContent  = T.toFixed(2);

        // === FIX 2: CÁLCULO DE MARGEN Y ROI ===
        const inv1 = odds[0] > 0 ? 1 / odds[0] : 0;
        const invX = odds[1] > 0 ? 1 / odds[1] : 0;
        const inv2 = odds[2] > 0 ? 1 / odds[2] : 0;

        const roi = T > 0 ? (B / T) * 100 : 0;
        document.getElementById("roi-label").textContent = roi.toFixed(3) + "%";
    }

    // Eventos
    if (recalcBtn) recalcBtn.addEventListener('click', recalc);

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

    // Primer cálculo
    recalc();
});
