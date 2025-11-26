function getParam(name) {
    const params = new URLSearchParams(window.location.search);
    return params.get(name) || "";
}

function initCalculator() {
    const name  = getParam("name");
    const date  = getParam("date");
    const league = getParam("league");
    const margin = parseFloat(getParam("margin") || "0");

    const homeOdd  = parseFloat(getParam("homeOdd") || "0");
    const drawOdd  = parseFloat(getParam("drawOdd") || "0");
    const awayOdd  = parseFloat(getParam("awayOdd") || "0");

    document.getElementById("match-name").textContent = name || "Partido";
    document.getElementById("match-league-date").textContent =
        (league ? league + " · " : "") + (date || "");

    document.getElementById("home-book").value = getParam("homeBook");
    document.getElementById("draw-book").value = getParam("drawBook");
    document.getElementById("away-book").value = getParam("awayBook");

    if (homeOdd) document.getElementById("home-odd").value = homeOdd;
    if (drawOdd) document.getElementById("draw-odd").value = drawOdd;
    if (awayOdd) document.getElementById("away-odd").value = awayOdd;

    const marginLabel = document.getElementById("margin-label");
    if (!isNaN(margin) && margin !== 0) {
        marginLabel.textContent = margin.toFixed(3) + "%";
        marginLabel.classList.add(margin > 0 ? "positive" : "negative");
    } else {
        marginLabel.textContent = "--";
    }

    // Listeners
    ["home-odd", "draw-odd", "away-odd", "total-stake"].forEach(id => {
        document.getElementById(id).addEventListener("input", recalc);
    });

    document.getElementById("recalc-btn").addEventListener("click", recalc);

    recalc();
}

function recalc() {
    const homeOdd = parseFloat(document.getElementById("home-odd").value);
    const drawOdd = parseFloat(document.getElementById("draw-odd").value);
    const awayOdd = parseFloat(document.getElementById("away-odd").value);
    const totalStake = parseFloat(document.getElementById("total-stake").value);

    const roiLabel = document.getElementById("roi-label");
    const gProfitLabel = document.getElementById("guaranteed-profit");

    roiLabel.textContent = "--";
    roiLabel.classList.remove("positive", "negative");
    gProfitLabel.textContent = "--";
    gProfitLabel.classList.remove("positive", "negative");

    if (!homeOdd || !drawOdd || !awayOdd || !totalStake) {
        return;
    }

    const invSum = (1 / homeOdd) + (1 / drawOdd) + (1 / awayOdd);
    if (invSum <= 0) return;

    const stakeHome = totalStake / (homeOdd * invSum);
    const stakeDraw = totalStake / (drawOdd * invSum);
    const stakeAway = totalStake / (awayOdd * invSum);

    document.getElementById("home-stake").value = stakeHome.toFixed(2);
    document.getElementById("draw-stake").value = stakeDraw.toFixed(2);
    document.getElementById("away-stake").value = stakeAway.toFixed(2);

    const profitHome = stakeHome * homeOdd - totalStake;
    const profitDraw = stakeDraw * drawOdd - totalStake;
    const profitAway = stakeAway * awayOdd - totalStake;

    document.getElementById("home-profit").textContent = profitHome.toFixed(2);
    document.getElementById("draw-profit").textContent = profitDraw.toFixed(2);
    document.getElementById("away-profit").textContent = profitAway.toFixed(2);

    // deberían ser casi iguales, usamos la media
    const avgProfit = (profitHome + profitDraw + profitAway) / 3;
    const roi = (avgProfit / totalStake) * 100;

    roiLabel.textContent = roi.toFixed(2) + "%";
    gProfitLabel.textContent = avgProfit.toFixed(2);

    const cls = roi >= 0 ? "positive" : "negative";
    roiLabel.classList.add(cls);
    gProfitLabel.classList.add(cls);
}

document.addEventListener("DOMContentLoaded", initCalculator);
