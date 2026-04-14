# leagues_config.py
# Configuración para odds-api.io

BOOKMAKERS = [
    "Bet365",
    "Betsafe",
    "1xbet",
    "Winamax DE",
    "Betcris"
]

# Lista completa de ligas con sus slugs en odds-api.io
LEAGUES = {
    "Premier League": {"provider": "odds-api.io", "league_id": "england-premier-league"},
    "FA Cup": {"provider": "odds-api.io", "league_id": "england-fa-cup"},
    "EFL Cup": {"provider": "odds-api.io", "league_id": "england-efl-cup"},
    "Championship": {"provider": "odds-api.io", "league_id": "england-championship"},

    "La Liga": {"provider": "odds-api.io", "league_id": "spain-laliga"},
    "Copa del Rey": {"provider": "odds-api.io", "league_id": "spain-copa-del-rey"},

    "Serie A": {"provider": "odds-api.io", "league_id": "italy-serie-a"},
    "Copa Italia": {"provider": "odds-api.io", "league_id": "italy-coppa-italia"},

    "Bundesliga": {"provider": "odds-api.io", "league_id": "germany-bundesliga"},
    "Copa Alemana": {"provider": "odds-api.io", "league_id": "germany-dfb-pokal"},

    "Ligue 1": {"provider": "odds-api.io", "league_id": "france-ligue-1"},
    "Copa Francia": {"provider": "odds-api.io", "league_id": "france-coupe-de-france"},

    "Brasileirao": {"provider": "odds-api.io", "league_id": "brazil-brasileiro-serie-a"},
    "Copa de Brasil": {"provider": "odds-api.io", "league_id": "brazil-copa-do-brasil"},

    "Liga MX": {"provider": "odds-api.io", "league_id": "mexico-liga-mx-clausura"},
    "MLS": {"provider": "odds-api.io", "league_id": "usa-mls"},
    "Liga 1 Perú": {"provider": "odds-api.io", "league_id": "peru-liga-1"},
    "Primeira Liga": {"provider": "odds-api.io", "league_id": "portugal-liga-portugal"},
    "Eredivisie": {"provider": "odds-api.io", "league_id": "netherlands-eredivisie"},
    "Eliminatorias Africa - WC26": {"provider": "odds-api.io", "league_id": "international-fifa-world-cup-qualification-caf"},
    "Eliminatorias Asia AFC - WC26": {"provider": "odds-api.io", "league_id": "international-world-cup-qualification-afc"},
    "Eliminatorias CONCACAF - WC26": {"provider": "odds-api.io", "league_id": "international-world-cup-qualification-concacaf"},
    "Eliminatorias Europa - WC26": {"provider": "odds-api.io", "league_id": "international-wc-qualification-uefa"},

    "UEFA Champions League": {"provider": "odds-api.io", "league_id": "international-clubs-uefa-champions-league"},
    "UEFA Europa League": {"provider": "odds-api.io", "league_id": "international-clubs-uefa-europa-league"},
    "UEFA Conference League": {"provider": "odds-api.io", "league_id": "international-clubs-uefa-conference-league"},

    "Copa Libertadores": {"provider": "odds-api.io", "league_id": "international-clubs-copa-libertadores"},
    "Copa Sudamericana": {"provider": "odds-api.io", "league_id": "international-clubs-copa-sudamericana"},
}