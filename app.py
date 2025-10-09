from flask import Flask, render_template

app = Flask(__name__)

@app.route('/')
def index():
    # Datos de prueba (hasta conectar con la API real)
    matches = [
        {
            "name": "Palmeiras vs Flamengo",
            "best_home": {"odd": 2.10, "bookmaker": "Bet365"},
            "best_draw": {"odd": 3.25, "bookmaker": "Betano"},
            "best_away": {"odd": 3.40, "bookmaker": "Betsson"},
            "best_bookmaker": "Bet365"
        },
        {
            "name": "Santos vs Corinthians",
            "best_home": {"odd": 2.50, "bookmaker": "Betfair"},
            "best_draw": {"odd": 3.10, "bookmaker": "Betano"},
            "best_away": {"odd": 2.90, "bookmaker": "1xBet"},
            "best_bookmaker": "Betfair"
        }
    ]

    return render_template('index.html', matches=matches)

if __name__ == '__main__':
    app.run(debug=True)