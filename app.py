from flask import Flask, render_template, jsonify, request, redirect, url_for, session
import os, json
from datetime import timedelta

app = Flask(__name__)
app.secret_key = "clave-super-secreta-123"
app.permanent_session_lifetime = timedelta(days=1)

DATA_PATH = os.path.join(os.path.dirname(__file__), "data", "cuotas.json")

USERNAME = "Mancorabet"
PASSWORD = "Mancora2025"

# ---------- LOGIN ----------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form.get("username") == USERNAME and request.form.get("password") == PASSWORD:
            session["logged_in"] = True
            session.permanent = True
            return redirect(url_for("index"))
        return render_template("login.html", error="Credenciales incorrectas")

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.pop("logged_in", None)
    return redirect(url_for("login"))

# ---------- UI PROTEGIDA ----------
@app.route("/")
def index():
    if "logged_in" not in session:
        return redirect(url_for("login"))
    return render_template("index.html")

# ---------- API ABIERTA (puedes protegerla si quieres) ----------
@app.route("/api/cuotas")
def api_cuotas():
    # OPCIONAL: proteger la API
    # if "logged_in" not in session:
    #     return jsonify({"error": "no autorizado"})

    if os.path.exists(DATA_PATH):
        with open(DATA_PATH, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
                ligas = [k for k in data.keys() if k != "metadata"]
                print("✅ Cuotas cargadas:", ligas)
                for liga in ligas:
                    print(f"📊 {liga}: {len(data[liga])} partidos")
                return jsonify(data)
            except Exception as e:
                print("❌ Error al cargar cuotas.json:", e)
                return jsonify({"error": "formato inválido"})
    print("⚠️ Archivo cuotas.json no encontrado")
    return jsonify({})
    
if __name__ == "__main__":
    app.run()