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
    previous = (
        history.loc[history["ANO"] == selected_year - 1, ["MES", "VALOR"]]
        .rename(columns={"VALOR": "ANTERIOR"})
    )
    historical = history.loc[history["ANO"] < selected_year]
    if historical.empty:
        band = pd.DataFrame(
            columns=["MES", "MIN_5A", "MAX_5A", "MEDIA_5A", "N_ANOS_BANDA"]
        )
    else:
        band = (
            historical.groupby("MES", as_index=False)
            .agg(
                MIN_5A=("VALOR", "min"),
                MAX_5A=("VALOR", "max"),
                MEDIA_5A=("VALOR", "mean"),
                N_ANOS_BANDA=("ANO", "nunique"),
            )
        )
    profile = (
        grid.merge(current, on="MES", how="left")
        .merge(previous, on="MES", how="left")
        .merge(band, on="MES", how="left")
    )
    previous_nonzero = profile["ANTERIOR"].where(profile["ANTERIOR"] != 0)
    mean_nonzero = profile["MEDIA_5A"].where(profile["MEDIA_5A"] != 0)
    profile["VAR_1A"] = profile["ATUAL"].sub(profile["ANTERIOR"]).div(previous_nonzero)
    profile["DESVIO_MEDIA_5A"] = profile["ATUAL"].sub(profile["MEDIA_5A"]).div(mean_nonzero)
    profile["MES_LABEL"] = profile["MES"].map(MONTH_NAMES)
    return profile


def monthly_variation_plotly(profile: pd.DataFrame, selected_year: int):
    import plotly.graph_objects as go

    data = profile.loc[profile["VAR_1A"].notna()].copy()
    colors = data["VAR_1A"].map(lambda value: "#18794E" if value >= 0 else "#C43D3D")
    fig = go.Figure(
        go.Bar(
            x=data["MES_LABEL"],
            y=data["VAR_1A"],
            marker={"color": colors},
            customdata=data[["ATUAL", "ANTERIOR", "DESVIO_MEDIA_5A"]],
            hovertemplate=(
                "%{x}<br>Variação anual: %{y:.1%}"
                "<br>Ano selecionado: %{customdata[0]:,.2f}"
                "<br>Ano anterior: %{customdata[1]:,.2f}"
                "<br>Contra média histórica: %{customdata[2]:.1%}<extra></extra>"
            ),
        )
    )
    fig.add_hline(y=0, line_color="#6B756D", line_width=1.2)
    fig.update_layout(
        title=f"Variação mensal de {selected_year} contra {selected_year - 1}",
        template="plotly_white",
        height=430,
        margin={"l": 20, "r": 20, "t": 60, "b": 45},
        xaxis={"title": None},
        yaxis={"title": "Variação", "tickformat": ".0%", "gridcolor": "#E8EEE9"},
        showlegend=False,
    )
    return fig


