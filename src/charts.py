from __future__ import annotations

import pandas as pd

from .utils import MONTH_NAMES


def prepare_monthly_profile(
    history: pd.DataFrame,
    selected_year: int,
    months: tuple[int, ...] = (),
) -> pd.DataFrame:
    selected_months = list(months) if months else list(range(1, 13))
    grid = pd.DataFrame({"MES": selected_months})
    current = (
        history.loc[history["ANO"] == selected_year, ["MES", "VALOR"]]
        .rename(columns={"VALOR": "ATUAL"})
    )
    historical = history.loc[history["ANO"] < selected_year]
    if historical.empty:
        band = pd.DataFrame(columns=["MES", "MIN_5A", "MAX_5A", "N_ANOS_BANDA"])
    else:
        band = (
            historical.groupby("MES", as_index=False)
            .agg(
                MIN_5A=("VALOR", "min"),
                MAX_5A=("VALOR", "max"),
                N_ANOS_BANDA=("ANO", "nunique"),
            )
        )
    profile = grid.merge(current, on="MES", how="left").merge(band, on="MES", how="left")
    profile["MES_LABEL"] = profile["MES"].map(MONTH_NAMES)
    return profile


def monthly_plotly(
    profile: pd.DataFrame,
    selected_year: int,
    metric_label: str,
    daily_average: bool,
):
    import plotly.graph_objects as go

    suffix = " — média por dia útil" if daily_average else " — total mensal"
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=profile["MES_LABEL"],
            y=profile["MIN_5A"],
            mode="lines",
            line={"width": 0},
            hoverinfo="skip",
            showlegend=False,
            name="Mínimo histórico",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=profile["MES_LABEL"],
            y=profile["MAX_5A"],
            mode="lines",
            line={"width": 0},
            fill="tonexty",
            fillcolor="rgba(120, 120, 120, 0.25)",
            name="Faixa mín.–máx. (5 anos anteriores)",
            hovertemplate="Máx.: %{y:,.2f}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=profile["MES_LABEL"],
            y=profile["ATUAL"],
            mode="lines+markers",
            line={"color": "#1B5E20", "width": 3},
            marker={"size": 8},
            name=str(selected_year),
            hovertemplate="%{x}: %{y:,.2f}<extra></extra>",
        )
    )
    fig.update_layout(
        title=f"{metric_label}{suffix}",
        xaxis_title=None,
        yaxis_title=metric_label,
        hovermode="x unified",
        template="plotly_white",
        legend={"orientation": "h", "y": -0.18},
        margin={"l": 20, "r": 20, "t": 70, "b": 70},
        height=460,
    )
    fig.update_yaxes(rangemode="tozero", tickformat=",.3s")
    return fig


def monthly_matplotlib(
    profile: pd.DataFrame,
    selected_year: int,
    metric_label: str,
    daily_average: bool,
):
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(11, 5.5))
    x = range(len(profile))
    ax.fill_between(x, profile["MIN_5A"], profile["MAX_5A"], color="0.75", alpha=0.5)
    ax.plot(x, profile["ATUAL"], color="#1B5E20", marker="o", linewidth=2.5, label=str(selected_year))
    ax.set_xticks(list(x), profile["MES_LABEL"])
    ax.set_ylabel(metric_label)
    ax.set_title(metric_label + (" — média por dia útil" if daily_average else " — total mensal"))
    ax.grid(axis="y", alpha=0.25)
    ax.legend()
    fig.tight_layout()
    return fig


def country_ranking_plotly(
    ranking: pd.DataFrame,
    metric_label: str,
    flow: str,
    top_n: int = 10,
):
    import plotly.graph_objects as go

    data = ranking.head(top_n).sort_values("VALOR", ascending=True)
    color = "#18794E" if flow == "EXP" else "#2563A6"
    role = "destinos" if flow == "EXP" else "origens"
    fig = go.Figure(
        go.Bar(
            x=data["VALOR"],
            y=data["PAIS"],
            orientation="h",
            marker={"color": color, "line": {"color": "rgba(255,255,255,.65)", "width": 1}},
            customdata=data[["PARTICIPACAO"]],
            hovertemplate=(
                "%{y}<br>" + metric_label + ": %{x:,.0f}"
                + "<br>Participação: %{customdata[0]:.2%}<extra></extra>"
            ),
        )
    )
    fig.update_layout(
        title=f"Top {min(top_n, len(data))} países de {role}",
        template="plotly_white",
        height=430,
        margin={"l": 10, "r": 20, "t": 55, "b": 25},
        xaxis={"title": metric_label, "tickformat": ",.3s", "gridcolor": "#E8EEE9"},
        yaxis={"title": None},
        showlegend=False,
    )
    return fig


