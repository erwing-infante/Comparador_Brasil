from flask import Flask, render_template, jsonify, request, redirect, url_for, session, Response
import os, json, sqlite3
from datetime import timedelta, datetime
from zoneinfo import ZoneInfo
import io
import csv

app = Flask(__name__)
app.secret_key = "clave-super-secreta-123"
app.permanent_session_lifetime = timedelta(days=1)

BASE_DIR = os.path.dirname(__file__)
DATA_PATH = os.path.join(BASE_DIR, "data", "cuotas.json")
DB_PATH = os.path.join(BASE_DIR, "data", "bets.db")

# ================================================================
# USUARIOS / ROLES
# ================================================================
# viewer: tus amigos (solo ver/calcular)
# owner: tú (registrar + operaciones + billetera)
USERS = {
    "Mancorabet": {"password": "Mancora2025", "role": "viewer"},  # compartido
    "Erwing": {"password": "Wayandoj29", "role": "owner"},        # privado
}


def require_login():
    return session.get("logged_in") is True


def require_owner():
    return session.get("role") == "owner"


# ================================================================
# DB (SQLite)
# ================================================================
def db_conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def parse_utc_text(date_utc: str) -> datetime:
    s = (date_utc or "").strip().replace(" UTC", "").strip()
    try:
        dt = datetime.strptime(s, "%Y-%m-%d %H:%M")
    except ValueError:
        dt = datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
    return dt.replace(tzinfo=ZoneInfo("UTC"))


def now_utc() -> datetime:
    return datetime.now(tz=ZoneInfo("UTC"))


def fmt_pe(dt_utc: datetime):
    dt_pe = dt_utc.astimezone(ZoneInfo("America/Lima"))
    return {
        "datetime_pe": dt_pe.strftime("%Y-%m-%d %H:%M"),
        "date_pe": dt_pe.strftime("%Y-%m-%d"),
        "time_pe": dt_pe.strftime("%H:%M"),
    }