def value_ranking_plotly(
    data: pd.DataFrame,
    label_column: str,
    value_column: str,
    title: str,
    top_n: int = 15,
    color: str = "#18794E",
):
    """Ranking horizontal compacto para produtos e composições."""
    import plotly.graph_objects as go

    ranked = data.nlargest(top_n, value_column).sort_values(value_column)
    fig = go.Figure(
        go.Bar(
            x=ranked[value_column],
            y=ranked[label_column],
            orientation="h",
            marker={"color": color},
            hovertemplate="%{y}<br>Valor FOB: US$ %{x:,.0f}<extra></extra>",
        )
    )
    fig.update_layout(
        title=title,
        template="plotly_white",
        height=max(410, 31 * len(ranked) + 105),
        margin={"l": 20, "r": 30, "t": 60, "b": 60},
        xaxis={
            "title": "Valor FOB (US$)", "tickformat": ",.3s",
            "gridcolor": "#E8EEE9", "automargin": True,
        },
        yaxis={"title": None, "automargin": True},
        showlegend=False,
    )
    return fig


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
            textinfo="percent",
            textposition="inside",
            hovertemplate="%{label}: %{value} países (%{percent})<extra></extra>",
        )
    )
    fig.update_layout(
        title="Situação por número de países",
        template="plotly_white",
        height=420,
        margin={"l": 10, "r": 10, "t": 55, "b": 65},
        showlegend=True,
        legend={"orientation": "h", "y": -0.08, "x": 0.5, "xanchor": "center"},
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
    status_labels = [labels[value] for value in totals.index]
    shares = totals / totals.sum() if totals.sum() else totals
    fig = go.Figure(
        go.Bar(
            x=totals.values,
            y=status_labels,
            orientation="h",
            marker={"color": ["#C43D3D", "#18794E", "#D28B20", "#5B6FB5"]},
            customdata=shares.values,
            text=[f"{value:.1%}" for value in shares],
            textposition="outside",
            cliponaxis=False,
            hovertemplate="%{y}<br>US$ %{x:,.0f}<br>%{customdata:.1%}<extra></extra>",
        )
    )
    fig.update_layout(
        title="Distribuição do valor exportado aos EUA",
        template="plotly_white",
        height=340,
        margin={"l": 20, "r": 80, "t": 60, "b": 55},
        showlegend=False,
        xaxis={"title": "Valor FOB (US$)", "tickformat": ",.3s", "gridcolor": "#E8EEE9"},
        yaxis={"title": None, "automargin": True, "categoryorder": "array", "categoryarray": status_labels[::-1]},
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


def section301_impact_ranking_plotly(
    data: pd.DataFrame,
    label_column: str,
    title: str,
    top_n: int = 10,
    color: str = "#B42318",
):
    """Ranking horizontal reutilizado nos recortes executivos da Seção 301."""
    import plotly.graph_objects as go

    columns = [label_column, "VALOR_POTENCIALMENTE_AFETADO"]
    has_tonnes = "TONELADAS_POTENCIALMENTE_AFETADAS" in data.columns
    has_share = "PARTICIPACAO_NO_AFETADO_BRASIL" in data.columns
    if has_tonnes:
        columns.append("TONELADAS_POTENCIALMENTE_AFETADAS")
    if has_share:
        columns.append("PARTICIPACAO_NO_AFETADO_BRASIL")
    ranked = (
        data[columns]
        .nlargest(top_n, "VALOR_POTENCIALMENTE_AFETADO")
        .sort_values("VALOR_POTENCIALMENTE_AFETADO")
    )
    custom_columns: list[str] = []
    hover = "%{y}<br>Potencialmente afetado: US$ %{x:,.0f}"
    if has_tonnes:
        custom_columns.append("TONELADAS_POTENCIALMENTE_AFETADAS")
        hover += "<br>Volume potencial: %{customdata[0]:,.1f} t"
    if has_share:
        share_index = len(custom_columns)
        custom_columns.append("PARTICIPACAO_NO_AFETADO_BRASIL")
        hover += f"<br>Participação no total: %{{customdata[{share_index}]:.2%}}"
    customdata = ranked[custom_columns] if custom_columns else None
    fig = go.Figure(
        go.Bar(
            x=ranked["VALOR_POTENCIALMENTE_AFETADO"],
            y=ranked[label_column],
            orientation="h",
            marker={"color": color},
            customdata=customdata,
            hovertemplate=hover + "<extra></extra>",
        )
    )
    fig.update_layout(
        title=title,
        template="plotly_white",
        height=max(400, 32 * len(ranked) + 110),
        margin={"l": 20, "r": 35, "t": 60, "b": 65},
        xaxis={
            "title": "Valor potencialmente afetado (US$)",
            "tickformat": ",.3s",
            "gridcolor": "#E8EEE9",
            "automargin": True,
        },
        yaxis={"title": None, "automargin": True},
        showlegend=False,
    )
    return fig


def section301_state_trade_plotly(data: pd.DataFrame, top_n: int = 15):
    """Compara exportações totais, vendas aos EUA e parcela potencialmente afetada por UF."""
    import plotly.graph_objects as go

    ranked = (
        data.nlargest(top_n, "VALOR_POTENCIALMENTE_AFETADO")
        .sort_values("VALOR_POTENCIALMENTE_AFETADO")
        .copy()
    )
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=ranked["EXPORTACOES_MUNDO"],
            y=ranked["UF_LABEL"],
            orientation="h",
            name="Exportações totais",
            marker={"color": "#DCE3DE"},
            width=0.76,
            hovertemplate="%{y}<br>Exportações totais: US$ %{x:,.0f}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Bar(
            x=ranked["EXPORTACOES_EUA"],
            y=ranked["UF_LABEL"],
            orientation="h",
            name="Exportações aos EUA",
            marker={"color": "#35658D"},
            width=0.50,
            customdata=ranked[["PARTICIPACAO_EUA"]],
            hovertemplate=(
                "%{y}<br>Exportações aos EUA: US$ %{x:,.0f}"
                "<br>Participação dos EUA: %{customdata[0]:.1%}<extra></extra>"
            ),
        )
    )
    fig.add_trace(
        go.Bar(
            x=ranked["VALOR_POTENCIALMENTE_AFETADO"],
            y=ranked["UF_LABEL"],
            orientation="h",
            name="Potencialmente afetado",
            marker={"color": "#B42318"},
            width=0.25,
            customdata=ranked[["PARTICIPACAO_AFETADA_NOS_EUA", "EXPOSICAO_EXPORTACOES_UF"]],
            hovertemplate=(
                "%{y}<br>Potencialmente afetado: US$ %{x:,.0f}"
                "<br>Das vendas aos EUA: %{customdata[0]:.1%}"
                "<br>Das exportações totais da UF: %{customdata[1]:.1%}<extra></extra>"
            ),
        )
    )
    fig.update_layout(
        title="Exportações totais, vendas aos EUA e valor potencialmente afetado",
        template="plotly_white",
        barmode="overlay",
        height=max(470, 34 * len(ranked) + 125),
        margin={"l": 20, "r": 30, "t": 70, "b": 75},
        xaxis={
            "title": "Valor FOB (US$)",
            "tickformat": ",.3s",
            "gridcolor": "#E8EEE9",
            "automargin": True,
        },
        yaxis={"title": None, "automargin": True},
        legend={"orientation": "h", "y": -0.13, "x": 0, "xanchor": "left"},
    )
    return fig


