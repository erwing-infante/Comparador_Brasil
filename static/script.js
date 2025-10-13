let allData = {};
let currentLeague = null;

async function fetchCuotas() {
  try {
    const res = await fetch('/api/cuotas');
    allData = await res.json();
    renderLeagues();
    if (currentLeague) {
      renderMatches(currentLeague);
    }
  } catch (e) {
    console.error("Error al cargar cuotas:", e);
  }
}

function renderLeagues() {
  const leagueList = document.getElementById('league-list');
  leagueList.innerHTML = '';

  Object.keys(allData).forEach(leagueName => {
    const li = document.createElement('li');
    li.textContent = leagueName;
    if (leagueName === currentLeague) li.classList.add('active');
    li.addEventListener('click', () => {
      currentLeague = leagueName;
      renderMatches(leagueName);
      renderLeagues();
    });
    leagueList.appendChild(li);
  });
}

function formatLocalDate(dateStr) {
  if (!dateStr) return '-';
  const date = new Date(dateStr); // The Odds API devuelve en UTC
  return date.toLocaleString('es-PE', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: 'numeric',
    minute: '2-digit',
    hour12: true
  });
}

function renderMatches(leagueName) {
  const matchesTableBody = document.querySelector('#matches-table tbody');
  const leagueTitle = document.getElementById('league-title');

  leagueTitle.textContent = leagueName;
  matchesTableBody.innerHTML = '';

  const matches = allData[leagueName] || [];
  if (matches.length === 0) {
    matchesTableBody.innerHTML = `<tr><td colspan="6">No hay partidos disponibles</td></tr>`;
    return;
  }

  matches.forEach(match => {
    const row = document.createElement('tr');

    // 📅 Fecha (formato local AM/PM)
    const dateCell = document.createElement('td');
    dateCell.textContent = formatLocalDate(match.date);
    row.appendChild(dateCell);

    // 🏟 Partido
    const nameCell = document.createElement('td');
    nameCell.textContent = match.name;
    row.appendChild(nameCell);

    // 🏠 Local
    const homeCell = document.createElement('td');
    homeCell.innerHTML = match.best_home.odd 
      ? `<span class="best-odd">${match.best_home.odd}</span><br><small>${match.best_home.bookmaker}</small>` 
      : '-';
    row.appendChild(homeCell);

    // 🤝 Empate
    const drawCell = document.createElement('td');
    drawCell.innerHTML = match.best_draw.odd 
      ? `<span class="best-odd">${match.best_draw.odd}</span><br><small>${match.best_draw.bookmaker}</small>` 
      : '-';
    row.appendChild(drawCell);

    // ✈️ Visita
    const awayCell = document.createElement('td');
    awayCell.innerHTML = match.best_away.odd 
      ? `<span class="best-odd">${match.best_away.odd}</span><br><small>${match.best_away.bookmaker}</small>` 
      : '-';
    row.appendChild(awayCell);

    // 📉 % Pérdida
    const lossCell = document.createElement('td');
    const h = parseFloat(match.best_home.odd);
    const d = parseFloat(match.best_draw.odd);
    const a = parseFloat(match.best_away.odd);

    if (h && d && a) {
      const margin = 100 - ((1 / h + 1 / d + 1 / a) * 100);
      // ✅ Positivo = verde, Negativo = rojo
      const color = margin > 0 ? 'green' : 'red';
      lossCell.innerHTML = `<span style="color:${color}; font-weight:bold;">${margin.toFixed(3)}%</span>`;
    } else {
      lossCell.textContent = '-';
    }
    row.appendChild(lossCell);

    matchesTableBody.appendChild(row);
  });
}

// 🔄 Actualizar cada 2 minutos automáticamente
setInterval(fetchCuotas, 120000);

// Llamada inicial
fetchCuotas();