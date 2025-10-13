from flask import Flask, render_template, jsonify, request, redirect, url_for, session
import os, json
from datetime import timedelta

app = Flask(__name__)
app.secret_key = "clave-super-secreta-123"  # Cambia esto por algo único
app.permanent_session_lifetime = timedelta(days=1)  # Sesión válida 1 día

DATA_PATH = os.path.join(os.path.dirname(__file__), "data", "cuotas.json")

# 🧍 Credenciales fijas
USERNAME = "Mancorabet"
PASSWORD = "Mancora2025"

# 🧭 Página principal (requiere login)
@app.route("/")
def index():
    if "logged_in" not in session:
        return redirect(url_for("login"))

    data = {}
    if os.path.exists(DATA_PATH):
        with open(DATA_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    return render_template("index.html", data=data)

# 🧠 API JSON (requiere login)
@app.route("/api/cuotas")
def api_cuotas():
    if "logged_in" not in session:
        return jsonify({"error": "No autorizado"}), 401

    if os.path.exists(DATA_PATH):
        with open(DATA_PATH, "r", encoding="utf-8") as f:
            return jsonify(json.load(f))
    return jsonify({})

# 🔐 Login
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        if username == USERNAME and password == PASSWORD:
            session.permanent = True
            session["logged_in"] = True
            return redirect(url_for("index"))
        else:
            return render_template("login.html", error="Credenciales incorrectas")

    return render_template("login.html")

# 🚪 Logout manual (opcional)
@app.route("/logout")
def logout():
    session.pop("logged_in", None)
    return redirect(url_for("login"))

if __name__ == "__main__":
    app.run(debug=True)