def wallet_apply(
    cur,
    bookmaker: str,
    delta: float,
    tx_type: str,
    note: str,
    bet_id: int | None,
    bookmaker_from: str,
    bookmaker_to: str,
    now_utc_str: str,
    now_pe_str: str
):
    bookmaker = (bookmaker or "").strip()
    if not bookmaker:
        return

    # upsert balance
    cur.execute("SELECT balance FROM wallet_accounts WHERE bookmaker=?", (bookmaker,))
    row = cur.fetchone()
    if row is None:
        cur.execute("INSERT INTO wallet_accounts (bookmaker, balance) VALUES (?, ?)", (bookmaker, 0.0))
        balance = 0.0
    else:
        balance = float(row["balance"] or 0)

    new_balance = balance + float(delta)
    cur.execute("UPDATE wallet_accounts SET balance=? WHERE bookmaker=?", (new_balance, bookmaker))

    # tx log (auditoría)
    cur.execute("""
        INSERT INTO wallet_tx (
            created_at_utc, created_at_pe,
            tx_type,
            bookmaker_from, bookmaker_to,
            amount,
            note,
            bet_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        now_utc_str, now_pe_str,
        tx_type,
        bookmaker_from, bookmaker_to,
        float(abs(delta)),
        note,
        bet_id
    ))


def init_db():
    conn = db_conn()
    cur = conn.cursor()

    # operaciones
    cur.execute("""
    CREATE TABLE IF NOT EXISTS bets (
        bet_id INTEGER PRIMARY KEY AUTOINCREMENT,

        league TEXT NOT NULL,
        match_name TEXT NOT NULL,

        event_datetime_utc TEXT NOT NULL,
        event_datetime_pe TEXT NOT NULL,
        event_date_pe TEXT NOT NULL,
        event_time_pe TEXT NOT NULL,

        created_at_utc TEXT NOT NULL,
        created_at_pe TEXT NOT NULL,
        created_date_pe TEXT NOT NULL,
        created_time_pe TEXT NOT NULL,

        status TEXT NOT NULL DEFAULT 'pendiente',
        total_payout REAL DEFAULT NULL
    );
    """)

    # ✅ SOLO ESTO: columnas PA (si tu DB ya existe, se agregan sin romper)
    try:
        cur.execute("ALTER TABLE bets ADD COLUMN pa_local INTEGER NOT NULL DEFAULT 0;")
    except Exception:
        pass
    try:
        cur.execute("ALTER TABLE bets ADD COLUMN pa_visita INTEGER NOT NULL DEFAULT 0;")
    except Exception:
        pass

    cur.execute("""
    CREATE TABLE IF NOT EXISTS bet_legs (
        leg_id INTEGER PRIMARY KEY AUTOINCREMENT,
        bet_id INTEGER NOT NULL,
        selection TEXT NOT NULL, -- HOME/DRAW/AWAY
        stake_total REAL NOT NULL DEFAULT 0,
        FOREIGN KEY(bet_id) REFERENCES bets(bet_id)
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS bet_leg_splits (
        split_id INTEGER PRIMARY KEY AUTOINCREMENT,
        leg_id INTEGER NOT NULL,
        person TEXT DEFAULT '',
        bookmaker TEXT NOT NULL,
        odd REAL NOT NULL,
        stake REAL NOT NULL,
        FOREIGN KEY(leg_id) REFERENCES bet_legs(leg_id)
    );
    """)

    # billetera (Opción 1: deposit/withdraw + movimientos por apuestas)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS wallet_accounts (
        bookmaker TEXT PRIMARY KEY,
        balance REAL NOT NULL DEFAULT 0
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS wallet_tx (
        tx_id INTEGER PRIMARY KEY AUTOINCREMENT,
        created_at_utc TEXT NOT NULL,
        created_at_pe TEXT NOT NULL,
        tx_type TEXT NOT NULL, -- deposit/withdraw/bet_place/bet_refund
        bookmaker_from TEXT DEFAULT '',
        bookmaker_to TEXT DEFAULT '',
        amount REAL NOT NULL,
        note TEXT DEFAULT '',
        bet_id INTEGER DEFAULT NULL
    );
    """)

    conn.commit()
    conn.close()


init_db()

# ================================================================
# LOGIN
# ================================================================
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = (request.form.get("username") or "").strip()
        p = (request.form.get("password") or "").strip()

        if u in USERS and USERS[u]["password"] == p:
            session["logged_in"] = True
            session["user"] = u
            session["role"] = USERS[u]["role"]
            session.permanent = True
            return redirect(url_for("index"))

        return render_template("login.html", error="Credenciales incorrectas")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ================================================================
# UI PROTEGIDA
# ================================================================
@app.route("/")
def index():
    if not require_login():
        return redirect(url_for("login"))
    return render_template("index.html")


@app.route("/calculadora")
def calculadora():
    if not require_login():
        return redirect(url_for("login"))

    name = request.args.get("name", "")
    date = request.args.get("date", "")
    league = request.args.get("league", "")

    homeOdd = request.args.get("homeOdd", "")
    homeBook = request.args.get("homeBook", "")

    drawOdd = request.args.get("drawOdd", "")
    drawBook = request.args.get("drawBook", "")

    awayOdd = request.args.get("awayOdd", "")
    awayBook = request.args.get("awayBook", "")

    return render_template(
        "calculadora.html",
        name=name,
        date=date,
        league=league,
        homeOdd=homeOdd,
        homeBook=homeBook,
        drawOdd=drawOdd,
        drawBook=drawBook,
        awayOdd=awayOdd,
        awayBook=awayBook,
        role=session.get("role", "viewer"),
        user=session.get("user", ""),
    )


# ================================================================
# NUEVO: DETALLE DE TODAS LAS CUOTAS
# ================================================================
@app.route("/detalle-cuotas")
def detalle_cuotas():
    if not require_login():
        return redirect(url_for("login"))
    return render_template("detalle_cuotas.html")


# ================================================================
# ADMIN: Operaciones (SOLO OWNER)
# ================================================================
@app.route("/admin/operaciones")
def admin_operaciones():
    if not require_login():
        return redirect(url_for("login"))
    if not require_owner():
        return redirect(url_for("index"))

    selected_league = (request.args.get("liga") or "").strip()

    conn = db_conn()
    cur = conn.cursor()

    cur.execute("SELECT DISTINCT league FROM bets ORDER BY league ASC;")
    leagues = [r["league"] for r in cur.fetchall()]

    if not selected_league and leagues:
        selected_league = leagues[0]

    if selected_league:
        cur.execute("""
            SELECT bet_id, league, match_name,
                   event_date_pe, event_time_pe,
                   created_date_pe, created_time_pe,
                   status, total_payout,
                   pa_local, pa_visita
            FROM bets
            WHERE league=?
            ORDER BY event_date_pe DESC, event_time_pe DESC, created_date_pe DESC, created_time_pe DESC;
        """, (selected_league,))
    else:
        cur.execute("""
            SELECT bet_id, league, match_name,
                   event_date_pe, event_time_pe,
                   created_date_pe, created_time_pe,
                   status, total_payout,
                   pa_local, pa_visita
            FROM bets
            ORDER BY league ASC, event_date_pe DESC, event_time_pe DESC, created_date_pe DESC, created_time_pe DESC;
        """)

    rows = cur.fetchall()
    conn.close()

    grouped_by_date = {}
    for r in rows:
        d = r["event_date_pe"]
        grouped_by_date.setdefault(d, [])
        grouped_by_date[d].append(dict(r))

    return render_template(
        "admin_operaciones.html",
        leagues=leagues,
        selected_league=selected_league,
        grouped_by_date=grouped_by_date
    )


# ================================================================
# ADMIN: Detalle operación (SOLO OWNER)
# ================================================================
@app.route("/admin/operacion/<int:bet_id>")
def admin_operacion_detalle(bet_id: int):
    if not require_login():
        return redirect(url_for("login"))
    if not require_owner():
        return redirect(url_for("index"))

    conn = db_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT bet_id, league, match_name,
               event_date_pe, event_time_pe,
               created_date_pe, created_time_pe,
               status, total_payout
        FROM bets
        WHERE bet_id=?
    """, (bet_id,))
    bet = cur.fetchone()
    if not bet:
        conn.close()
        return "No existe", 404

    cur.execute("""
        SELECT l.selection, s.person, s.bookmaker, s.odd, s.stake
        FROM bet_legs l
        JOIN bet_leg_splits s ON s.leg_id = l.leg_id
        WHERE l.bet_id=?
        ORDER BY l.selection ASC, s.bookmaker ASC
    """, (bet_id,))
    rows = cur.fetchall()
    conn.close()

    legs = {"HOME": [], "DRAW": [], "AWAY": []}
    for r in rows:
        legs[r["selection"]].append(dict(r))

    return render_template("admin_operacion_detalle.html", bet=dict(bet), legs=legs)


# ================================================================
# ADMIN: Billetera (SOLO OWNER) - Opción 1 (deposit/withdraw)
# ================================================================
@app.route("/admin/billetera")
def admin_billetera():
    if not require_login():
        return redirect(url_for("login"))
    if not require_owner():
        return redirect(url_for("index"))

    conn = db_conn()
    cur = conn.cursor()

    cur.execute("SELECT bookmaker, balance FROM wallet_accounts ORDER BY bookmaker ASC;")
    accounts = [dict(r) for r in cur.fetchall()]

    cur.execute("""
        SELECT tx_id, created_at_pe, tx_type, bookmaker_from, bookmaker_to, amount, note, bet_id
        FROM wallet_tx
        ORDER BY tx_id DESC
        LIMIT 5000;
    """)
    txs = [dict(r) for r in cur.fetchall()]

    conn.close()

    return render_template("admin_billetera.html", accounts=accounts, txs=txs)


@app.route("/admin/api/wallet/move", methods=["POST"])
def admin_wallet_move():
    if not require_login():
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    if not require_owner():
        return jsonify({"ok": False, "error": "forbidden"}), 403

    payload = request.get_json(silent=True) or {}
    tx_type = (payload.get("type") or "").strip().lower()
    bookmaker_from = (payload.get("from") or "").strip()
    bookmaker_to = (payload.get("to") or "").strip()
    note = (payload.get("note") or "").strip()

    try:
        amount = float(payload.get("amount"))
    except Exception:
        amount = 0.0

    if tx_type not in {"deposit", "withdraw"}:
        return jsonify({"ok": False, "error": "type inválido"}), 400
    if amount <= 0:
        return jsonify({"ok": False, "error": "amount inválido"}), 400

    dt_now_utc = now_utc()
    pe_now = fmt_pe(dt_now_utc)
    now_utc_str = dt_now_utc.strftime("%Y-%m-%d %H:%M:%S")
    now_pe_str = pe_now["datetime_pe"]

    conn = db_conn()
    cur = conn.cursor()
    try:
        if tx_type == "deposit":
            if not bookmaker_to:
                return jsonify({"ok": False, "error": "Falta 'to' (casa)"}), 400
            wallet_apply(
                cur,
                bookmaker=bookmaker_to,
                delta=+amount,
                tx_type="deposit",
                note=note or "Depósito",
                bet_id=None,
                bookmaker_from="",
                bookmaker_to=bookmaker_to,
                now_utc_str=now_utc_str,
                now_pe_str=now_pe_str
            )
        else:  # withdraw
            if not bookmaker_from:
                return jsonify({"ok": False, "error": "Falta 'from' (casa)"}), 400
            wallet_apply(
                cur,
                bookmaker=bookmaker_from,
                delta=-amount,
                tx_type="withdraw",
                note=note or "Retiro",
                bet_id=None,
                bookmaker_from=bookmaker_from,
                bookmaker_to="",
                now_utc_str=now_utc_str,
                now_pe_str=now_pe_str
            )

        conn.commit()
        return jsonify({"ok": True})
    except Exception as e:
        conn.rollback()
        return jsonify({"ok": False, "error": str(e)}), 500
    finally:
        conn.close()


# ================================================================
# ✅ PA (Pago Anticipado) - marcar checks PA L / PA V
# ================================================================
@app.route("/admin/api/bets/pa", methods=["POST"])
def admin_set_pa():
    if not require_login():
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    if not require_owner():
        return jsonify({"ok": False, "error": "forbidden"}), 403

    payload = request.get_json(silent=True) or {}
    bet_id = int(payload.get("bet_id", 0) or 0)
    side = (payload.get("side") or "").strip().upper()  # 'L' o 'V'
    value = 1 if bool(payload.get("value")) else 0

    if bet_id <= 0 or side not in {"L", "V"}:
        return jsonify({"ok": False, "error": "bet_id o side inválido"}), 400

    col = "pa_local" if side == "L" else "pa_visita"

    conn = db_conn()
    cur = conn.cursor()
    try:
        cur.execute(f"UPDATE bets SET {col}=? WHERE bet_id=?", (value, bet_id))
        conn.commit()
        return jsonify({"ok": True})
    except Exception as e:
        conn.rollback()
        return jsonify({"ok": False, "error": str(e)}), 500
    finally:
        conn.close()


# ================================================================
# ✅ RESET OPERACIONES (Opción B)
# - Borra bets/legs/splits
# - Borra wallet_tx ligados a bet (bet_id NOT NULL)
# - Recalcula wallet_accounts con lo que queda (depósitos/retiros)
# ================================================================
@app.route("/admin/api/bets/reset", methods=["POST"])
def admin_reset_operaciones():
    if not require_login():
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    if not require_owner():
        return jsonify({"ok": False, "error": "forbidden"}), 403

    conn = db_conn()
    cur = conn.cursor()
    try:
        # 1) borrar operaciones
        cur.execute("DELETE FROM bet_leg_splits;")
        cur.execute("DELETE FROM bet_legs;")
        cur.execute("DELETE FROM bets;")

        # 2) borrar tx de billetera ligados a operaciones
        cur.execute("DELETE FROM wallet_tx WHERE bet_id IS NOT NULL;")

        # 3) recalcular wallet_accounts con lo que queda
        cur.execute("DELETE FROM wallet_accounts;")

        # Entradas (deposit) -> bookmaker_to
        cur.execute("""
            SELECT bookmaker_to AS bk, SUM(amount) AS amt
            FROM wallet_tx
            WHERE tx_type='deposit'
              AND TRIM(COALESCE(bookmaker_to,'')) <> ''
            GROUP BY bookmaker_to
        """)
        inc = {r["bk"]: float(r["amt"] or 0) for r in cur.fetchall()}

        # Salidas (withdraw) -> bookmaker_from
        cur.execute("""
            SELECT bookmaker_from AS bk, SUM(amount) AS amt
            FROM wallet_tx
            WHERE tx_type='withdraw'
              AND TRIM(COALESCE(bookmaker_from,'')) <> ''
            GROUP BY bookmaker_from
        """)
        dec = {r["bk"]: float(r["amt"] or 0) for r in cur.fetchall()}

        books = set(list(inc.keys()) + list(dec.keys()))
        for bk in books:
            bal = float(inc.get(bk, 0.0)) - float(dec.get(bk, 0.0))
            cur.execute("INSERT INTO wallet_accounts (bookmaker, balance) VALUES (?, ?)", (bk, bal))

        conn.commit()
        return jsonify({"ok": True})
    except Exception as e:
        conn.rollback()
        return jsonify({"ok": False, "error": str(e)}), 500
    finally:
        conn.close()


# ================================================================
# ✅ EXPORT / RESET BILLETERA (SOLO OWNER)
# ================================================================
@app.route("/admin/api/wallet/export")
def admin_wallet_export():
    if not require_login():
        return redirect(url_for("login"))
    if not require_owner():
        return redirect(url_for("index"))

    conn = db_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT tx_id, created_at_pe, tx_type, bookmaker_from, bookmaker_to, amount, note, bet_id
        FROM wallet_tx
        ORDER BY tx_id ASC;
    """)
    rows = cur.fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["tx_id", "created_at_pe", "tx_type", "bookmaker_from", "bookmaker_to", "amount", "note", "bet_id"])
    for r in rows:
        writer.writerow([
            r["tx_id"],
            r["created_at_pe"],
            r["tx_type"],
            r["bookmaker_from"],
            r["bookmaker_to"],
            r["amount"],
            r["note"],
            r["bet_id"],
        ])

    csv_text = output.getvalue()
    output.close()

    filename = f"billetera_movimientos_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(
        csv_text,
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@app.route("/admin/api/wallet/reset", methods=["POST"])
def admin_wallet_reset():
    if not require_login():
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    if not require_owner():
        return jsonify({"ok": False, "error": "forbidden"}), 403

    conn = db_conn()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM wallet_tx;")
        cur.execute("DELETE FROM wallet_accounts;")
        conn.commit()
        return jsonify({"ok": True})
    except Exception as e:
        conn.rollback()
        return jsonify({"ok": False, "error": str(e)}), 500
    finally:
        conn.close()


