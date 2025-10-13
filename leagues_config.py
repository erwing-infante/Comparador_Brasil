# leagues_config.py

# Regiones para cubrir tus casas: EU/EU-exchange/UK/AU
REGIONS = "eu,uk,au"

# Bookmakers a considerar (en minúsculas, como los devuelve la API)
BOOKMAKERS = [
    "bet365_au",
    "betfair_ex_eu",
    "suprabets",
    "leovegas_se",
    "betsson",
    "onexbet",
    "coolbet",
    "pinnacle",
]

# Mapa visible -> sport_key en The Odds API
LEAGUES = {
    "Premier League": "soccer_england_premier_league",
    "FA Cup": "soccer_england_fa_cup",
    "Carabao Cup": "soccer_england_efl_cup",
    "Championship": "soccer_england_championship",

    "La Liga": "soccer_spain_la_liga",
    "Copa del Rey": "soccer_spain_copa_del_rey",

    "Serie A": "soccer_italy_serie_a",
    "Copa Italia": "soccer_italy_coppa_italia",

    "Bundesliga": "soccer_germany_bundesliga",
    "Copa Alemana": "soccer_germany_dfb_pokal",

    "Ligue 1": "soccer_france_ligue_one",

    "Brasileirao": "soccer_brazil_campeonato",
    "Liga MX": "soccer_mexico_liga_mx",
    "MLS": "soccer_usa_mls",
    "Liga 1 Perú": "soccer_peru_primera_division",

    "UEFA Champions League": "soccer_uefa_champions_league",
    "UEFA Europa League": "soccer_uefa_europa_league",
    "UEFA Conference League": "soccer_uefa_europa_conference_league",

    "Copa Libertadores": "soccer_south_america_copa_libertadores",
    "Copa Sudamericana": "soccer_south_america_copa_sudamericana",
}