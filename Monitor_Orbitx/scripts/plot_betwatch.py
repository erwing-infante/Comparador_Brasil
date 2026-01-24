import os
import sys
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)
from config_orbitx import HISTORY_DIR  # noqa

CSV_LIGA_NAME = os.getenv("CSV_LIGA_NAME", "uefa_europa_league")
CSV_PATH = os.path.join(HISTORY_DIR, f"orbitx_{CSV_LIGA_NAME}.csv")

MARKET_ID = os.getenv("MARKET_ID", "1.251723513")
OUT_HTML = os.getenv("OUT_HTML", "betwatch_like.html")

BUCKET_SECONDS = int(os.getenv("BUCKET_SECONDS", "10"))
SHOW_LAY = os.getenv("SHOW_LAY", "0") == "1"

# Escalón del precio (Betwatch-like)
# hv  = salto vertical en el instante del cambio
# hvh = salto más "suave" (centrado entre puntos)
PRICE_STEP_SHAPE = os.getenv("PRICE_STEP_SHAPE", "hv")  # "hv" o "hvh"

# Padding del eje X: aire al inicio/fin como Betwatch
# Usa % del rango total (con mínimo)
X_PAD_PCT = float(os.getenv("X_PAD_PCT", "0.05"))  # 2%
X_PAD_MIN_SECONDS = int(os.getenv("X_PAD_MIN_SECONDS", "600"))  # 2 min

SPANISH_MONTHS = {
    1: "enero", 2: "febrero", 3: "marzo", 4: "abril",
    5: "mayo", 6: "junio", 7: "julio", 8: "agosto",
    9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre"
}

def money(x):
    if x is None or pd.isna(x):
        return ""
    return f"${float(x):,.0f}"

def safe_dt(s):
    try:
        dt = pd.to_datetime(s, errors="coerce")
        return None if pd.isna(dt) else dt
    except Exception:
        return None

def robust_odds_range(series, top_pad=0.50, bottom_pad=0.12):
    s = pd.to_numeric(series, errors="coerce").dropna()
    if s.empty:
        return None
    lo, hi = float(s.min()), float(s.max())
    if lo == hi:
        return (max(0.98, lo - 0.06), hi + 0.12)
    rng = hi - lo
    upper = hi + max(rng * top_pad, 0.06)
    lower = lo - max(rng * bottom_pad, 0.03)
    if lower < 1.0:
        lower = max(0.98, lower)
    return (lower, upper)

# ✅ Headroom real para que spikes NO choquen el borde superior
def robust_vol_range(series, top_pad=0.15):
    s = pd.to_numeric(series, errors="coerce").dropna()
    if s.empty:
        return (0, 1)

    v_max = float(s.max())
    v_p99 = float(s.quantile(0.99))

    base = max(v_p99, v_max, 1.0)
    upper = base * (1.0 + top_pad)

    if upper < 50:
        upper += 5

    return (0, upper)

def bucketize(df, seconds=10):
    d = df.sort_values("ts_pe").copy()
    d["bucket"] = d["ts_pe"].dt.floor(f"{seconds}S")
    out = (
        d.groupby("bucket", as_index=False)
         .agg(
             best_back_odds=("best_back_odds", "last"),
             best_lay_odds=("best_lay_odds", "last"),
             dv=("delta_tv_runner", "sum"),
             tv_runner=("tv_runner", "last"),
             tv_market=("tv_market", "last"),
         )
    )
    return out.rename(columns={"bucket": "ts_pe"})

# ✅ Mantener SOLO puntos donde cambia el precio (como Betwatch)
def compress_price_changes(b: pd.DataFrame, col="best_back_odds"):
    if b is None or b.empty or col not in b.columns:
        return b
    out = b.copy()
    out[col] = pd.to_numeric(out[col], errors="coerce")
    keep = out[col].ne(out[col].shift())
    if len(out) > 0:
        keep.iloc[0] = True
        keep.iloc[-1] = True
    return out.loc[keep].copy()

def xdomain(col: int) -> str:
    return "x domain" if col == 1 else f"x{col} domain"

def ydomain(col: int) -> str:
    return "y domain" if col == 1 else f"y{col} domain"

def add_volume_spikes(fig, b, row, col):
    """
    Volumen como "spikes" verticales (palitos finos) estilo Betwatch.
    Scatter con cortes None: (x,0)->(x,v)->None
    """
    bv = b.dropna(subset=["ts_pe", "dv"]).copy()
    x_spike, y_spike = [], []

    for x, v in zip(bv["ts_pe"], bv["dv"]):
        x_spike.extend([x, x, None])
        y_spike.extend([0, v, None])

    fig.add_trace(
        go.Scatter(
            x=x_spike,
            y=y_spike,
            mode="lines",
            line=dict(color="rgba(120,120,120,0.55)", width=1),
            hovertemplate="Vol: %{y:,.0f}<extra></extra>",
            showlegend=False,
            cliponaxis=True,  # ✅ no dibujar fuera del panel
        ),
        row=row, col=col, secondary_y=True
    )