# ================================================================
# ADMIN APIs (SOLO OWNER)
# ================================================================
@app.route("/admin/api/bets/register", methods=["POST"])
def admin_register_bet():
    if not require_login():
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    if not require_owner():
        return jsonify({"ok": False, "error": "forbidden"}), 403

    payload = request.get_json(silent=True) or {}

    league = (payload.get("league") or "").strip()
    name = (payload.get("name") or "").strip()
    date_utc = (payload.get("date_utc") or "").strip()
    total_payout = payload.get("total_payout", None)
    legs = payload.get("legs") or {}

    if not league or not name or not date_utc:
        return jsonify({"ok": False, "error": "Faltan league/name/date_utc"}), 400

    for key in ("HOME", "DRAW", "AWAY"):
        if key not in legs or not isinstance(legs[key], list) or len(legs[key]) == 0:
            return jsonify({"ok": False, "error": f"Falta leg {key} o está vacío"}), 400

    def valid_split(s):
        try:
            book = (s.get("book") or "").strip()
            odd = float(s.get("odd"))
            stake = float(s.get("stake"))
            return bool(book) and odd > 1.0 and stake > 0
        except Exception:
            return False

    all_splits = legs["HOME"] + legs["DRAW"] + legs["AWAY"]
    if not all(valid_split(s) for s in all_splits):
        return jsonify({"ok": False, "error": "Revisa book/odd/stake (odd>1, stake>0)"}), 400

    try:
        dt_event_utc = parse_utc_text(date_utc)
        pe_event = fmt_pe(dt_event_utc)
    except Exception as e:
        return jsonify({"ok": False, "error": f"date_parse_error: {e}"}), 400

    dt_created_utc = now_utc()
    pe_created = fmt_pe(dt_created_utc)

    now_utc_str = dt_created_utc.strftime("%Y-%m-%d %H:%M:%S")
    now_pe_str = pe_created["datetime_pe"]

    conn = db_conn()
    cur = conn.cursor()

    try:
        cur.execute("""
            INSERT INTO bets (
                league, match_name,
                event_datetime_utc, event_datetime_pe, event_date_pe, event_time_pe,
                created_at_utc, created_at_pe, created_date_pe, created_time_pe,
                status, total_payout
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pendiente', ?)
        """, (
            league, name,
            date_utc, pe_event["datetime_pe"], pe_event["date_pe"], pe_event["time_pe"],
            now_utc_str,
            pe_created["datetime_pe"], pe_created["date_pe"], pe_created["time_pe"],
            total_payout
        ))
        bet_id = cur.lastrowid

        def insert_leg(selection, splits_list):
            stake_total = sum(float(x.get("stake")) for x in splits_list)
            cur.execute("""
                INSERT INTO bet_legs (bet_id, selection, stake_total)
                VALUES (?, ?, ?)
            """, (bet_id, selection, stake_total))
            leg_id = cur.lastrowid

            for sp in splits_list:
                person = (sp.get("person") or "").strip()
                book = (sp.get("book") or "").strip()
                odd = float(sp.get("odd"))
                stake = float(sp.get("stake"))
                cur.execute("""
                    INSERT INTO bet_leg_splits (leg_id, person, bookmaker, odd, stake)
                    VALUES (?, ?, ?, ?, ?)
                """, (leg_id, person, book, odd, stake))

        insert_leg("HOME", legs["HOME"])
        insert_leg("DRAW", legs["DRAW"])
        insert_leg("AWAY", legs["AWAY"])

        # DESCUESTA billetera por casa (bet_place)
        totals = {}
        for sp in all_splits:
            bk = (sp.get("book") or "").strip()
            st = float(sp.get("stake"))
            totals[bk] = totals.get(bk, 0.0) + st

        for bk, amt in totals.items():
            if amt > 0:
                wallet_apply(
                    cur,
                    bookmaker=bk,
                    delta=-amt,
                    tx_type="bet_place",
                    note=f"Apuesta registrada #{bet_id}",
                    bet_id=bet_id,
                    bookmaker_from=bk,
                    bookmaker_to="",
                    now_utc_str=now_utc_str,
                    now_pe_str=now_pe_str
                )

        conn.commit()
        return jsonify({"ok": True, "bet_id": bet_id})

    except Exception as e:
        conn.rollback()
        return jsonify({"ok": False, "error": str(e)}), 500
    finally:
        conn.close()