def section301_state_dependency_plotly(data: pd.DataFrame):
    """Relaciona dependência dos EUA, alcance potencial e valor exposto por UF."""
    import plotly.graph_objects as go

    work = data.loc[data["VALOR_POTENCIALMENTE_AFETADO"] > 0].copy()
    if work.empty:
        return go.Figure()
    max_value = float(work["VALOR_POTENCIALMENTE_AFETADO"].max())
    size_ref = 2.0 * max_value / (52.0**2) if max_value > 0 else 1.0
    colors = work["EUA_MAIOR_CLIENTE"].map({"Sim": "#B42318", "Não": "#35658D"})
    fig = go.Figure(
        go.Scatter(
            x=work["PARTICIPACAO_EUA"],
            y=work["PARTICIPACAO_AFETADA_NOS_EUA"],
            mode="markers+text",
            text=work["UF"],
            textposition="top center",
            marker={
                "size": work["VALOR_POTENCIALMENTE_AFETADO"],
                "sizemode": "area",
                "sizeref": size_ref,
                "sizemin": 8,
                "color": colors,
                "opacity": 0.78,
                "line": {"color": "#FFFFFF", "width": 1.2},
            },
            customdata=work[[
                "UF_LABEL", "EXPORTACOES_MUNDO", "EXPORTACOES_EUA",
                "VALOR_POTENCIALMENTE_AFETADO", "EXPOSICAO_EXPORTACOES_UF",
                "EUA_MAIOR_CLIENTE",
            ]],
            hovertemplate=(
                "<b>%{customdata[0]}</b>"
                "<br>Participação dos EUA: %{x:.1%}"
                "<br>Parcela potencial das vendas aos EUA: %{y:.1%}"
                "<br>Exportações totais: US$ %{customdata[1]:,.0f}"
                "<br>Exportações aos EUA: US$ %{customdata[2]:,.0f}"
                "<br>Valor potencial: US$ %{customdata[3]:,.0f}"
                "<br>Exposição nas exportações da UF: %{customdata[4]:.1%}"
                "<br>EUA é o maior cliente: %{customdata[5]}<extra></extra>"
            ),
        )
    )
    fig.update_layout(
        title="Dependência do mercado americano e alcance potencial das tarifas",
        template="plotly_white",
        height=560,
        margin={"l": 30, "r": 35, "t": 70, "b": 70},
        showlegend=False,
        xaxis={
            "title": "Participação dos EUA nas exportações da UF",
            "tickformat": ".0%",
            "rangemode": "tozero",
            "gridcolor": "#E8EEE9",
        },
        yaxis={
            "title": "Parcela potencialmente afetada das vendas aos EUA",
            "tickformat": ".0%",
            "rangemode": "tozero",
            "gridcolor": "#E8EEE9",
        },
    )
    return fig