def apply_betwatch_x_padding(fig, b, col):
    """
    ✅ Espacio libre al inicio y final, proporcional al rango total (tipo Betwatch).
    """
    if b is None or b.empty or not b["ts_pe"].notna().any():
        return

    xmin = b["ts_pe"].min()
    xmax = b["ts_pe"].max()
    span = xmax - xmin

    pad_pct = span * X_PAD_PCT
    pad_min = pd.Timedelta(seconds=max(X_PAD_MIN_SECONDS, BUCKET_SECONDS * 6))
    pad = max(pad_pct, pad_min)

    fig.update_xaxes(range=[xmin - pad, xmax + pad], row=1, col=col)

def main():
    if not MARKET_ID:
        raise SystemExit("❌ Falta MARKET_ID. Ej: set MARKET_ID=1.252329716")
    if not os.path.exists(CSV_PATH):
        raise SystemExit(f"❌ No existe CSV: {CSV_PATH}")

    df = pd.read_csv(CSV_PATH)
    df = df[df["market_id"].astype(str) == str(MARKET_ID)].copy()
    if df.empty:
        raise SystemExit("❌ No hay data para ese market_id aún.")

    df["ts_pe"] = pd.to_datetime(df["ts_pe"], errors="coerce")
    df = df.dropna(subset=["ts_pe"]).sort_values(["ts_pe", "selection"])

    for c in ["best_back_odds", "best_lay_odds", "tv_runner", "tv_market"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        else:
            df[c] = pd.NA

    df["delta_tv_runner"] = df.groupby("selection")["tv_runner"].diff().fillna(0)
    df.loc[df["delta_tv_runner"] < 0, "delta_tv_runner"] = 0

    event_name = str(df["event_name"].dropna().iloc[0]) if df["event_name"].notna().any() else "Partido"
    raw = event_name.replace(" v ", " — ").replace(" vs ", " — ")
    parts = [p.strip() for p in raw.split("—")]
    left_team = parts[0] if len(parts) >= 1 else raw
    right_team = parts[1] if len(parts) >= 2 else ""

    start_pe_raw = str(df["start_pe"].dropna().iloc[0]) if df["start_pe"].notna().any() else ""
    start_dt = safe_dt(start_pe_raw)
    if start_dt is None:
        start_dt = df["ts_pe"].iloc[-1]

    hora_txt = start_dt.strftime("%H:%M")
    fecha_txt = f"{start_dt.day} {SPANISH_MONTHS.get(start_dt.month,'')}"
    matched = float(df["tv_market"].dropna().iloc[-1]) if df["tv_market"].notna().any() else None

    fig = make_subplots(
        rows=1, cols=3,
        horizontal_spacing=0.08,
        specs=[[{"secondary_y": True}, {"secondary_y": True}, {"secondary_y": True}]]
    )

    order = [("HOME", 1), ("DRAW", 2), ("AWAY", 3)]
    panel_titles = {1: "1", 2: "X", 3: "2"}

    for sel, col in order:
        dsel = df[df["selection"].astype(str) == str(sel)].copy()
        if dsel.empty:
            b = pd.DataFrame({
                "ts_pe": [],
                "best_back_odds": [],
                "best_lay_odds": [],
                "dv": [],
                "tv_runner": [],
                "tv_market": [],
            })
        else:
            b = bucketize(dsel, seconds=BUCKET_SECONDS)

        # ✅ Padding tipo Betwatch (aire inicio/fin)
        apply_betwatch_x_padding(fig, b, col)

        # ✅ Volumen usa TODOS los buckets
        add_volume_spikes(fig, b, row=1, col=col)

        # ✅ Precio usa SOLO puntos donde cambió (Betwatch)
        bp = compress_price_changes(b, "best_back_odds")

        fig.add_trace(
            go.Scatter(
                x=bp["ts_pe"],
                y=bp["best_back_odds"],
                mode="lines",
                line=dict(color="#d60000", width=2.0),
                connectgaps=True,
                line_shape=PRICE_STEP_SHAPE,  # ✅ "hv" o "hvh"
                hovertemplate="Precio: %{y:.2f}<extra></extra>",
                showlegend=False,
            ),
            row=1, col=col, secondary_y=False
        )

        # Lay opcional (también comprimido para no meter ruido)
        if SHOW_LAY:
            bl = compress_price_changes(b, "best_lay_odds")
            fig.add_trace(
                go.Scatter(
                    x=bl["ts_pe"],
                    y=bl["best_lay_odds"],
                    mode="lines",
                    line=dict(color="rgba(255,140,0,0.85)", width=1.6, dash="dot"),
                    connectgaps=True,
                    line_shape=PRICE_STEP_SHAPE,
                    hovertemplate="Lay: %{y:.2f}<extra></extra>",
                    showlegend=False,
                ),
                row=1, col=col, secondary_y=False
            )

        pr = robust_odds_range(bp["best_back_odds"]) if (bp is not None and not bp.empty) else robust_odds_range(b["best_back_odds"])
        vr = robust_vol_range(b["dv"])

        # X axis
        fig.update_xaxes(
            showgrid=False,
            showline=True, linecolor="rgba(0,0,0,0.25)", mirror=True,
            showticklabels=False,
            zeroline=False,
            row=1, col=col,
        )

        # Y axis (Price) - grilla punteada suave
        fig.update_yaxes(
            showgrid=True,
            gridcolor="rgba(0,0,0,0.10)",
            griddash="dot",
            gridwidth=1,
            showline=True, linecolor="rgba(0,0,0,0.25)", mirror=True,
            zeroline=False,
            tickfont=dict(size=11, color="#d60000"),
            ticks="outside",
            ticklen=4,
            tickwidth=1,
            range=list(pr) if pr else None,
            row=1, col=col, secondary_y=False
        )

        # Y axis (Volume) - sin grid, ticks discretos + headroom
        fig.update_yaxes(
            showgrid=False,
            showline=True, linecolor="rgba(0,0,0,0.25)", mirror=True,
            zeroline=False,
            tickfont=dict(size=11, color="#666"),
            ticks="outside",
            ticklen=4,
            tickwidth=1,
            range=list(vr) if vr else None,
            row=1, col=col, secondary_y=True
        )

        # Etiquetas laterales Price / Volume
        fig.add_annotation(
            x=-0.13, y=0.5,
            xref=xdomain(col), yref=ydomain(col),
            text="<span style='color:#d60000'>Price</span>",
            textangle=-90,
            showarrow=False,
            font=dict(size=15),
        )
        fig.add_annotation(
            x=1.13, y=0.5,
            xref=xdomain(col), yref=ydomain(col),
            text="<span style='color:#666'>Volume</span>",
            textangle=-90,
            showarrow=False,
            font=dict(size=15),
        )

        # Título 1 / X / 2 arriba
        fig.add_annotation(
            x=0.5, y=1.16,
            xref=xdomain(col), yref=ydomain(col),
            text=f"<span style='color:#111;font-weight:800'>{panel_titles[col]}</span>",
            showarrow=False,
            font=dict(size=28),
        )

        # Texto debajo: $TV - last_price
        last_tv = float(b["tv_runner"].dropna().iloc[-1]) if len(b) and b["tv_runner"].notna().any() else None
        last_price = float(bp["best_back_odds"].dropna().iloc[-1]) if (bp is not None and len(bp) and bp["best_back_odds"].notna().any()) else None
        label = f"{money(last_tv)} - {last_price:.2f}" if (last_tv is not None and last_price is not None) else ""

        fig.add_annotation(
            x=0.5, y=-0.14,
            xref=xdomain(col), yref=ydomain(col),
            text=f"<span style='letter-spacing:0.2px;color:#111'>{label}</span>",
            showarrow=False,
            font=dict(size=18),
        )

    # Layout general
    fig.update_layout(
        template="simple_white",
        paper_bgcolor="white",
        plot_bgcolor="white",
        height=680,
        margin=dict(l=100, r=48, t=130, b=120),
        font=dict(family="Arial, Inter, sans-serif", size=12, color="#111"),
        hovermode="closest",  # ✅ más Betwatch que x unified
    )

    # Mantener dominios verticales
    y0 = 0.01
    y1 = 0.80
    fig.update_layout(
        yaxis=dict(domain=[y0, y1]),
        yaxis2=dict(domain=[y0, y1]),
        yaxis3=dict(domain=[y0, y1]),
        yaxis4=dict(domain=[y0, y1]),
        yaxis5=dict(domain=[y0, y1]),
        yaxis6=dict(domain=[y0, y1]),
    )

    # Encabezado partido
    y_top = 1.15

    fig.add_annotation(
        x=0.4, y=y_top,
        xref="paper", yref="paper",
        text=f"<span style='font-weight:500'>{left_team}</span>",
        showarrow=False,
        font=dict(size=24, color="#111"),
        xanchor="right",
    )
    fig.add_annotation(
        x=0.54, y=y_top,
        xref="paper", yref="paper",
        text=f"<span style='font-weight:500'>{right_team}</span>",
        showarrow=False,
        font=dict(size=24, color="#111"),
        xanchor="left",
    )
    fig.add_annotation(
        x=0.47, y=y_top + 0.05,
        xref="paper", yref="paper",
        text=f"<span style='font-weight:700'>{hora_txt}</span>",
        showarrow=False,
        font=dict(size=34, color="#111"),
        xanchor="center",
    )
    fig.add_annotation(
        x=0.47, y=y_top - 0.07,
        xref="paper", yref="paper",
        text=f"<span style='color:#666'>{fecha_txt}</span>",
        showarrow=False,
        font=dict(size=18, color="#666"),
        xanchor="center",
    )
    if matched is not None:
        fig.add_annotation(
            x=0.98, y=y_top + 0.08,
            xref="paper", yref="paper",
            text=f"Matched: {money(matched)}",
            showarrow=False,
            xanchor="right",
            font=dict(size=14, color="#333")
        )

    fig.write_html(
        OUT_HTML,
        include_plotlyjs="cdn",
        config={"displayModeBar": False, "scrollZoom": False}
    )
    print(f"✅ Generado: {OUT_HTML}")

if __name__ == "__main__":
    main()