@app.route("/admin/api/bets/status", methods=["POST"])
def admin_set_status():
    if not require_login():
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    if not require_owner():
        return jsonify({"ok": False, "error": "forbidden"}), 403

    payload = request.get_json(silent=True) or {}
    bet_id = int(payload.get("bet_id", 0) or 0)
    status = (payload.get("status") or "").strip().lower()

    allowed = {"pendiente", "local", "empate", "visita"}
    if bet_id <= 0 or status not in allowed:
        return jsonify({"ok": False, "error": "bet_id o status inválido"}), 400

    # Mapea tu status UI -> selection guardada en DB
    status_to_sel = {"local": "HOME", "empate": "DRAW", "visita": "AWAY"}

    dt_now_utc = now_utc()
    pe_now = fmt_pe(dt_now_utc)
    now_utc_str = dt_now_utc.strftime("%Y-%m-%d %H:%M:%S")
    now_pe_str = pe_now["datetime_pe"]

    conn = db_conn()
    cur = conn.cursor()
    try:
        # 1) Resetear el WIN NETO previo de este bet_id (evita acumulación)
        # neto = SUM(bet_win) - SUM(bet_win_revert) por casa
        cur.execute("""
            SELECT bk, SUM(delta) AS neto
            FROM (
                SELECT bookmaker_to AS bk, amount AS delta
                FROM wallet_tx
                WHERE bet_id=? AND tx_type='bet_win'

                UNION ALL

                SELECT bookmaker_from AS bk, -amount AS delta
                FROM wallet_tx
                WHERE bet_id=? AND tx_type='bet_win_revert'
            )
            GROUP BY bk
        """, (bet_id, bet_id))
        net_rows = cur.fetchall()

        for r in net_rows:
            bk = (r["bk"] or "").strip()
            neto = float(r["neto"] or 0)
            if bk and abs(neto) > 1e-9:
                wallet_apply(
                    cur,
                    bookmaker=bk,
                    delta=-neto,
                    tx_type="bet_win_revert",
                    note=f"Reset win neto #{bet_id}",
                    bet_id=bet_id,
                    bookmaker_from=bk,
                    bookmaker_to="",
                    now_utc_str=now_utc_str,
                    now_pe_str=now_pe_str
                )

        # 2) Actualizar status
        cur.execute("UPDATE bets SET status=? WHERE bet_id=?", (status, bet_id))

        # 3) Si el nuevo status es ganador, liquidar (SUM(odd*stake)) por casa
        if status in status_to_sel:
            sel = status_to_sel[status]
            cur.execute("""
                SELECT s.bookmaker AS bookmaker, SUM(s.odd * s.stake) AS payout
                FROM bet_legs l
                JOIN bet_leg_splits s ON s.leg_id = l.leg_id
                WHERE l.bet_id=? AND l.selection=?
                GROUP BY s.bookmaker
            """, (bet_id, sel))
            payouts = cur.fetchall()

            for r in payouts:
                bk = (r["bookmaker"] or "").strip()
                amt = float(r["payout"] or 0)
                if bk and amt > 0:
                    wallet_apply(
                        cur,
                        bookmaker=bk,
                        delta=+amt,
                        tx_type="bet_win",
                        note=f"Cobro ({status}) #{bet_id}",
                        bet_id=bet_id,
                        bookmaker_from="",
                        bookmaker_to=bk,
                        now_utc_str=now_utc_str,
                        now_pe_str=now_pe_str
                    )

        conn.commit()
        return jsonify({"ok": True})
    except Exception as e:
        conn.rollback()
        return jsonify({"ok": False, "error": str(e)}), 500
    finally:
        conn.close()