def trade_balance_plotly(balance: pd.DataFrame, countries_each_side: int = 10):
    import plotly.graph_objects as go

    positive = balance.loc[balance["SALDO"] > 0].nlargest(countries_each_side, "SALDO")
    negative = balance.loc[balance["SALDO"] < 0].nsmallest(countries_each_side, "SALDO")
    data = pd.concat([negative, positive], ignore_index=True).drop_duplicates("CO_PAIS")
    data = data.sort_values("SALDO")
    colors = data["SALDO"].map(lambda value: "#18794E" if value > 0 else "#C43D3D")
    fig = go.Figure(
        go.Bar(
            x=data["SALDO"],
            y=data["PAIS"],
            orientation="h",
            marker={"color": colors},
            customdata=data[["EXPORTACOES", "IMPORTACOES", "SITUACAO"]],
            hovertemplate=(
                "%{y}<br>Saldo: US$ %{x:,.0f}"
                "<br>Exportações: US$ %{customdata[0]:,.0f}"
                "<br>Importações: US$ %{customdata[1]:,.0f}"
                "<br>Situação: %{customdata[2]}<extra></extra>"
            ),
        )
    )
    fig.add_vline(x=0, line_width=1.4, line_color="#6B756D")
    fig.update_layout(
        title="Maiores superávits e déficits bilaterais",
        template="plotly_white",
        height=max(460, 26 * len(data) + 100),
        margin={"l": 10, "r": 20, "t": 55, "b": 25},
        xaxis={"title": "Saldo comercial (US$)", "tickformat": ",.3s", "gridcolor": "#E8EEE9"},
        yaxis={"title": None},
        showlegend=False,
    )
    return fig


def balance_status_plotly(balance: pd.DataFrame):
    import plotly.graph_objects as go

    order = ["Superávit", "Déficit", "Zerado"]
    counts = balance["SITUACAO"].value_counts().reindex(order, fill_value=0)
    fig = go.Figure(
        go.Pie(
            labels=counts.index,
            values=counts.values,
            hole=0.65,
            marker={"colors": ["#18794E", "#C43D3D", "#8A938C"]},
            textinfo="label+value",
            hovertemplate="%{label}: %{value} países (%{percent})<extra></extra>",
        )
    )
    fig.update_layout(
        title="Situação por número de países",
        template="plotly_white",
        height=420,
        margin={"l": 10, "r": 10, "t": 55, "b": 25},
        showlegend=False,
        annotations=[
            {
                "text": f"{int(counts.sum())}<br><span style='font-size:12px'>países</span>",
                "x": 0.5,
                "y": 0.5,
                "font": {"size": 22, "color": "#173A25"},
                "showarrow": False,
            }
        ],
    )
    return fig


def section301_status_plotly(exposure: pd.DataFrame):
    import plotly.graph_objects as go

    order = [
        "Sem correspondência - potencialmente afetado",
        "Correspondência com isenção no SH6",
        "Correspondência condicionada no SH6",
        "Correspondência mista no SH6",
    ]
    labels = {
        order[0]: "Potencialmente afetado",
        order[1]: "Correspondência com isenção",
        order[2]: "Isenção condicionada",
        order[3]: "Correspondência mista",
    }
    totals = exposure.groupby("SITUACAO_301")["VL_FOB"].sum().reindex(order, fill_value=0)
    fig = go.Figure(
        go.Pie(
            labels=[labels[value] for value in totals.index],
            values=totals.values,
            hole=0.64,
            marker={"colors": ["#C43D3D", "#18794E", "#D28B20", "#5B6FB5"]},
            textinfo="label+percent",
            hovertemplate="%{label}<br>US$ %{value:,.0f}<br>%{percent}<extra></extra>",
        )
    )
    fig.update_layout(
        title="Distribuição do valor exportado aos EUA",
        template="plotly_white",
        height=440,
        margin={"l": 10, "r": 10, "t": 60, "b": 25},
        showlegend=False,
        annotations=[
            {
                "text": "SH6<br><span style='font-size:11px'>triagem indicativa</span>",
                "x": 0.5,
                "y": 0.5,
                "font": {"size": 18, "color": "#173A25"},
                "showarrow": False,
            }
        ],
    )
    return fig


def section301_products_plotly(exposure: pd.DataFrame, top_n: int = 15):
    import plotly.graph_objects as go

    colors = {
        "Sem correspondência - potencialmente afetado": "#C43D3D",
        "Correspondência com isenção no SH6": "#18794E",
        "Correspondência condicionada no SH6": "#D28B20",
        "Correspondência mista no SH6": "#5B6FB5",
    }
    data = exposure.nlargest(top_n, "VL_FOB").copy().sort_values("VL_FOB")
    data["ROTULO"] = data.apply(
        lambda row: f"{str(row['NO_NCM_POR'])[:46]} · {row['CO_NCM']}", axis=1
    )
    fig = go.Figure(
        go.Bar(
            x=data["VL_FOB"],
            y=data["ROTULO"],
            orientation="h",
            marker={"color": data["SITUACAO_301"].map(colors)},
            customdata=data[["CO_SH6", "SITUACAO_301", "PARTICIPACAO_FOB_EUA"]],
            hovertemplate=(
                "%{y}<br>Valor FOB: US$ %{x:,.0f}"
                "<br>SH6: %{customdata[0]}"
                "<br>Situação: %{customdata[1]}"
                "<br>Participação: %{customdata[2]:.2%}<extra></extra>"
            ),
        )
    )
    fig.update_layout(
        title=f"Top {min(top_n, len(data))} NCMs exportadas aos EUA",
        template="plotly_white",
        height=max(460, 29 * len(data) + 110),
        margin={"l": 10, "r": 20, "t": 60, "b": 25},
        xaxis={"title": "Valor FOB (US$)", "tickformat": ",.3s", "gridcolor": "#E8EEE9"},
        yaxis={"title": None},
        showlegend=False,
    )
    return fig