def us_effective_tariff_plotly(data: pd.DataFrame):
    """Série mensal da tarifa efetiva cobrada pelos EUA sobre produtos brasileiros."""
    import plotly.graph_objects as go

    series = data.sort_values("DATA").copy()
    tick_data = series.iloc[::6].copy()
    if not tick_data.empty and tick_data.iloc[-1]["DATA"] != series.iloc[-1]["DATA"]:
        tick_data = pd.concat([tick_data, series.tail(1)], ignore_index=True)
    tick_text = tick_data["DATA"].map(
        lambda value: f"{MONTH_NAMES[int(value.month)]}/{int(value.year)}"
    )

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=series["DATA"],
            y=series["TARIFA_EFETIVA_PCT"],
            mode="lines",
            line={"color": "#1D2821", "width": 2.2},
            customdata=series[[
                "IMPORTACOES_CONSUMO_USD",
                "DIREITOS_ADUANEIROS_USD",
                "TARIFA_BASE_TRIBUTAVEL_PCT",
            ]],
            name="Tarifa efetiva total",
            hovertemplate=(
                "%{x|%m/%Y}<br><b>Tarifa efetiva: %{y:.2f}%</b>"
                "<br>Importações para consumo: US$ %{customdata[0]:,.0f}"
                "<br>Direitos aduaneiros: US$ %{customdata[1]:,.0f}"
                "<br>Taxa sobre a base tributável: %{customdata[2]:.2f}%"
                "<extra></extra>"
            ),
        )
    )
    latest = series.iloc[-1]
    fig.add_trace(
        go.Scatter(
            x=[latest["DATA"]],
            y=[latest["TARIFA_EFETIVA_PCT"]],
            mode="markers",
            marker={"size": 9, "color": "#1F633F", "line": {"color": "#FFFFFF", "width": 2}},
            showlegend=False,
            hoverinfo="skip",
        )
    )
    fig.add_annotation(
        x=latest["DATA"],
        y=latest["TARIFA_EFETIVA_PCT"],
        text=f"{latest['TARIFA_EFETIVA_PCT']:.1f}%",
        showarrow=True,
        arrowhead=0,
        arrowcolor="#617068",
        ax=-34,
        ay=-34,
        bgcolor="#FFFFFF",
        bordercolor="#C9D2CC",
        borderpad=5,
        font={"color": "#17472F", "size": 12},
    )
    fig.update_layout(
        title={
            "text": "Tarifa efetiva dos EUA sobre importações originárias do Brasil",
            "font": {"size": 20, "color": "#1D2821"},
            "x": 0,
        },
        template="plotly_white",
        height=510,
        margin={"l": 25, "r": 45, "t": 75, "b": 70},
        hovermode="x unified",
        showlegend=False,
        xaxis={
            "title": None,
            "tickmode": "array",
            "tickvals": tick_data["DATA"],
            "ticktext": tick_text,
            "tickangle": -42,
            "showgrid": False,
            "linecolor": "#AEB9B1",
        },
        yaxis={
            "title": "Tarifa efetiva (%)",
            "ticksuffix": "%",
            "rangemode": "tozero",
            "gridcolor": "#E5EAE6",
            "zeroline": False,
        },
    )
    return fig