@app.route("/admin/api/bets/delete", methods=["POST"])
def admin_delete_bet():
    if not require_login():
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    if not require_owner():
        return jsonify({"ok": False, "error": "forbidden"}), 403

    payload = request.get_json(silent=True) or {}
    bet_id = int(payload.get("bet_id", 0) or 0)
    if bet_id <= 0:
        return jsonify({"ok": False, "error": "bet_id inválido"}), 400

    dt_now_utc = now_utc()
    pe_now = fmt_pe(dt_now_utc)
    now_utc_str = dt_now_utc.strftime("%Y-%m-%d %H:%M:%S")
    now_pe_str = pe_now["datetime_pe"]

    conn = db_conn()
    cur = conn.cursor()
    try:
        # ============================
        # ✅ FIX: si el bet quedó "ganado", primero revertir WIN NETO
        # neto = SUM(bet_win) - SUM(bet_win_revert) por casa
        # ============================
        cur.execute("""
            SELECT bk, SUM(delta) AS neto
            FROM (
                SELECT bookmaker_to AS bk, amount AS delta
                FROM wallet_tx
                WHERE bet_id=? AND tx_type='bet_win'

                UNION ALL

                SELECT bookmaker_from AS bk, -amount AS delta
                FROM wallet_tx
                WHERE bet_id=? AND tx_type='bet_win_revert'
            )
            GROUP BY bk
        """, (bet_id, bet_id))
        net_rows = cur.fetchall()

        for r in net_rows:
            bk = (r["bk"] or "").strip()
            neto = float(r["neto"] or 0)
            if bk and abs(neto) > 1e-9:
                wallet_apply(
                    cur,
                    bookmaker=bk,
                    delta=-neto,
                    tx_type="bet_win_revert",
                    note=f"Reset win neto #{bet_id} (delete)",
                    bet_id=bet_id,
                    bookmaker_from=bk,
                    bookmaker_to="",
                    now_utc_str=now_utc_str,
                    now_pe_str=now_pe_str
                )

        # refund por casa (sum stakes)
        cur.execute("""
            SELECT s.bookmaker, SUM(s.stake) AS total_stake
            FROM bet_legs l
            JOIN bet_leg_splits s ON s.leg_id = l.leg_id
            WHERE l.bet_id=?
            GROUP BY s.bookmaker
        """, (bet_id,))
        refunds = cur.fetchall()

        for r in refunds:
            bk = r["bookmaker"]
            amt = float(r["total_stake"] or 0)
            if amt > 0:
                wallet_apply(
                    cur,
                    bookmaker=bk,
                    delta=+amt,
                    tx_type="bet_refund",
                    note=f"Refund por borrar operación #{bet_id}",
                    bet_id=bet_id,
                    bookmaker_from="",
                    bookmaker_to=bk,
                    now_utc_str=now_utc_str,
                    now_pe_str=now_pe_str
                )

        # borrar splits/legs/bet
        cur.execute("SELECT leg_id FROM bet_legs WHERE bet_id=?", (bet_id,))
        legs = [int(r["leg_id"]) for r in cur.fetchall()]
        if legs:
            cur.execute(
                f"DELETE FROM bet_leg_splits WHERE leg_id IN ({','.join(['?']*len(legs))})",
                legs
            )
        cur.execute("DELETE FROM bet_legs WHERE bet_id=?", (bet_id,))
        cur.execute("DELETE FROM bets WHERE bet_id=?", (bet_id,))

        conn.commit()
        return jsonify({"ok": True})
    except Exception as e:
        conn.rollback()
        return jsonify({"ok": False, "error": str(e)}), 500
    finally:
        conn.close()


# ================================================================
# API ABIERTA
# ================================================================
@app.route("/api/cuotas")
def api_cuotas():
    if os.path.exists(DATA_PATH):
        with open(DATA_PATH, "r", encoding="utf-8") as f:
            try:
                return jsonify(json.load(f))
            except Exception:
                return jsonify({"error": "formato inválido"})
    return jsonify({})


if __name__ == "__main__":
    app.run()