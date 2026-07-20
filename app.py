from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path

import pandas as pd
import streamlit as st

from src.charts import (
    balance_status_plotly,
    country_ranking_plotly,
    monthly_matplotlib,
    monthly_plotly,
    monthly_variation_plotly,
    prepare_monthly_profile,
    section301_impact_ranking_plotly,
    section301_products_plotly,
    section301_state_dependency_plotly,
    section301_state_trade_plotly,
    section301_status_plotly,
    trade_balance_plotly,
    us_effective_tariff_plotly,
    value_ranking_plotly,
)
from src.queries import (
    LEVELS,
    FilterState,
    available_months,
    available_years,
    country_composition,
    country_ranking,
    database_token,
    filter_options,
    hierarchy_table,
    monthly_history,
    quality_report,
    section301_exposure,
    section301_sector_impact,
    section301_state_impact,
    section301_state_products,
    summary_metrics,
    trade_balance_by_country,
)
from src.utils import MONTH_NAMES, format_compact


PROJECT_DIR = Path(__file__).resolve().parent
FULL_DATABASE = PROJECT_DIR / "data" / "processed" / "comex.duckdb"
WEB_DATABASE = PROJECT_DIR / "data" / "processed" / "comex_web.duckdb"
DATABASE = Path(
    os.environ.get(
        "COMEX_DATABASE",
        str(WEB_DATABASE if WEB_DATABASE.exists() else FULL_DATABASE),
    )
).expanduser().resolve()
SECTION301_REFERENCE = PROJECT_DIR / "data" / "reference" / "section301_exemptions_sh6.csv"
US_TARIFF_REFERENCE = PROJECT_DIR / "data" / "reference" / "us_effective_tariff_brazil.csv"
UF_NAMES = {
    "AC": "Acre", "AL": "Alagoas", "AP": "Amapá", "AM": "Amazonas",
    "BA": "Bahia", "CE": "Ceará", "DF": "Distrito Federal", "ES": "Espírito Santo",
    "GO": "Goiás", "MA": "Maranhão", "MT": "Mato Grosso", "MS": "Mato Grosso do Sul",
    "MG": "Minas Gerais", "PA": "Pará", "PB": "Paraíba", "PR": "Paraná",
    "PE": "Pernambuco", "PI": "Piauí", "RJ": "Rio de Janeiro", "RN": "Rio Grande do Norte",
    "RS": "Rio Grande do Sul", "RO": "Rondônia", "RR": "Roraima", "SC": "Santa Catarina",
    "SP": "São Paulo", "SE": "Sergipe", "TO": "Tocantins",
}


st.set_page_config(
    page_title="Painel do Comércio Exterior",
    page_icon="↗",
    layout="wide",
    initial_sidebar_state="expanded",
)


def _inject_css() -> None:
    st.markdown(
        """
        <style>
        :root {
            --brand: #1F633F;
            --brand-dark: #17472F;
            --brand-soft: #EDF4EF;
            --ink: #1D2821;
            --muted: #66706A;
            --line: #D8DEDA;
            --surface: #FFFFFF;
            --canvas: #F5F6F4;
        }
        [data-testid="stAppViewContainer"] {
            background: var(--canvas);
        }
        [data-testid="stHeader"] { background: rgba(245,246,244,.94); }
        [data-testid="stSidebar"] {
            background: #F8F9F7;
            border-right: 1px solid var(--line);
        }
        [data-testid="stSidebar"] h2 { color: var(--ink); letter-spacing: -.01em; }
        .block-container { max-width: 1420px; padding-top: 1rem; padding-bottom: 3rem; }
        .hero-panel {
            background: var(--surface); color: var(--ink);
            border: 1px solid var(--line); border-left: 5px solid var(--brand);
            border-radius: 5px; padding: 1.45rem 1.6rem 1.35rem;
            margin-bottom: 1rem;
        }
        .hero-kicker { color: var(--muted); font-size: .78rem; font-weight: 620; letter-spacing: .02em; }
        .hero-title { font-size: clamp(1.9rem, 3vw, 2.45rem); line-height: 1.12; font-weight: 690; letter-spacing: -.03em; margin: .3rem 0 .45rem; }
        .hero-subtitle { max-width: 800px; color: var(--muted); font-size: .96rem; margin-bottom: .85rem; }
        .hero-context { color: var(--brand-dark); font-size: .86rem; font-weight: 620; }
        .section-heading { margin: .35rem 0 1rem; }
        .section-kicker { color: var(--brand); letter-spacing: 0; font-size: .78rem; font-weight: 650; }
        .section-title { color: var(--ink); font-size: 1.55rem; font-weight: 680; letter-spacing: -.02em; margin-top: .18rem; }
        .section-description { color: var(--muted); font-size: .93rem; margin-top: .25rem; }
        div[data-testid="stMetric"] {
            background: var(--surface); border: 1px solid var(--line);
            border-radius: 6px; padding: .9rem 1rem;
        }
        div[data-testid="stMetric"] label { color: var(--muted); font-weight: 620; }
        div[data-testid="stMetricValue"] {
            color: var(--brand-dark); letter-spacing: -.035em;
            font-size: clamp(1.35rem, 2.25vw, 2.15rem); white-space: nowrap;
        }
        .metric-grid {
            display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
            gap: 1rem; margin: .25rem 0 1.15rem;
        }
        .metric-card {
            background: var(--surface); border: 1px solid var(--line);
            border-radius: 6px; padding: .95rem 1rem; min-width: 0;
        }
        .metric-card-label { color: var(--muted); font-size: .86rem; font-weight: 620; }
        .metric-card-value {
            color: var(--brand-dark); font-size: clamp(1.45rem, 2.25vw, 2.05rem);
            line-height: 1.18; letter-spacing: -.04em; margin-top: .45rem; white-space: nowrap;
        }
        .metric-card-status { font-size: .78rem; font-weight: 680; margin-top: .5rem; }
        .status-positive { color: #18794E; }
        .status-negative { color: #C43D3D; }
        .status-neutral { color: #68736B; }
        [data-testid="stVerticalBlockBorderWrapper"] {
            background: var(--surface); border-color: var(--line) !important;
            border-radius: 6px;
        }
        .stTabs [data-baseweb="tab-list"] { gap: .2rem; border-bottom: 1px solid var(--line); }
        .stTabs [data-baseweb="tab"] { height: 3rem; padding: 0 .85rem; border-radius: 0; font-weight: 580; }
        .stTabs [aria-selected="true"] { background: transparent; color: var(--brand-dark); font-weight: 680; }
        .stButton > button, .stDownloadButton > button {
            border-radius: 4px; border-color: #B8C5BC; color: var(--brand-dark); font-weight: 620;
        }
        div[data-testid="stDataFrame"] { border: 1px solid var(--line); border-radius: 4px; overflow: hidden; }
        .footer-note { color: #758078; font-size: .78rem; text-align: center; padding-top: 2rem; }
        .executive-banner {
            background: #F8F6EE; border: 1px solid #DDD6BF; border-left: 4px solid #9A762E;
            border-radius: 4px; padding: .9rem 1rem; margin: .3rem 0 1.1rem;
            color: #4F452F;
        }
        .executive-banner strong { color: #6D4C0C; }
        .stTabs .stTabs [data-baseweb="tab-list"] {
            background: transparent; padding: 0; border: 0; border-bottom: 1px solid var(--line);
            border-radius: 0; gap: .15rem;
        }
        .stTabs .stTabs [data-baseweb="tab"] { height: 2.7rem; border-radius: 0; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _hero(state: FilterState) -> None:
    flow = "Exportações" if state.flow == "EXP" else "Importações"
    months = "Todos os meses disponíveis" if len(state.months) == 12 else f"{len(state.months)} mês(es) selecionado(s)"
    st.markdown(
        f"""
        <div class="hero-panel">
            <div class="hero-kicker">Comércio exterior brasileiro</div>
            <div class="hero-title">Painel do Comércio Exterior</div>
            <div class="hero-subtitle">Dados da SECEX organizados por produto, setor, país e unidade da Federação.</div>
            <div class="hero-context">{flow} · {state.year} · {months}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _section_header(kicker: str, title: str, description: str) -> None:
    st.markdown(
        f"""
        <div class="section-heading">
            <div class="section-kicker">{kicker}</div>
            <div class="section-title">{title}</div>
            <div class="section-description">{description}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


@st.cache_data(show_spinner=False)
def cached_years(database: str, flow: str, db_version: tuple[int, int]) -> list[int]:
    return available_years(Path(database), flow)


@st.cache_data(show_spinner=False)
def cached_months(database: str, flow: str, year: int, db_version: tuple[int, int]) -> list[int]:
    return available_months(Path(database), flow, year)


@st.cache_data(show_spinner=False)
def cached_options(
    database: str,
    state: FilterState,
    attribute: str,
    db_version: tuple[int, int],
) -> pd.DataFrame:
    return filter_options(Path(database), state, attribute)


@st.cache_data(show_spinner=False)
def cached_summary(database: str, state: FilterState, db_version: tuple[int, int]):
    return summary_metrics(Path(database), state)


@st.cache_data(show_spinner=False)
def cached_hierarchy(
    database: str,
    state: FilterState,
    level: str,
    db_version: tuple[int, int],
) -> pd.DataFrame:
    return hierarchy_table(Path(database), state, level)


@st.cache_data(show_spinner=False)
def cached_history(
    database: str,
    state: FilterState,
    metric: str,
    daily_average: bool,
    db_version: tuple[int, int],
) -> tuple[pd.DataFrame, list[int]]:
    return monthly_history(Path(database), state, metric, daily_average)


@st.cache_data(show_spinner=False)
def cached_ranking(
    database: str,
    state: FilterState,
    metric: str,
    top_n: int,
    db_version: tuple[int, int],
) -> pd.DataFrame:
    return country_ranking(Path(database), state, metric, top_n=top_n)


@st.cache_data(show_spinner=False)
def cached_country_composition(
    database: str,
    state: FilterState,
    country_code: str,
    level: str,
    db_version: tuple[int, int],
) -> pd.DataFrame:
    return country_composition(Path(database), state, country_code, level)


@st.cache_data(show_spinner=False)
def cached_balance(
    database: str,
    state: FilterState,
    db_version: tuple[int, int],
) -> pd.DataFrame:
    return trade_balance_by_country(Path(database), state)


@st.cache_data(show_spinner=False)
def cached_section301(
    database: str,
    state: FilterState,
    reference_csv: str,
    db_version: tuple[int, int],
    reference_version: tuple[int, int],
) -> pd.DataFrame:
    return section301_exposure(Path(database), state, Path(reference_csv))


@st.cache_data(show_spinner=False)
def cached_section301_sectors(
    database: str,
    state: FilterState,
    reference_csv: str,
    level: str,
    db_version: tuple[int, int],
    reference_version: tuple[int, int],
) -> pd.DataFrame:
    return section301_sector_impact(Path(database), state, Path(reference_csv), level)


@st.cache_data(show_spinner=False)
def cached_section301_states(
    database: str,
    state: FilterState,
    reference_csv: str,
    db_version: tuple[int, int],
    reference_version: tuple[int, int],
) -> pd.DataFrame:
    return section301_state_impact(Path(database), state, Path(reference_csv))


@st.cache_data(show_spinner=False)
def cached_section301_state_products(
    database: str,
    state: FilterState,
    reference_csv: str,
    uf: str,
    level: str,
    db_version: tuple[int, int],
    reference_version: tuple[int, int],
) -> pd.DataFrame:
    return section301_state_products(
        Path(database), state, Path(reference_csv), uf=uf, level=level
    )


@st.cache_data(show_spinner=False)
def cached_us_effective_tariff(
    reference_csv: str,
    reference_version: tuple[int, int],
) -> pd.DataFrame:
    data = pd.read_csv(reference_csv, sep=";")
    required = {
        "DATA", "IMPORTACOES_CONSUMO_USD", "DIREITOS_ADUANEIROS_USD",
        "BASE_TRIBUTAVEL_USD", "TARIFA_EFETIVA_PCT", "TARIFA_BASE_TRIBUTAVEL_PCT",
    }
    missing = required.difference(data.columns)
    if missing:
        raise ValueError(f"Colunas ausentes na série tarifária: {', '.join(sorted(missing))}")
    data["DATA"] = pd.to_datetime(data["DATA"], errors="coerce")
    numeric_columns = required.difference({"DATA"})
    for column in numeric_columns:
        data[column] = pd.to_numeric(data[column], errors="coerce")
    data = data.dropna(subset=list(required)).sort_values("DATA").drop_duplicates("DATA")
    calculated = data["DIREITOS_ADUANEIROS_USD"].div(
        data["IMPORTACOES_CONSUMO_USD"].replace(0, pd.NA)
    ).mul(100)
    if calculated.sub(data["TARIFA_EFETIVA_PCT"]).abs().max() > 0.001:
        raise ValueError("A tarifa efetiva não confere com direitos ÷ importações para consumo.")
    return data.reset_index(drop=True)


@st.cache_data(show_spinner=False)
def cached_quality(database: str, db_version: tuple[int, int]):
    report = quality_report(Path(database))
    return report, report.attrs.get("files", pd.DataFrame())


def _multiselect_filter(
    state: FilterState,
    attribute: str,
    title: str,
    db_version: tuple[int, int],
    container,
) -> FilterState:
    options = cached_options(str(DATABASE), state, attribute, db_version)
    codes = options["CODIGO"].tolist()
    labels = dict(zip(options["CODIGO"], options["DESCRICAO"], strict=False))
    selected = container.multiselect(
        title,
        options=codes,
        format_func=lambda code: f"{code} — {labels.get(code, code)}" if code != labels.get(code) else code,
        key=f"filter_{attribute}",
        placeholder="Todos",
    )
    return replace(state, **{attribute: tuple(selected)})


def _filters(db_version: tuple[int, int]) -> FilterState:
    st.sidebar.header("Filtros da análise")
    st.sidebar.caption("Os filtros são aplicados simultaneamente a gráficos e tabelas.")
    flow_label = st.sidebar.radio("Fluxo", ["Exportação", "Importação"], horizontal=True)
    flow = "EXP" if flow_label == "Exportação" else "IMP"
    years = cached_years(str(DATABASE), flow, db_version)
    if not years:
        st.error(f"Não há dados disponíveis para {flow_label.lower()}.")
        st.stop()
    year = st.sidebar.selectbox("Ano", years, index=0)
    available = cached_months(str(DATABASE), flow, year, db_version)
    months = st.sidebar.multiselect(
        "Meses",
        options=available,
        default=available,
        format_func=lambda month: MONTH_NAMES[month],
        key=f"months_{flow}_{year}",
    )
    state = FilterState(flow=flow, year=year, months=tuple(months))
    state = _multiselect_filter(state, "sectors", "Setor", db_version, st.sidebar)
    state = _multiselect_filter(state, "categories", "Categoria de uso", db_version, st.sidebar)
    classification = st.sidebar.expander("Classificação SH/NCM", expanded=False)
    with classification:
        state = _multiselect_filter(state, "sh2", "SH2", db_version, classification)
        state = _multiselect_filter(state, "sh4", "SH4", db_version, classification)
        state = _multiselect_filter(state, "sh6", "SH6", db_version, classification)
        state = _multiselect_filter(state, "ncm", "NCM (8 dígitos)", db_version, classification)
    return state


def _overview(state: FilterState, db_version: tuple[int, int]) -> None:
    _section_header(
        "Série mensal",
        "Evolução do fluxo selecionado",
        "Compare o ano escolhido com a faixa observada nos cinco anos anteriores.",
    )
    metrics = cached_summary(str(DATABASE), state, db_version)
    weight_kg = metrics["KG_LIQUIDO"]
    weight_tonnes = 0 if weight_kg is None or pd.isna(weight_kg) else weight_kg / 1000
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Valor FOB", format_compact(metrics["VL_FOB"], "US$ "))
    c2.metric("Peso líquido", format_compact(weight_tonnes, "") + " t")
    c3.metric("FOB por kg", "—" if pd.isna(metrics["FOB_POR_KG"]) else f"US$ {metrics['FOB_POR_KG']:,.3f}")
    c4.metric("NCMs no recorte", f"{int(metrics['NCMS'] or 0):,}".replace(",", "."))

    with st.container(border=True):
        metric_options = {
            "Valor FOB": "VL_FOB",
            "Peso líquido (t)": "KG_LIQUIDO",
            "Valor médio (US$/kg)": "FOB_POR_KG",
        }
        left, right = st.columns([2, 1], vertical_alignment="bottom")
        metric_label = left.radio(
            "Indicador mensal", list(metric_options), horizontal=True, key="monthly_metric_v2"
        )
        metric = metric_options[metric_label]
        if metric == "FOB_POR_KG":
            right.caption("Preço unitário não é dividido por dias úteis.")
            daily_average = False
        else:
            daily_average = right.toggle("Média por dia útil", value=False, key="monthly_daily_v2")
        history, historical_years = cached_history(
            str(DATABASE), state, metric, daily_average, db_version
        )
        if metric == "KG_LIQUIDO":
            history = history.copy()
            history["VALOR"] = history["VALOR"] / 1000
        profile = prepare_monthly_profile(history, state.year, state.months)
        if profile["ATUAL"].notna().sum() == 0:
            st.warning("Não há observações para o recorte selecionado.")
            return

        aggregate = "mean" if metric == "FOB_POR_KG" else "sum"
        current_value = getattr(profile["ATUAL"], aggregate)(min_count=1) if aggregate == "sum" else profile["ATUAL"].mean()
        previous_value = getattr(profile["ANTERIOR"], aggregate)(min_count=1) if aggregate == "sum" else profile["ANTERIOR"].mean()
        annual_change = (
            (current_value - previous_value) / previous_value
            if pd.notna(previous_value) and previous_value != 0 else pd.NA
        )
        peak = profile.loc[profile["ATUAL"].idxmax()] if profile["ATUAL"].notna().any() else None
        unit_prefix = "US$ " if metric in {"VL_FOB", "FOB_POR_KG"} else ""
        unit_suffix = " t" if metric == "KG_LIQUIDO" else ""

        def format_monthly_value(value: float) -> str:
            if pd.isna(value):
                return "—"
            if metric == "FOB_POR_KG":
                return f"US$ {value:,.3f}".replace(",", "X").replace(".", ",").replace("X", ".")
            return format_compact(value, unit_prefix) + unit_suffix

        k1, k2, k3, k4 = st.columns(4)
        period_label = "Média mensal" if metric == "FOB_POR_KG" else "Acumulado selecionado"
        k1.metric(period_label, format_monthly_value(current_value))
        k2.metric(
            f"Mesmo período de {state.year - 1}",
            format_monthly_value(previous_value),
        )
        k3.metric(
            "Variação anual",
            "—" if pd.isna(annual_change) else f"{annual_change:+.1%}",
        )
        k4.metric(
            "Mês de maior nível",
            "—" if peak is None else str(peak["MES_LABEL"]),
            delta=None if peak is None else format_monthly_value(peak["ATUAL"]),
            delta_color="off",
        )

        if not historical_years:
            st.info("A base ainda não possui anos anteriores para formar comparações históricas.")
        elif len(historical_years) < 5:
            st.caption(
                f"A referência histórica usa {len(historical_years)} ano(s) disponível(is): "
                + ", ".join(map(str, historical_years))
            )

        evolution_tab, variation_tab, table_tab = st.tabs(
            ["Evolução e faixa histórica", "Variação anual", "Tabela mensal"]
        )
        with evolution_tab:
            try:
                figure = monthly_plotly(profile, state.year, metric_label, daily_average)
                st.plotly_chart(
                    figure,
                    use_container_width=True,
                    config={"displaylogo": False},
                    key="monthly_evolution_chart",
                )
            except ImportError:
                st.pyplot(monthly_matplotlib(profile, state.year, metric_label, daily_average))
        with variation_tab:
            if profile["VAR_1A"].notna().any():
                st.plotly_chart(
                    monthly_variation_plotly(profile, state.year),
                    use_container_width=True,
                    config={"displaylogo": False},
                    key="monthly_variation_chart",
                )
            else:
                st.info("Não há observações comparáveis no ano anterior para os meses selecionados.")
        with table_tab:
            st.dataframe(
                profile[[
                    "MES_LABEL", "ATUAL", "ANTERIOR", "VAR_1A", "MEDIA_5A",
                    "DESVIO_MEDIA_5A", "MIN_5A", "MAX_5A", "N_ANOS_BANDA",
                ]],
                use_container_width=True,
                hide_index=True,
                column_config={
                    "MES_LABEL": "Mês",
                    "ATUAL": st.column_config.NumberColumn(str(state.year), format="localized"),
                    "ANTERIOR": st.column_config.NumberColumn(str(state.year - 1), format="localized"),
                    "VAR_1A": st.column_config.NumberColumn("Variação anual", format="percent"),
                    "MEDIA_5A": st.column_config.NumberColumn("Média histórica", format="localized"),
                    "DESVIO_MEDIA_5A": st.column_config.NumberColumn("Contra média histórica", format="percent"),
                    "MIN_5A": st.column_config.NumberColumn("Mínimo histórico", format="localized"),
                    "MAX_5A": st.column_config.NumberColumn("Máximo histórico", format="localized"),
                    "N_ANOS_BANDA": st.column_config.NumberColumn("Anos na referência", format="%d"),
                },
            )


def _hierarchy(state: FilterState, db_version: tuple[int, int]) -> None:
    _section_header(
        "Produtos e classificações",
        "Composição do comércio exterior",
        "Navegue das grandes categorias até o NCM. Os níveis SH são exibidos com sua descrição em português.",
    )
    with st.container(border=True):
        level = st.selectbox("Nível de agregação", list(LEVELS), index=0)
        table = cached_hierarchy(str(DATABASE), state, level, db_version)
        if table.empty:
            st.info("Não há classificações para o recorte selecionado.")
            return

        def readable_classification(row: pd.Series) -> str:
            code = "" if pd.isna(row["CODIGO"]) else str(row["CODIGO"])
            description = "" if pd.isna(row["DESCRICAO"]) else str(row["DESCRICAO"]).strip()
            if level in {"Setor", "Categoria de uso"}:
                return description or code or "Não classificado"
            if not description or description == code:
                return f"{level} {code} — descrição não localizada"
            return f"{description} ({level} {code})"

        display = table.copy()
        display["TONELADAS"] = display["KG_LIQUIDO"] / 1000
        display.insert(0, "CLASSIFICACAO", display.apply(readable_classification, axis=1))
        options = display["CODIGO"].astype(str).tolist()
        option_labels = dict(zip(options, display["CLASSIFICACAO"], strict=False))
        selected_code = st.selectbox(
            "Classificação para detalhar",
            options,
            format_func=lambda code: option_labels.get(code, code),
            key=f"classification_detail_{level}",
        )
        state_attribute = {
            "Setor": "sectors", "Categoria de uso": "categories", "SH2": "sh2",
            "SH4": "sh4", "SH6": "sh6", "NCM": "ncm",
        }[level]
        detail_state = replace(state, **{state_attribute: (selected_code,)})
        overview_tab, ncm_tab, country_tab = st.tabs(
            ["Visão geral", "Principais NCM", "Principais destinos/origens"]
        )

        with overview_tab:
            st.dataframe(
                display[["CLASSIFICACAO", "TONELADAS", "VL_FOB", "PARTICIPACAO_FOB", "FOB_POR_KG"]],
                use_container_width=True,
                hide_index=True,
                height=520,
                column_config={
                    "CLASSIFICACAO": st.column_config.TextColumn("Classificação", width="large"),
                    "TONELADAS": st.column_config.NumberColumn("Peso líquido (t)", format="localized"),
                    "VL_FOB": st.column_config.NumberColumn("Valor FOB (US$)", format="localized"),
                    "PARTICIPACAO_FOB": st.column_config.NumberColumn("Participação no FOB", format="percent"),
                    "FOB_POR_KG": st.column_config.NumberColumn("Valor médio (US$/kg)", format="%.4f"),
                },
            )
            st.download_button(
                "Baixar classificação em CSV",
                data=table.to_csv(index=False, sep=";", decimal=",", encoding="utf-8-sig"),
                file_name=f"comex_{state.flow.lower()}_{state.year}_{level.lower().replace(' ', '_')}.csv",
                mime="text/csv",
            )

        with ncm_tab:
            ncm_table = cached_hierarchy(str(DATABASE), detail_state, "NCM", db_version).copy()
            if ncm_table.empty:
                st.info("Não há NCM para a classificação selecionada.")
            else:
                ncm_table["TONELADAS"] = ncm_table["KG_LIQUIDO"] / 1000
                ncm_table["ROTULO"] = (
                    ncm_table["DESCRICAO"].astype(str).str.slice(0, 58)
                    + " · " + ncm_table["CODIGO"].astype(str)
                )
                st.plotly_chart(
                    value_ranking_plotly(
                        ncm_table, "ROTULO", "VL_FOB",
                        f"Principais NCM — {option_labels.get(selected_code, selected_code)}",
                        top_n=15,
                    ),
                    use_container_width=True,
                    config={"displaylogo": False},
                    key="hierarchy_ncm_ranking_chart",
                )
                st.dataframe(
                    ncm_table[["CODIGO", "DESCRICAO", "TONELADAS", "VL_FOB", "PARTICIPACAO_FOB", "FOB_POR_KG"]],
                    use_container_width=True,
                    hide_index=True,
                    height=500,
                    column_config={
                        "CODIGO": "NCM",
                        "DESCRICAO": st.column_config.TextColumn("Descrição do produto", width="large"),
                        "TONELADAS": st.column_config.NumberColumn("Peso líquido (t)", format="localized"),
                        "VL_FOB": st.column_config.NumberColumn("Valor FOB (US$)", format="localized"),
                        "PARTICIPACAO_FOB": st.column_config.NumberColumn("Participação", format="percent"),
                        "FOB_POR_KG": st.column_config.NumberColumn("US$/kg", format="%.4f"),
                    },
                )

        with country_tab:
            countries = cached_ranking(str(DATABASE), detail_state, "VL_FOB", 25, db_version)
            if countries.empty:
                st.info("Não há parceiros para a classificação selecionada.")
            else:
                role = "destinos" if state.flow == "EXP" else "origens"
                st.plotly_chart(
                    country_ranking_plotly(countries, "Valor FOB", state.flow, top_n=15),
                    use_container_width=True,
                    config={"displaylogo": False},
                    key="hierarchy_country_ranking_chart",
                )
                st.caption(f"Principais {role} da classificação selecionada, com os mesmos filtros de ano e mês.")
                st.dataframe(
                    countries.drop(columns="CO_PAIS"),
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "PAIS": "País",
                        "VALOR": st.column_config.NumberColumn("Valor FOB (US$)", format="localized"),
                        "PARTICIPACAO": st.column_config.NumberColumn("Participação", format="percent"),
                        "VAR_1A": st.column_config.NumberColumn("Variação anual", format="percent"),
                        "VAR_2A": st.column_config.NumberColumn("Variação em 2 anos", format="percent"),
                    },
                )


def _countries(state: FilterState, db_version: tuple[int, int]) -> None:
    role = "destino" if state.flow == "EXP" else "origem"
    _section_header(
        "Países parceiros",
        f"Principais países de {role}",
        "Ranking, participação e comparação com o mesmo período de anos anteriores.",
    )
    with st.container(border=True):
        ranking_tab, composition_tab = st.tabs(["Ranking de países", "O que o Brasil comercializa com o país"])
        with ranking_tab:
            col1, col2 = st.columns(2)
            metric_label = col1.radio(
                "Ordenar por", ["Valor FOB", "Peso líquido (t)"], horizontal=True, key="country_metric"
            )
            top_n = col2.slider("Quantidade de países", min_value=5, max_value=30, value=15, step=5)
            metric = "VL_FOB" if metric_label == "Valor FOB" else "KG_LIQUIDO"
            raw_table = cached_ranking(str(DATABASE), state, metric, top_n, db_version)
            if metric == "KG_LIQUIDO":
                raw_table = raw_table.copy()
                raw_table["VALOR"] = raw_table["VALOR"] / 1000
            if raw_table.empty:
                st.info("Não há países para o recorte selecionado.")
            else:
                st.plotly_chart(
                    country_ranking_plotly(raw_table, metric_label, state.flow),
                    use_container_width=True,
                    config={"displaylogo": False},
                    key="countries_main_ranking_chart",
                )
                table = raw_table.rename(
                    columns={
                        "VALOR": metric_label.upper().replace(" ", "_"),
                        "PARTICIPACAO": "PARTICIPAÇÃO",
                        "VAR_1A": "VARIAÇÃO_1_ANO",
                        "VAR_2A": "VARIAÇÃO_2_ANOS",
                    }
                ).drop(columns="CO_PAIS")
                value_column = metric_label.upper().replace(" ", "_")
                st.dataframe(
                    table,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "PAIS": st.column_config.TextColumn("País", width="medium"),
                        value_column: st.column_config.NumberColumn(metric_label, format="localized"),
                        "PARTICIPAÇÃO": st.column_config.NumberColumn("Participação", format="percent"),
                        "VARIAÇÃO_1_ANO": st.column_config.NumberColumn("Variação vs. ano anterior", format="percent"),
                        "VARIAÇÃO_2_ANOS": st.column_config.NumberColumn("Variação vs. 2 anos", format="percent"),
                    },
                )
                st.caption("As comparações usam os mesmos meses selecionados. Base zero ou ausente é exibida sem variação.")
                st.download_button(
                    "Baixar ranking em CSV",
                    data=raw_table.to_csv(index=False, sep=";", decimal=",", encoding="utf-8-sig"),
                    file_name=f"ranking_paises_{state.flow.lower()}_{state.year}.csv",
                    mime="text/csv",
                )

        with composition_tab:
            all_countries = cached_ranking(str(DATABASE), state, "VL_FOB", 250, db_version)
            if all_countries.empty:
                st.info("Não há países para detalhar.")
            else:
                country_names = dict(zip(all_countries["CO_PAIS"], all_countries["PAIS"], strict=False))
                selected_country = st.selectbox(
                    "Selecione o país",
                    all_countries["CO_PAIS"].tolist(),
                    format_func=lambda code: country_names.get(code, code),
                    key="country_composition_selector",
                )
                selected_row = all_countries.loc[all_countries["CO_PAIS"] == selected_country].iloc[0]
                p1, p2, p3 = st.columns(3)
                p1.metric("Valor FOB com o país", format_compact(selected_row["VALOR"], "US$ "))
                p2.metric("Participação no fluxo", f"{selected_row['PARTICIPACAO']:.1%}")
                p3.metric(
                    "Variação anual",
                    "—" if pd.isna(selected_row["VAR_1A"]) else f"{selected_row['VAR_1A']:+.1%}",
                )
                sector_tab, category_tab, ncm_tab = st.tabs(["Setores", "Categorias de uso", "Principais NCM"])
                level_specs = [
                    (sector_tab, "SETOR", "Setores"),
                    (category_tab, "CATEGORIA_USO", "Categorias de uso"),
                    (ncm_tab, "NCM", "NCM"),
                ]
                for target_tab, level_code, level_title in level_specs:
                    with target_tab:
                        composition = cached_country_composition(
                            str(DATABASE), state, str(selected_country), level_code, db_version
                        )
                        if composition.empty:
                            st.info("Não há dados para este detalhamento.")
                            continue
                        composition = composition.copy()
                        composition["ROTULO"] = composition.apply(
                            lambda row: (
                                str(row["DESCRICAO"])
                                if level_code != "NCM"
                                else f"{str(row['DESCRICAO'])[:58]} · {row['CODIGO']}"
                            ),
                            axis=1,
                        )
                        action = "exportados para" if state.flow == "EXP" else "importados de"
                        st.plotly_chart(
                            value_ranking_plotly(
                                composition, "ROTULO", "VL_FOB",
                                f"{level_title} {action} {country_names.get(selected_country, selected_country)}",
                                top_n=15,
                                color="#18794E" if state.flow == "EXP" else "#2563A6",
                            ),
                            use_container_width=True,
                            config={"displaylogo": False},
                            key=f"country_composition_{level_code}_chart",
                        )
                        st.dataframe(
                            composition[["CODIGO", "DESCRICAO", "VL_FOB", "TONELADAS", "PARTICIPACAO", "NCMS"]],
                            use_container_width=True,
                            hide_index=True,
                            column_config={
                                "CODIGO": "Código" if level_code == "NCM" else "Classificação",
                                "DESCRICAO": st.column_config.TextColumn("Descrição", width="large"),
                                "VL_FOB": st.column_config.NumberColumn("Valor FOB (US$)", format="localized"),
                                "TONELADAS": st.column_config.NumberColumn("Peso líquido (t)", format="localized"),
                                "PARTICIPACAO": st.column_config.NumberColumn("Participação no país", format="percent"),
                                "NCMS": st.column_config.NumberColumn("Quantidade de NCM", format="%d"),
                            },
                        )


def _trade_balance(state: FilterState, db_version: tuple[int, int]) -> None:
    _section_header(
        "Balança comercial",
        "Saldo comercial por país",
        "Exportações menos importações para o mesmo ano, meses e recorte de produtos — independentemente do fluxo selecionado na barra lateral.",
    )
    balance = cached_balance(str(DATABASE), state, db_version)
    if balance.empty:
        st.info("Não há exportações ou importações para calcular o saldo neste recorte.")
        return

    total_exports = balance["EXPORTACOES"].sum()
    total_imports = balance["IMPORTACOES"].sum()
    total_balance = total_exports - total_imports
    overall_status = "Superávit" if total_balance > 0 else "Déficit" if total_balance < 0 else "Zerado"
    status_class = "status-positive" if total_balance > 0 else "status-negative" if total_balance < 0 else "status-neutral"
    status_symbol = "▲" if total_balance > 0 else "▼" if total_balance < 0 else "●"
    st.markdown(
        f"""
        <div class="metric-grid">
          <div class="metric-card">
            <div class="metric-card-label">Exportações</div>
            <div class="metric-card-value">{format_compact(total_exports, 'US$ ')}</div>
          </div>
          <div class="metric-card">
            <div class="metric-card-label">Importações</div>
            <div class="metric-card-value">{format_compact(total_imports, 'US$ ')}</div>
          </div>
          <div class="metric-card">
            <div class="metric-card-label">Saldo comercial</div>
            <div class="metric-card-value">{format_compact(total_balance, 'US$ ')}</div>
            <div class="metric-card-status {status_class}">{status_symbol} {overall_status}</div>
          </div>
          <div class="metric-card">
            <div class="metric-card-label">Corrente de comércio</div>
            <div class="metric-card-value">{format_compact(total_exports + total_imports, 'US$ ')}</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.container(border=True):
        graph_col, status_col = st.columns([1.75, 1])
        with graph_col:
            countries_each_side = st.slider(
                "Países em cada lado do gráfico", 5, 15, 8, key="balance_chart_countries"
            )
            st.plotly_chart(
                trade_balance_plotly(balance, countries_each_side),
                use_container_width=True,
                config={"displaylogo": False},
                key="trade_balance_country_chart",
            )
        with status_col:
            st.plotly_chart(
                balance_status_plotly(balance),
                use_container_width=True,
                config={"displaylogo": False},
                key="trade_balance_status_chart",
            )

    with st.container(border=True):
        control1, control2 = st.columns(2)
        statuses = control1.multiselect(
            "Situação",
            ["Superávit", "Déficit", "Zerado"],
            default=["Superávit", "Déficit", "Zerado"],
            key="balance_status_filter",
        )
        sort_mode = control2.selectbox(
            "Ordenar tabela por",
            ["Maior saldo", "Maior déficit", "Maior corrente de comércio", "País"],
        )
        filtered = balance.loc[balance["SITUACAO"].isin(statuses)].copy()
        if sort_mode == "Maior saldo":
            filtered = filtered.sort_values("SALDO", ascending=False)
        elif sort_mode == "Maior déficit":
            filtered = filtered.sort_values("SALDO", ascending=True)
        elif sort_mode == "Maior corrente de comércio":
            filtered = filtered.sort_values("CORRENTE_COMERCIO", ascending=False)
        else:
            filtered = filtered.sort_values("PAIS")

        display = filtered.drop(columns="CO_PAIS").rename(
            columns={
                "EXPORTACOES": "EXPORTAÇÕES",
                "IMPORTACOES": "IMPORTAÇÕES",
                "CORRENTE_COMERCIO": "CORRENTE_DE_COMÉRCIO",
                "SITUACAO": "SITUAÇÃO",
            }
        )
        status_icons = {"Superávit": "▲ Superávit", "Déficit": "▼ Déficit", "Zerado": "● Zerado"}
        display["SITUAÇÃO"] = display["SITUAÇÃO"].map(status_icons)
        st.dataframe(
            display,
            use_container_width=True,
            hide_index=True,
            height=560,
            column_config={
                "PAIS": st.column_config.TextColumn("País", width="medium"),
                "EXPORTAÇÕES": st.column_config.NumberColumn("Exportações (US$)", format="localized"),
                "IMPORTAÇÕES": st.column_config.NumberColumn("Importações (US$)", format="localized"),
                "SALDO": st.column_config.NumberColumn("Saldo (US$)", format="localized"),
                "CORRENTE_DE_COMÉRCIO": st.column_config.NumberColumn(
                    "Corrente de comércio (US$)", format="localized"
                ),
                "SITUAÇÃO": st.column_config.TextColumn("Situação", width="small"),
            },
        )
        st.download_button(
            "Baixar saldo por país em CSV",
            data=filtered.to_csv(index=False, sep=";", decimal=",", encoding="utf-8-sig"),
            file_name=f"saldo_por_pais_{state.year}.csv",
            mime="text/csv",
        )


def _section301_legacy(state: FilterState, db_version: tuple[int, int]) -> None:
    _section_header(
        "MEDIDA COMERCIAL DOS ESTADOS UNIDOS",
        "Exposição potencial à Seção 301",
        "Triagem das exportações brasileiras aos EUA pela correspondência SH6 com as isenções do Anexo II.",
    )
    if not SECTION301_REFERENCE.exists():
        st.error(
            "A referência do Anexo II não foi encontrada em "
            "data/reference/section301_exemptions_sh6.csv."
        )
        return
    reference_version = database_token(SECTION301_REFERENCE)
    exposure = cached_section301(
        str(DATABASE),
        state,
        str(SECTION301_REFERENCE),
        db_version,
        reference_version,
    )
    if exposure.empty:
        st.info("Não há exportações brasileiras aos Estados Unidos no recorte selecionado.")
        return

    affected_label = "Sem correspondência - potencialmente afetado"
    exemption_label = "Correspondência com isenção no SH6"
    conditioned_label = "Correspondência condicionada no SH6"
    mixed_label = "Correspondência mista no SH6"
    total = exposure["VL_FOB"].sum()
    affected_value = exposure.loc[exposure["SITUACAO_301"] == affected_label, "VL_FOB"].sum()
    exemption_value = exposure.loc[exposure["SITUACAO_301"] != affected_label, "VL_FOB"].sum()
    conditioned_value = exposure.loc[
        exposure["SITUACAO_301"].isin([conditioned_label, mixed_label]), "VL_FOB"
    ].sum()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Exportações aos EUA", format_compact(total, "US$ "))
    c2.metric("Sem correspondência no Anexo II", format_compact(affected_value, "US$ "))
    c3.metric("Com correspondência de isenção", format_compact(exemption_value, "US$ "))
    c4.metric(
        "Parcela com correspondência",
        "—" if not total else f"{exemption_value / total:.1%}",
        help="Inclui correspondências condicionadas e não representa confirmação jurídica da isenção.",
    )

    st.warning(
        "O cruzamento por SH6 é uma aproximação. Uma correspondência indica que existe ao menos uma linha "
        "HTSUS isenta dentro do mesmo SH6; não confirma que toda NCM brasileira esteja isenta. "
        "A ausência de correspondência indica exposição potencial, não incidência definitiva."
    )

    st.markdown("### Setores mais expostos e dependência dos EUA")
    st.caption(
        "Compare o valor potencialmente afetado com a participação dos EUA nas exportações "
        "do setor. A posição considera todos os países de destino no mesmo recorte."
    )
    control_col, sort_col = st.columns([1, 1.4])
    with control_col:
        sector_level_label = st.radio(
            "Detalhamento setorial",
            ["Setor macro", "Seção ISIC"],
            horizontal=True,
            key="section301_sector_level",
        )
    with sort_col:
        sector_order = st.selectbox(
            "Ordenar setores por",
            [
                "Maior valor potencialmente afetado",
                "Maior dependência dos EUA",
                "Maior exposição sobre as exportações do setor",
            ],
            key="section301_sector_order",
        )
    sector_level = "SETOR" if sector_level_label == "Setor macro" else "ISIC"
    sector_impact = cached_section301_sectors(
        str(DATABASE),
        state,
        str(SECTION301_REFERENCE),
        sector_level,
        db_version,
        reference_version,
    )
    order_columns = {
        "Maior valor potencialmente afetado": "VALOR_POTENCIALMENTE_AFETADO",
        "Maior dependência dos EUA": "PARTICIPACAO_EUA",
        "Maior exposição sobre as exportações do setor": "EXPOSICAO_EXPORTACOES_SETOR",
    }
    sector_impact = sector_impact.sort_values(
        order_columns[sector_order], ascending=False, na_position="last"
    )
    sector_display = sector_impact.copy()
    sector_display["EUA_MAIOR_CLIENTE"] = sector_display["EUA_MAIOR_CLIENTE"].map(
        {"Sim": "★ Sim", "Não": "Não"}
    )
    sector_visible = ["SETOR"]
    if sector_level == "ISIC":
        sector_visible.extend(["CO_ISIC_SECAO", "NO_ISIC_SECAO"])
    sector_visible.extend(
        [
            "PRINCIPAL_DESTINO",
            "POSICAO_EUA",
            "EUA_MAIOR_CLIENTE",
            "EXPORTACOES_MUNDO",
            "EXPORTACOES_EUA",
            "PARTICIPACAO_EUA",
            "VALOR_POTENCIALMENTE_AFETADO",
            "PARTICIPACAO_AFETADA_NOS_EUA",
            "EXPOSICAO_EXPORTACOES_SETOR",
        ]
    )
    with st.container(border=True):
        st.dataframe(
            sector_display[sector_visible],
            use_container_width=True,
            hide_index=True,
            height=min(520, 38 + max(len(sector_display), 1) * 35),
            column_config={
                "SETOR": st.column_config.TextColumn("Setor macro", width="medium"),
                "CO_ISIC_SECAO": st.column_config.TextColumn("ISIC", width="small"),
                "NO_ISIC_SECAO": st.column_config.TextColumn("Descrição ISIC", width="large"),
                "PRINCIPAL_DESTINO": st.column_config.TextColumn(
                    "Maior cliente", width="medium"
                ),
                "POSICAO_EUA": st.column_config.NumberColumn(
                    "Posição dos EUA", format="%d",
                    help="Posição dos Estados Unidos entre os destinos das exportações do setor.",
                ),
                "EUA_MAIOR_CLIENTE": st.column_config.TextColumn(
                    "EUA é o maior cliente?", width="small"
                ),
                "EXPORTACOES_MUNDO": st.column_config.NumberColumn(
                    "Exportações mundiais (US$)", format="localized"
                ),
                "EXPORTACOES_EUA": st.column_config.NumberColumn(
                    "Exportações aos EUA (US$)", format="localized"
                ),
                "PARTICIPACAO_EUA": st.column_config.NumberColumn(
                    "Participação dos EUA", format="percent",
                    help="Exportações aos EUA divididas pelas exportações mundiais do setor.",
                ),
                "VALOR_POTENCIALMENTE_AFETADO": st.column_config.NumberColumn(
                    "Potencialmente afetado (US$)", format="localized"
                ),
                "PARTICIPACAO_AFETADA_NOS_EUA": st.column_config.NumberColumn(
                    "% das vendas aos EUA", format="percent",
                    help="Parcela das exportações aos EUA sem correspondência de isenção no SH6.",
                ),
                "EXPOSICAO_EXPORTACOES_SETOR": st.column_config.NumberColumn(
                    "Exposição do setor", format="percent",
                    help="Valor potencialmente afetado dividido pelas exportações mundiais do setor.",
                ),
            },
        )
        st.download_button(
            "Baixar análise setorial em CSV",
            data=sector_impact.to_csv(index=False, sep=";", decimal=",", encoding="utf-8-sig"),
            file_name=f"secao_301_eua_impacto_setorial_{sector_level.lower()}_{state.year}.csv",
            mime="text/csv",
        )

    with st.container(border=True):
        chart_col, donut_col = st.columns([1.7, 1])
        with chart_col:
            top_n = st.slider("Quantidade de NCMs no gráfico", 10, 30, 15, 5, key="section301_top")
            st.plotly_chart(
                section301_products_plotly(exposure, top_n),
                use_container_width=True,
                config={"displaylogo": False},
                key="section301_legacy_products_chart",
            )
        with donut_col:
            st.plotly_chart(
                section301_status_plotly(exposure),
                use_container_width=True,
                config={"displaylogo": False},
                key="section301_legacy_status_chart",
            )

    with st.container(border=True):
        status_options = [affected_label, exemption_label, conditioned_label, mixed_label]
        status_labels = {
            affected_label: "Potencialmente afetado",
            exemption_label: "Correspondência com isenção",
            conditioned_label: "Isenção condicionada",
            mixed_label: "Correspondência mista",
        }
        selected_status = st.multiselect(
            "Situação potencial",
            status_options,
            default=status_options,
            format_func=lambda value: status_labels[value],
            key="section301_status_filter",
        )
        table = exposure.loc[exposure["SITUACAO_301"].isin(selected_status)].copy()
        table["SITUACAO_301"] = table["SITUACAO_301"].map(
            {
                affected_label: "● Potencialmente afetado",
                exemption_label: "● Correspondência com isenção",
                conditioned_label: "● Isenção condicionada",
                mixed_label: "● Correspondência mista",
            }
        )
        display = table.rename(
            columns={
                "NO_NCM_POR": "PRODUTO_NCM",
                "NO_SH6_POR": "DESCRICAO_SH6",
                "VL_FOB": "VALOR_FOB",
                "KG_LIQUIDO": "PESO_LIQUIDO",
                "PARTICIPACAO_FOB_EUA": "PARTICIPACAO",
                "SITUACAO_301": "SITUACAO",
                "LIMITACOES_PT": "LIMITACOES",
                "CODIGOS_HTSUS": "HTSUS_ISENTOS_NO_SH6",
            }
        )
        visible = [
            "PRODUTO_NCM",
            "CO_NCM",
            "DESCRICAO_SH6",
            "CO_SH6",
            "VALOR_FOB",
            "PARTICIPACAO",
            "SITUACAO",
            "LIMITACOES",
            "HTSUS_ISENTOS_NO_SH6",
        ]
        st.dataframe(
            display[visible],
            use_container_width=True,
            hide_index=True,
            height=610,
            column_config={
                "PRODUTO_NCM": st.column_config.TextColumn("Produto NCM", width="large"),
                "CO_NCM": st.column_config.TextColumn("NCM", width="small"),
                "DESCRICAO_SH6": st.column_config.TextColumn("Descrição SH6", width="large"),
                "CO_SH6": st.column_config.TextColumn("SH6", width="small"),
                "VALOR_FOB": st.column_config.NumberColumn("Valor FOB aos EUA (US$)", format="localized"),
                "PARTICIPACAO": st.column_config.NumberColumn("Participação", format="percent"),
                "SITUACAO": st.column_config.TextColumn("Situação potencial", width="medium"),
                "LIMITACOES": st.column_config.TextColumn("Limitação da isenção", width="large"),
                "HTSUS_ISENTOS_NO_SH6": st.column_config.TextColumn(
                    "Linhas HTSUS isentas no mesmo SH6", width="large"
                ),
            },
        )
        st.download_button(
            "Baixar triagem da Seção 301 em CSV",
            data=table.to_csv(index=False, sep=";", decimal=",", encoding="utf-8-sig"),
            file_name=f"secao_301_eua_exposicao_sh6_{state.year}.csv",
            mime="text/csv",
        )

    with st.expander("Metodologia, vigência e limitações"):
        st.markdown(
            f"""
            - **Fonte normativa:** *Brazil 301 Final Action FRN 7-15-2026 final*, Anexo I, páginas 28–41, e Anexo II, páginas 42–138.
            - **Alíquota adicional geral:** 25%, aplicável em regra a partir de **22 de julho de 2026**. A exceção de medicamentos patenteados indicada no Anexo I passa a produzir efeitos em **31 de julho de 2026**.
            - **Base econômica:** exportações brasileiras aos Estados Unidos no ano e nos meses selecionados. Para períodos anteriores à vigência, os valores representam uma base histórica de exposição.
            - **Chave de aproximação:** seis primeiros dígitos do HTSUS e da NCM. Os desdobramentos nacionais posteriores ao SH6 não são equivalentes.
            - **Isenção condicionada:** “Ex” vale somente para o produto descrito; “Pharma”, somente para uso farmacêutico; “Aircraft”, somente para aeronaves civis e artigos abrangidos.
            - **Cobertura incompleta por SH6:** exceções vinculadas a regimes do capítulo 99, capítulo 98, bagagem, doações, materiais informativos e outras condições de entrada não são integralmente identificáveis pelos seis dígitos. Isso pode superestimar o grupo potencialmente afetado.
            - **Interpretação jurídica:** a descrição do Anexo II é informativa; a classificação HTSUS declarada e a decisão da U.S. Customs and Border Protection controlam o tratamento efetivo.
            - **Valor condicionado identificado:** {format_compact(conditioned_value, "US$ ")} dentro do recorte selecionado.
            """
        )


def _section301_sh6_summary(exposure: pd.DataFrame, affected_label: str) -> pd.DataFrame:
    work = exposure.copy()
    work["VALOR_POTENCIALMENTE_AFETADO"] = work["VL_FOB"].where(
        work["SITUACAO_301"].eq(affected_label), 0
    )
    work["KG_POTENCIALMENTE_AFETADO"] = work["KG_LIQUIDO"].where(
        work["SITUACAO_301"].eq(affected_label), 0
    )
    summary = (
        work.groupby(
            ["SETOR", "CO_SH6", "NO_SH6_POR", "SITUACAO_301"],
            as_index=False,
            dropna=False,
        )
        .agg(
            EXPORTACOES_EUA=("VL_FOB", "sum"),
            KG_EUA=("KG_LIQUIDO", "sum"),
            VALOR_POTENCIALMENTE_AFETADO=("VALOR_POTENCIALMENTE_AFETADO", "sum"),
            KG_POTENCIALMENTE_AFETADO=("KG_POTENCIALMENTE_AFETADO", "sum"),
            NCMS=("CO_NCM", "nunique"),
        )
    )
    summary["TONELADAS_EUA"] = summary.pop("KG_EUA") / 1000
    summary["TONELADAS_POTENCIALMENTE_AFETADAS"] = (
        summary.pop("KG_POTENCIALMENTE_AFETADO") / 1000
    )
    total = summary["VALOR_POTENCIALMENTE_AFETADO"].sum(min_count=1)
    summary["PARTICIPACAO_NO_AFETADO_BRASIL"] = (
        summary["VALOR_POTENCIALMENTE_AFETADO"] / total if total and total > 0 else pd.NA
    )
    return summary.sort_values("VALOR_POTENCIALMENTE_AFETADO", ascending=False)


def _section301_category_summary(exposure: pd.DataFrame, affected_label: str) -> pd.DataFrame:
    work = exposure.copy()
    work["CATEGORIA_USO"] = work["CATEGORIA_USO"].fillna("Não classificado")
    work["VALOR_POTENCIALMENTE_AFETADO"] = work["VL_FOB"].where(
        work["SITUACAO_301"].eq(affected_label), 0
    )
    work["KG_POTENCIALMENTE_AFETADO"] = work["KG_LIQUIDO"].where(
        work["SITUACAO_301"].eq(affected_label), 0
    )
    summary = (
        work.groupby("CATEGORIA_USO", as_index=False, dropna=False)
        .agg(
            EXPORTACOES_EUA=("VL_FOB", "sum"),
            KG_EUA=("KG_LIQUIDO", "sum"),
            VALOR_POTENCIALMENTE_AFETADO=("VALOR_POTENCIALMENTE_AFETADO", "sum"),
            KG_POTENCIALMENTE_AFETADO=("KG_POTENCIALMENTE_AFETADO", "sum"),
            SH6=("CO_SH6", "nunique"),
            NCMS=("CO_NCM", "nunique"),
        )
    )
    summary["TONELADAS_EUA"] = summary.pop("KG_EUA") / 1000
    summary["TONELADAS_POTENCIALMENTE_AFETADAS"] = (
        summary.pop("KG_POTENCIALMENTE_AFETADO") / 1000
    )
    summary["PARTICIPACAO_AFETADA_NOS_EUA"] = (
        summary["VALOR_POTENCIALMENTE_AFETADO"] / summary["EXPORTACOES_EUA"].replace(0, pd.NA)
    )
    total = summary["VALOR_POTENCIALMENTE_AFETADO"].sum(min_count=1)
    summary["PARTICIPACAO_NO_AFETADO_BRASIL"] = (
        summary["VALOR_POTENCIALMENTE_AFETADO"] / total if total and total > 0 else pd.NA
    )
    return summary.sort_values("VALOR_POTENCIALMENTE_AFETADO", ascending=False)


def _section301(state: FilterState, db_version: tuple[int, int]) -> None:
    _section_header(
        "Medidas comerciais dos Estados Unidos",
        "Exposição das exportações brasileiras à Seção 301",
        "Cruzamento indicativo por setor, produto, categoria de uso e unidade da Federação.",
    )
    if not SECTION301_REFERENCE.exists():
        st.error(
            "A referência do Anexo II não foi encontrada em "
            "data/reference/section301_exemptions_sh6.csv."
        )
        return

    affected_label = "Sem correspondência - potencialmente afetado"
    exemption_label = "Correspondência com isenção no SH6"
    conditioned_label = "Correspondência condicionada no SH6"
    mixed_label = "Correspondência mista no SH6"
    status_options = [affected_label, exemption_label, conditioned_label, mixed_label]
    status_labels = {
        affected_label: "Potencialmente afetado",
        exemption_label: "Correspondência com isenção",
        conditioned_label: "Isenção condicionada",
        mixed_label: "Correspondência mista",
    }
    reference_version = database_token(SECTION301_REFERENCE)
    exposure = cached_section301(
        str(DATABASE), state, str(SECTION301_REFERENCE), db_version, reference_version
    )
    if exposure.empty:
        st.info("Não há exportações brasileiras aos Estados Unidos no recorte selecionado.")
        return

    sector_macro = cached_section301_sectors(
        str(DATABASE), state, str(SECTION301_REFERENCE), "SETOR", db_version, reference_version
    )
    state_impact = cached_section301_states(
        str(DATABASE), state, str(SECTION301_REFERENCE), db_version, reference_version
    )
    sh6_summary = _section301_sh6_summary(exposure, affected_label)
    category_summary = _section301_category_summary(exposure, affected_label)
    total = exposure["VL_FOB"].sum()
    affected_mask = exposure["SITUACAO_301"].eq(affected_label)
    affected_value = exposure.loc[affected_mask, "VL_FOB"].sum()
    affected_tonnes = exposure.loc[affected_mask, "KG_LIQUIDO"].sum() / 1000
    exemption_value = total - affected_value
    conditioned_value = exposure.loc[
        exposure["SITUACAO_301"].isin([conditioned_label, mixed_label]), "VL_FOB"
    ].sum()

    st.markdown(
        """
        <div class="executive-banner">
          <strong>Nota:</strong> “potencialmente afetado” significa que não foi encontrada
          correspondência de isenção no mesmo SH6. É uma aproximação econômica e não substitui
          a análise aduaneira ou jurídica. Esta aba sempre utiliza
          exportações, independentemente do fluxo selecionado na barra lateral.
        </div>
        """,
        unsafe_allow_html=True,
    )

    tab_summary, tab_tariff, tab_sectors, tab_states, tab_categories, tab_products, tab_method = st.tabs(
        [
            "Visão geral",
            "Tarifa efetiva",
            "Setores e SH6",
            "Estados exportadores",
            "Categoria de uso",
            "Produtos NCM",
            "Metodologia",
        ]
    )

    with tab_summary:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Exportações aos EUA", format_compact(total, "US$ "))
        c2.metric("Valor potencialmente afetado", format_compact(affected_value, "US$ "))
        c3.metric("Parcela potencialmente afetada", "—" if not total else f"{affected_value / total:.1%}")
        c4.metric("Volume potencialmente afetado", format_compact(affected_tonnes, "") + " t")

        st.markdown("#### Destaques do período")
        signal1, signal2, signal3 = st.columns(3)
        top_sector = sector_macro.iloc[0] if not sector_macro.empty else None
        affected_sh6 = sh6_summary.loc[sh6_summary["VALOR_POTENCIALMENTE_AFETADO"] > 0]
        top_sh6 = affected_sh6.iloc[0] if not affected_sh6.empty else None
        valid_states = state_impact.loc[state_impact["UF"] != "Não informado"] if not state_impact.empty else state_impact
        top_state = valid_states.iloc[0] if not valid_states.empty else None
        with signal1.container(border=True):
            st.caption("Setor com maior valor exposto")
            st.markdown(f"**{top_sector['SETOR'] if top_sector is not None else 'Não disponível'}**")
            st.write(
                format_compact(top_sector["VALOR_POTENCIALMENTE_AFETADO"], "US$ ")
                if top_sector is not None else "—"
            )
            if top_sector is not None:
                st.caption(f"EUA representam {top_sector['PARTICIPACAO_EUA']:.1%} das vendas externas do setor.")
        with signal2.container(border=True):
            st.caption("SH6 com maior valor exposto")
            st.markdown(f"**{top_sh6['NO_SH6_POR'] if top_sh6 is not None else 'Não disponível'}**")
            st.write(
                format_compact(top_sh6["VALOR_POTENCIALMENTE_AFETADO"], "US$ ")
                if top_sh6 is not None else "—"
            )
            if top_sh6 is not None:
                st.caption(f"SH6 {top_sh6['CO_SH6']} · {top_sh6['TONELADAS_POTENCIALMENTE_AFETADAS']:,.0f} t")
        with signal3.container(border=True):
            st.caption("UF com maior valor exposto")
            uf_name = UF_NAMES.get(top_state["UF"], top_state["UF"]) if top_state is not None else "Não disponível"
            st.markdown(f"**{uf_name}**")
            st.write(
                format_compact(top_state["VALOR_POTENCIALMENTE_AFETADO"], "US$ ")
                if top_state is not None else "—"
            )
            if top_state is not None:
                st.caption(f"{top_state['PARTICIPACAO_NO_AFETADO_BRASIL']:.1%} do valor nacional potencialmente afetado.")

        with st.container(border=True):
            st.plotly_chart(
                section301_impact_ranking_plotly(
                    affected_sh6.assign(
                        ROTULO=affected_sh6["NO_SH6_POR"].str.slice(0, 55)
                        + " · " + affected_sh6["CO_SH6"].astype(str)
                    ),
                    "ROTULO",
                    "SH6 com maior valor potencialmente afetado",
                    top_n=10,
                ),
                use_container_width=True,
                config={"displaylogo": False},
                key="section301_summary_sh6_chart",
            )
        with st.container(border=True):
            st.plotly_chart(
                section301_status_plotly(exposure),
                use_container_width=True,
                config={"displaylogo": False},
                key="section301_summary_status_chart",
            )

    with tab_tariff:
        if not US_TARIFF_REFERENCE.exists():
            st.warning(
                "A série tarifária não foi encontrada em "
                "data/reference/us_effective_tariff_brazil.csv."
            )
        else:
            tariff_version = database_token(US_TARIFF_REFERENCE)
            tariff = cached_us_effective_tariff(str(US_TARIFF_REFERENCE), tariff_version)
            if tariff.empty:
                st.info("A série tarifária está vazia.")
            else:
                latest = tariff.iloc[-1]
                previous = tariff.iloc[-2] if len(tariff) > 1 else None
                prior_year_date = latest["DATA"] - pd.DateOffset(years=1)
                prior_year_rows = tariff.loc[tariff["DATA"] == prior_year_date]
                prior_year = prior_year_rows.iloc[-1] if not prior_year_rows.empty else None
                peak = tariff.loc[tariff["TARIFA_EFETIVA_PCT"].idxmax()]
                latest_label = f"{MONTH_NAMES[int(latest['DATA'].month)]}/{int(latest['DATA'].year)}"
                peak_label = f"{MONTH_NAMES[int(peak['DATA'].month)]}/{int(peak['DATA'].year)}"
                monthly_change = (
                    latest["TARIFA_EFETIVA_PCT"] - previous["TARIFA_EFETIVA_PCT"]
                    if previous is not None else pd.NA
                )
                annual_change = (
                    latest["TARIFA_EFETIVA_PCT"] - prior_year["TARIFA_EFETIVA_PCT"]
                    if prior_year is not None else pd.NA
                )

                st.caption(
                    "Direitos aduaneiros cobrados pelos Estados Unidos como percentual do valor "
                    f"das importações para consumo. Último mês disponível: {latest_label}."
                )
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Tarifa efetiva", f"{latest['TARIFA_EFETIVA_PCT']:.2f}%".replace(".", ","))
                c2.metric(
                    "Variação mensal",
                    "—" if pd.isna(monthly_change) else f"{monthly_change:+.2f} p.p.".replace(".", ","),
                )
                c3.metric(
                    "Variação em 12 meses",
                    "—" if pd.isna(annual_change) else f"{annual_change:+.2f} p.p.".replace(".", ","),
                )
                c4.metric(
                    "Pico da série",
                    f"{peak['TARIFA_EFETIVA_PCT']:.2f}%".replace(".", ","),
                    help=f"Maior valor mensal, observado em {peak_label}.",
                )

                with st.container(border=True):
                    st.plotly_chart(
                        us_effective_tariff_plotly(tariff),
                        use_container_width=True,
                        config={"displaylogo": False, "scrollZoom": False},
                        key="us_effective_tariff_chart",
                    )

                with st.expander("Consultar os dados mensais e a taxa sobre a base tributável"):
                    table = tariff.copy()
                    table["MES"] = table["DATA"].map(
                        lambda value: f"{MONTH_NAMES[int(value.month)]}/{int(value.year)}"
                    )
                    st.dataframe(
                        table[[
                            "MES", "IMPORTACOES_CONSUMO_USD", "DIREITOS_ADUANEIROS_USD",
                            "BASE_TRIBUTAVEL_USD", "TARIFA_EFETIVA_PCT",
                            "TARIFA_BASE_TRIBUTAVEL_PCT",
                        ]],
                        use_container_width=True,
                        hide_index=True,
                        height=450,
                        column_config={
                            "MES": "Mês",
                            "IMPORTACOES_CONSUMO_USD": st.column_config.NumberColumn(
                                "Importações para consumo (US$)", format="localized"
                            ),
                            "DIREITOS_ADUANEIROS_USD": st.column_config.NumberColumn(
                                "Direitos aduaneiros (US$)", format="localized"
                            ),
                            "BASE_TRIBUTAVEL_USD": st.column_config.NumberColumn(
                                "Base tributável (US$)", format="localized"
                            ),
                            "TARIFA_EFETIVA_PCT": st.column_config.NumberColumn(
                                "Tarifa efetiva", format="%.2f%%"
                            ),
                            "TARIFA_BASE_TRIBUTAVEL_PCT": st.column_config.NumberColumn(
                                "Taxa sobre a base tributável", format="%.2f%%"
                            ),
                        },
                    )
                    st.download_button(
                        "Baixar série tarifária em CSV",
                        tariff.to_csv(index=False, sep=";", decimal=",", encoding="utf-8-sig"),
                        file_name="tarifa_efetiva_eua_brasil.csv",
                        mime="text/csv",
                    )

                st.caption(
                    "Fonte: U.S. Census Bureau, International Trade API. "
                    "Tarifa efetiva = direitos aduaneiros calculados ÷ importações para consumo × 100. "
                    "A taxa sobre a base tributável usa somente o valor das mercadorias sujeitas a direitos."
                )

    with tab_sectors:
        level_col, order_col = st.columns([1, 1.4])
        sector_level_label = level_col.radio(
            "Detalhamento", ["Setor macro", "Seção ISIC"], horizontal=True,
            key="section301_sector_level_v2",
        )
        sector_order = order_col.selectbox(
            "Priorizar por",
            ["Valor potencialmente afetado", "Dependência dos EUA", "Exposição do setor"],
            key="section301_sector_order_v2",
        )
        sector_level = "SETOR" if sector_level_label == "Setor macro" else "ISIC"
        sectors = (
            sector_macro if sector_level == "SETOR" else cached_section301_sectors(
                str(DATABASE), state, str(SECTION301_REFERENCE), "ISIC", db_version, reference_version
            )
        )
        sector_sort = {
            "Valor potencialmente afetado": "VALOR_POTENCIALMENTE_AFETADO",
            "Dependência dos EUA": "PARTICIPACAO_EUA",
            "Exposição do setor": "EXPOSICAO_EXPORTACOES_SETOR",
        }[sector_order]
        sectors = sectors.sort_values(sector_sort, ascending=False, na_position="last")
        sector_columns = ["SETOR"] if sector_level == "SETOR" else ["CO_ISIC_SECAO", "NO_ISIC_SECAO"]
        sector_columns += [
            "PRINCIPAL_DESTINO", "POSICAO_EUA", "EUA_MAIOR_CLIENTE",
            "EXPORTACOES_MUNDO", "EXPORTACOES_EUA", "TONELADAS_EUA",
            "PARTICIPACAO_EUA", "VALOR_POTENCIALMENTE_AFETADO",
            "TONELADAS_POTENCIALMENTE_AFETADAS", "PARTICIPACAO_AFETADA_NOS_EUA",
            "EXPOSICAO_EXPORTACOES_SETOR",
        ]
        st.dataframe(
            sectors[sector_columns], use_container_width=True, hide_index=True, height=430,
            column_config={
                "SETOR": st.column_config.TextColumn("Setor", width="medium"),
                "CO_ISIC_SECAO": st.column_config.TextColumn("ISIC", width="small"),
                "NO_ISIC_SECAO": st.column_config.TextColumn("Descrição ISIC", width="large"),
                "PRINCIPAL_DESTINO": st.column_config.TextColumn("Maior cliente", width="medium"),
                "POSICAO_EUA": st.column_config.NumberColumn("Posição dos EUA", format="%d"),
                "EUA_MAIOR_CLIENTE": st.column_config.TextColumn("EUA é o maior cliente?"),
                "EXPORTACOES_MUNDO": st.column_config.NumberColumn("Exportações mundiais (US$)", format="localized"),
                "EXPORTACOES_EUA": st.column_config.NumberColumn("Exportações aos EUA (US$)", format="localized"),
                "TONELADAS_EUA": st.column_config.NumberColumn("Volume aos EUA (t)", format="localized"),
                "PARTICIPACAO_EUA": st.column_config.NumberColumn("Participação dos EUA", format="percent"),
                "VALOR_POTENCIALMENTE_AFETADO": st.column_config.NumberColumn("Potencialmente afetado (US$)", format="localized"),
                "TONELADAS_POTENCIALMENTE_AFETADAS": st.column_config.NumberColumn("Volume potencial (t)", format="localized"),
                "PARTICIPACAO_AFETADA_NOS_EUA": st.column_config.NumberColumn("% das vendas aos EUA", format="percent"),
                "EXPOSICAO_EXPORTACOES_SETOR": st.column_config.NumberColumn("Exposição do setor", format="percent"),
            },
        )

        st.markdown("#### SH6 mais afetados dentro de cada setor")
        selected_sector = st.selectbox(
            "Escolha o setor", ["Todos"] + sorted(sh6_summary["SETOR"].dropna().unique().tolist()),
            key="section301_sh6_sector",
        )
        only_affected = st.toggle("Mostrar somente SH6 potencialmente afetados", True, key="section301_sh6_only")
        sh6_table = sh6_summary.copy()
        if selected_sector != "Todos":
            sh6_table = sh6_table.loc[sh6_table["SETOR"] == selected_sector]
        if only_affected:
            sh6_table = sh6_table.loc[sh6_table["VALOR_POTENCIALMENTE_AFETADO"] > 0]
        if sh6_table.empty:
            st.info("Não há SH6 para os critérios selecionados.")
        else:
            sh6_table = sh6_table.copy()
            sh6_table["ROTULO"] = sh6_table["NO_SH6_POR"].str.slice(0, 58) + " · " + sh6_table["CO_SH6"].astype(str)
            st.plotly_chart(
                section301_impact_ranking_plotly(
                    sh6_table, "ROTULO", f"SH6 prioritários — {selected_sector}", top_n=15
                ),
                use_container_width=True,
                config={"displaylogo": False},
                key="section301_sector_sh6_chart",
            )
            st.dataframe(
                sh6_table[[
                    "SETOR", "CO_SH6", "NO_SH6_POR", "NCMS", "EXPORTACOES_EUA",
                    "TONELADAS_EUA", "VALOR_POTENCIALMENTE_AFETADO",
                    "TONELADAS_POTENCIALMENTE_AFETADAS", "PARTICIPACAO_NO_AFETADO_BRASIL",
                    "SITUACAO_301",
                ]],
                use_container_width=True, hide_index=True, height=520,
                column_config={
                    "SETOR": "Setor", "CO_SH6": "SH6",
                    "NO_SH6_POR": st.column_config.TextColumn("Descrição SH6", width="large"),
                    "NCMS": "NCMs", "EXPORTACOES_EUA": st.column_config.NumberColumn("Exportações aos EUA (US$)", format="localized"),
                    "TONELADAS_EUA": st.column_config.NumberColumn("Volume aos EUA (t)", format="localized"),
                    "VALOR_POTENCIALMENTE_AFETADO": st.column_config.NumberColumn("Potencialmente afetado (US$)", format="localized"),
                    "TONELADAS_POTENCIALMENTE_AFETADAS": st.column_config.NumberColumn("Volume potencial (t)", format="localized"),
                    "PARTICIPACAO_NO_AFETADO_BRASIL": st.column_config.NumberColumn("Participação no valor afetado", format="percent"),
                    "SITUACAO_301": st.column_config.TextColumn("Situação", width="medium"),
                },
            )
            st.download_button(
                "Baixar SH6 do setor em CSV", sh6_table.to_csv(index=False, sep=";", decimal=",", encoding="utf-8-sig"),
                file_name=f"secao301_sh6_{state.year}.csv", mime="text/csv",
            )

    with tab_states:
        if state_impact.empty or state_impact["UF"].eq("Não informado").all():
            st.warning(
                "A base web ativa não possui UF exportadora. Gere novamente o banco com "
                "`.\\.venv\\Scripts\\python.exe build_web_database.py --force` e reinicie o site."
            )
        else:
            states = state_impact.copy()
            states["UF_LABEL"] = states["UF"].map(
                lambda code: f"{UF_NAMES.get(code, code)} ({code})" if code in UF_NAMES else code
            )
            states["POSICAO_IMPACTO"] = (
                states["VALOR_POTENCIALMENTE_AFETADO"]
                .rank(method="min", ascending=False)
                .astype("Int64")
            )
            states["FAIXA_IMPACTO"] = states.apply(
                lambda row: (
                    "Sem exposição identificada"
                    if row["VALOR_POTENCIALMENTE_AFETADO"] <= 0
                    else "Maior exposição potencial"
                    if row["POSICAO_IMPACTO"] <= 5
                    else "Exposição relevante"
                    if row["POSICAO_IMPACTO"] <= 10
                    else "Menor exposição relativa"
                ),
                axis=1,
            )
            identified_states = states.loc[states["UF"] != "Não informado"].copy()
            national_exports = cached_summary(
                str(DATABASE), replace(state, flow="EXP"), db_version
            )["VL_FOB"]
            exports_to_us = states["EXPORTACOES_EUA"].sum()
            affected_states_value = states["VALOR_POTENCIALMENTE_AFETADO"].sum()
            us_share = exports_to_us / national_exports if national_exports else pd.NA

            st.caption(
                "A comparação usa o valor FOB exportado no ano, meses e produtos selecionados. "
                "O resultado representa exposição potencial, não uma perda já observada após a tarifa."
            )
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Exportações brasileiras no recorte", format_compact(national_exports, "US$ "))
            c2.metric("Exportações aos EUA", format_compact(exports_to_us, "US$ "))
            c3.metric(
                "Participação dos EUA",
                "—" if pd.isna(us_share) else f"{us_share:.1%}".replace(".", ","),
            )
            c4.metric(
                "Valor potencialmente afetado",
                format_compact(affected_states_value, "US$ "),
            )

            top_states = (
                identified_states.loc[identified_states["VALOR_POTENCIALMENTE_AFETADO"] > 0]
                .nlargest(3, "VALOR_POTENCIALMENTE_AFETADO")
            )
            st.markdown("#### UFs com maior exposição potencial")
            if top_states.empty:
                st.info("Nenhuma UF apresentou valor potencialmente afetado no recorte.")
            else:
                highlights = st.columns(len(top_states))
                for column, (_, row) in zip(highlights, top_states.iterrows(), strict=False):
                    with column.container(border=True):
                        st.caption(f"{int(row['POSICAO_IMPACTO'])}ª posição no valor exposto")
                        st.markdown(f"**{row['UF_LABEL']}**")
                        st.write(format_compact(row["VALOR_POTENCIALMENTE_AFETADO"], "US$ "))
                        st.caption(
                            f"EUA: {row['PARTICIPACAO_EUA']:.1%} das exportações da UF · "
                            f"parcela potencial: {row['PARTICIPACAO_AFETADA_NOS_EUA']:.1%} "
                            "das vendas aos EUA."
                        )

            values_tab, dependency_tab = st.tabs(
                ["Comparação dos valores", "Dependência e alcance potencial"]
            )
            with values_tab:
                st.plotly_chart(
                    section301_state_trade_plotly(identified_states, top_n=15),
                    use_container_width=True,
                    config={"displaylogo": False},
                    key="section301_states_trade_chart",
                )
                st.caption(
                    "As barras são sobrepostas: o valor vermelho é parte das exportações aos EUA, "
                    "e as exportações aos EUA são parte das exportações totais da UF."
                )
            with dependency_tab:
                st.plotly_chart(
                    section301_state_dependency_plotly(identified_states),
                    use_container_width=True,
                    config={"displaylogo": False},
                    key="section301_states_dependency_chart",
                )
                st.caption(
                    "O tamanho da bolha representa o valor potencialmente afetado. Em vermelho, "
                    "UFs nas quais os Estados Unidos são o maior destino das exportações."
                )

            st.markdown("#### Produtos com maior exposição por UF")
            state_labels = dict(zip(
                identified_states["UF"], identified_states["UF_LABEL"], strict=False
            ))
            state_options = (
                identified_states.sort_values(
                    "VALOR_POTENCIALMENTE_AFETADO", ascending=False
                )["UF"].tolist()
            )
            product_control, level_control, amount_control = st.columns([1.4, 1, 1])
            selected_uf = product_control.selectbox(
                "Unidade da Federação",
                state_options,
                format_func=lambda code: state_labels.get(code, code),
                key="section301_state_product_uf",
            )
            product_level = level_control.radio(
                "Detalhamento",
                ["SH6", "NCM"],
                horizontal=True,
                key="section301_state_product_level",
            )
            state_product_top = amount_control.selectbox(
                "Itens no gráfico",
                [10, 15, 20, 30],
                index=1,
                key="section301_state_product_top",
            )
            state_products = cached_section301_state_products(
                str(DATABASE), state, str(SECTION301_REFERENCE), selected_uf,
                product_level, db_version, reference_version,
            )
            if state_products.empty:
                st.info("Não há produtos exportados aos EUA para a UF e o recorte selecionados.")
            else:
                state_row = identified_states.loc[identified_states["UF"] == selected_uf].iloc[0]
                affected_products = state_products.loc[
                    state_products["VALOR_POTENCIALMENTE_AFETADO"] > 0
                ].copy()
                p1, p2, p3, p4 = st.columns(4)
                p1.metric(
                    f"Exportações de {selected_uf} aos EUA",
                    format_compact(state_row["EXPORTACOES_EUA"], "US$ "),
                )
                p2.metric(
                    "Valor potencialmente afetado",
                    format_compact(state_row["VALOR_POTENCIALMENTE_AFETADO"], "US$ "),
                )
                p3.metric(
                    "Parcela das vendas aos EUA",
                    f"{state_row['PARTICIPACAO_AFETADA_NOS_EUA']:.1%}".replace(".", ","),
                )
                p4.metric(
                    f"{product_level} potencialmente afetados",
                    f"{len(affected_products):,}".replace(",", "."),
                )

                if affected_products.empty:
                    st.info(
                        f"Não foram encontrados {product_level} sem correspondência de isenção "
                        f"para {state_labels.get(selected_uf, selected_uf)}."
                    )
                else:
                    affected_products["ROTULO"] = (
                        affected_products["DESCRICAO"].astype(str).str.slice(0, 58)
                        + " · " + affected_products["CODIGO"].astype(str)
                    )
                    chart_products = affected_products.rename(
                        columns={
                            "PARTICIPACAO_NO_AFETADO_UF": "PARTICIPACAO_NO_AFETADO_BRASIL"
                        }
                    )
                    st.plotly_chart(
                        section301_impact_ranking_plotly(
                            chart_products,
                            "ROTULO",
                            f"{product_level} com maior valor potencialmente afetado — "
                            f"{state_labels.get(selected_uf, selected_uf)}",
                            top_n=state_product_top,
                            color="#9C3D2E",
                        ),
                        use_container_width=True,
                        config={"displaylogo": False},
                        key="section301_state_products_chart",
                    )

                show_only_affected = st.toggle(
                    "Mostrar somente produtos potencialmente afetados",
                    True,
                    key="section301_state_product_only_affected",
                )
                product_table = affected_products if show_only_affected else state_products.copy()
                product_table["SITUACAO"] = product_table["SITUACAO_301"].map(status_labels)
                table_columns = [
                    "SETOR", "CATEGORIA_USO", "CODIGO", "DESCRICAO",
                ]
                if product_level == "SH6":
                    table_columns.append("NCMS")
                else:
                    table_columns.extend(["CO_SH6", "NO_SH6_POR"])
                table_columns += [
                    "VL_FOB", "TONELADAS_EUA", "VALOR_POTENCIALMENTE_AFETADO",
                    "TONELADAS_POTENCIALMENTE_AFETADAS", "PARTICIPACAO_FOB_EUA",
                    "PARTICIPACAO_NO_AFETADO_UF", "SITUACAO", "LIMITACOES_PT",
                ]
                st.dataframe(
                    product_table[table_columns],
                    use_container_width=True,
                    hide_index=True,
                    height=560,
                    column_config={
                        "SETOR": st.column_config.TextColumn("Setor", width="medium"),
                        "CATEGORIA_USO": st.column_config.TextColumn("Categoria de uso", width="medium"),
                        "CODIGO": product_level,
                        "DESCRICAO": st.column_config.TextColumn(
                            f"Descrição {product_level}", width="large"
                        ),
                        "NCMS": "Quantidade de NCM",
                        "CO_SH6": "SH6",
                        "NO_SH6_POR": st.column_config.TextColumn("Descrição SH6", width="large"),
                        "VL_FOB": st.column_config.NumberColumn(
                            "Exportações aos EUA (US$)", format="localized"
                        ),
                        "TONELADAS_EUA": st.column_config.NumberColumn(
                            "Volume aos EUA (t)", format="localized"
                        ),
                        "VALOR_POTENCIALMENTE_AFETADO": st.column_config.NumberColumn(
                            "Potencialmente afetado (US$)", format="localized"
                        ),
                        "TONELADAS_POTENCIALMENTE_AFETADAS": st.column_config.NumberColumn(
                            "Volume potencial (t)", format="localized"
                        ),
                        "PARTICIPACAO_FOB_EUA": st.column_config.NumberColumn(
                            "Participação nas vendas da UF aos EUA", format="percent"
                        ),
                        "PARTICIPACAO_NO_AFETADO_UF": st.column_config.NumberColumn(
                            "Participação no valor afetado da UF", format="percent"
                        ),
                        "SITUACAO": st.column_config.TextColumn(
                            "Situação potencial", width="medium"
                        ),
                        "LIMITACOES_PT": st.column_config.TextColumn(
                            "Limitação da isenção", width="large"
                        ),
                    },
                )
                st.download_button(
                    f"Baixar produtos de {selected_uf} em CSV",
                    product_table.to_csv(index=False, sep=";", decimal=",", encoding="utf-8-sig"),
                    file_name=f"secao301_{selected_uf.lower()}_{product_level.lower()}_{state.year}.csv",
                    mime="text/csv",
                )

            st.markdown("#### Tabela comparativa por unidade da Federação")
            state_order = st.selectbox(
                "Ordenar UFs por",
                [
                    "Valor potencialmente afetado", "Exportações totais", "Exportações aos EUA",
                    "Participação dos EUA", "Exposição da UF",
                ],
                key="section301_state_order",
            )
            state_sort = {
                "Valor potencialmente afetado": "VALOR_POTENCIALMENTE_AFETADO",
                "Exportações totais": "EXPORTACOES_MUNDO",
                "Exportações aos EUA": "EXPORTACOES_EUA",
                "Participação dos EUA": "PARTICIPACAO_EUA",
                "Exposição da UF": "EXPOSICAO_EXPORTACOES_UF",
            }[state_order]
            states = states.sort_values(state_sort, ascending=False, na_position="last")
            st.dataframe(
                states[[
                    "POSICAO_IMPACTO", "FAIXA_IMPACTO", "UF_LABEL", "PRINCIPAL_DESTINO",
                    "POSICAO_EUA", "EUA_MAIOR_CLIENTE",
                    "EXPORTACOES_MUNDO", "EXPORTACOES_EUA", "TONELADAS_EUA",
                    "PARTICIPACAO_EUA", "VALOR_POTENCIALMENTE_AFETADO",
                    "TONELADAS_POTENCIALMENTE_AFETADAS", "PARTICIPACAO_AFETADA_NOS_EUA",
                    "PARTICIPACAO_NO_AFETADO_BRASIL", "EXPOSICAO_EXPORTACOES_UF",
                ]],
                use_container_width=True, hide_index=True, height=590,
                column_config={
                    "POSICAO_IMPACTO": st.column_config.NumberColumn("Posição no impacto", format="%d"),
                    "FAIXA_IMPACTO": st.column_config.TextColumn(
                        "Nível de exposição potencial", width="medium"
                    ),
                    "UF_LABEL": st.column_config.TextColumn("UF exportadora", width="medium"),
                    "PRINCIPAL_DESTINO": st.column_config.TextColumn("Maior cliente", width="medium"),
                    "POSICAO_EUA": st.column_config.NumberColumn("Posição dos EUA", format="%d"),
                    "EUA_MAIOR_CLIENTE": "EUA é o maior cliente?",
                    "EXPORTACOES_MUNDO": st.column_config.NumberColumn("Exportações mundiais (US$)", format="localized"),
                    "EXPORTACOES_EUA": st.column_config.NumberColumn("Exportações aos EUA (US$)", format="localized"),
                    "TONELADAS_EUA": st.column_config.NumberColumn("Volume aos EUA (t)", format="localized"),
                    "PARTICIPACAO_EUA": st.column_config.NumberColumn("Participação dos EUA", format="percent"),
                    "VALOR_POTENCIALMENTE_AFETADO": st.column_config.NumberColumn("Potencialmente afetado (US$)", format="localized"),
                    "TONELADAS_POTENCIALMENTE_AFETADAS": st.column_config.NumberColumn("Volume potencial (t)", format="localized"),
                    "PARTICIPACAO_AFETADA_NOS_EUA": st.column_config.NumberColumn("% das vendas aos EUA", format="percent"),
                    "PARTICIPACAO_NO_AFETADO_BRASIL": st.column_config.NumberColumn("Participação no afetado Brasil", format="percent"),
                    "EXPOSICAO_EXPORTACOES_UF": st.column_config.NumberColumn("Exposição da UF", format="percent"),
                },
            )
            st.download_button(
                "Baixar análise por UF em CSV", states.to_csv(index=False, sep=";", decimal=",", encoding="utf-8-sig"),
                file_name=f"secao301_estados_{state.year}.csv", mime="text/csv",
            )

    with tab_categories:
        st.caption(
            "A categoria de uso segue a Grande Categoria Econômica (CGCE): bens de capital, "
            "bens intermediários, bens de consumo e combustíveis e lubrificantes."
        )
        category_chart = category_summary.copy()
        st.plotly_chart(
            section301_impact_ranking_plotly(
                category_chart, "CATEGORIA_USO", "Exposição potencial por categoria de uso",
                top_n=len(category_chart), color="#8A5A20",
            ),
            use_container_width=True,
            config={"displaylogo": False},
            key="section301_category_chart",
        )
        st.dataframe(
            category_summary[[
                "CATEGORIA_USO", "SH6", "NCMS", "EXPORTACOES_EUA", "TONELADAS_EUA",
                "VALOR_POTENCIALMENTE_AFETADO", "TONELADAS_POTENCIALMENTE_AFETADAS",
                "PARTICIPACAO_AFETADA_NOS_EUA", "PARTICIPACAO_NO_AFETADO_BRASIL",
            ]],
            use_container_width=True, hide_index=True,
            column_config={
                "CATEGORIA_USO": st.column_config.TextColumn("Categoria de uso", width="large"),
                "SH6": "SH6", "NCMS": "NCMs",
                "EXPORTACOES_EUA": st.column_config.NumberColumn("Exportações aos EUA (US$)", format="localized"),
                "TONELADAS_EUA": st.column_config.NumberColumn("Volume aos EUA (t)", format="localized"),
                "VALOR_POTENCIALMENTE_AFETADO": st.column_config.NumberColumn("Potencialmente afetado (US$)", format="localized"),
                "TONELADAS_POTENCIALMENTE_AFETADAS": st.column_config.NumberColumn("Volume potencial (t)", format="localized"),
                "PARTICIPACAO_AFETADA_NOS_EUA": st.column_config.NumberColumn("% das vendas aos EUA", format="percent"),
                "PARTICIPACAO_NO_AFETADO_BRASIL": st.column_config.NumberColumn("Participação no afetado Brasil", format="percent"),
            },
        )
        selected_category = st.selectbox(
            "Detalhar produtos da categoria",
            category_summary["CATEGORIA_USO"].tolist(), key="section301_category_detail",
        )
        category_products = exposure.loc[exposure["CATEGORIA_USO"] == selected_category].copy()
        category_only_affected = st.toggle(
            "Mostrar somente produtos potencialmente afetados", True, key="section301_category_only"
        )
        if category_only_affected:
            category_products = category_products.loc[category_products["SITUACAO_301"] == affected_label]
        category_products["TONELADAS"] = category_products["KG_LIQUIDO"] / 1000
        category_products["VALOR_POTENCIALMENTE_AFETADO"] = category_products["VL_FOB"].where(
            category_products["SITUACAO_301"].eq(affected_label), 0
        )
        st.dataframe(
            category_products[[
                "SETOR", "CO_NCM", "NO_NCM_POR", "CO_SH6", "NO_SH6_POR",
                "VL_FOB", "TONELADAS", "VALOR_POTENCIALMENTE_AFETADO", "SITUACAO_301",
            ]].sort_values("VALOR_POTENCIALMENTE_AFETADO", ascending=False),
            use_container_width=True, hide_index=True, height=520,
            column_config={
                "SETOR": "Setor", "CO_NCM": "NCM",
                "NO_NCM_POR": st.column_config.TextColumn("Produto NCM", width="large"),
                "CO_SH6": "SH6", "NO_SH6_POR": st.column_config.TextColumn("Descrição SH6", width="large"),
                "VL_FOB": st.column_config.NumberColumn("Exportações aos EUA (US$)", format="localized"),
                "TONELADAS": st.column_config.NumberColumn("Volume (t)", format="localized"),
                "VALOR_POTENCIALMENTE_AFETADO": st.column_config.NumberColumn("Potencialmente afetado (US$)", format="localized"),
                "SITUACAO_301": st.column_config.TextColumn("Situação", width="medium"),
            },
        )

    with tab_products:
        selected_status = st.multiselect(
            "Situação potencial", status_options, default=status_options,
            format_func=lambda value: status_labels[value], key="section301_status_filter_v2",
        )
        products = exposure.loc[exposure["SITUACAO_301"].isin(selected_status)].copy()
        products["TONELADAS"] = products["KG_LIQUIDO"] / 1000
        products["SITUACAO"] = products["SITUACAO_301"].map(status_labels)
        st.dataframe(
            products[[
                "SETOR", "CATEGORIA_USO", "NO_NCM_POR", "CO_NCM", "NO_SH6_POR", "CO_SH6",
                "VL_FOB", "TONELADAS", "PARTICIPACAO_FOB_EUA", "SITUACAO",
                "LIMITACOES_PT", "CODIGOS_HTSUS",
            ]],
            use_container_width=True, hide_index=True, height=620,
            column_config={
                "SETOR": "Setor", "CATEGORIA_USO": "Categoria de uso",
                "NO_NCM_POR": st.column_config.TextColumn("Produto NCM", width="large"),
                "CO_NCM": "NCM", "NO_SH6_POR": st.column_config.TextColumn("Descrição SH6", width="large"),
                "CO_SH6": "SH6", "VL_FOB": st.column_config.NumberColumn("Valor FOB aos EUA (US$)", format="localized"),
                "TONELADAS": st.column_config.NumberColumn("Volume (t)", format="localized"),
                "PARTICIPACAO_FOB_EUA": st.column_config.NumberColumn("Participação", format="percent"),
                "SITUACAO": st.column_config.TextColumn("Situação potencial", width="medium"),
                "LIMITACOES_PT": st.column_config.TextColumn("Limitação da isenção", width="large"),
                "CODIGOS_HTSUS": st.column_config.TextColumn("Linhas HTSUS no mesmo SH6", width="large"),
            },
        )
        st.download_button(
            "Baixar triagem completa em CSV",
            products.to_csv(index=False, sep=";", decimal=",", encoding="utf-8-sig"),
            file_name=f"secao301_produtos_{state.year}.csv", mime="text/csv",
        )

    with tab_method:
        st.markdown(
            f"""
            ### Escopo e cautelas de interpretação

            - **Fonte normativa:** *Brazil 301 Final Action FRN 7-15-2026 final*, Anexos I e II.
            - **Alíquota adicional geral:** 25%, aplicável em regra a partir de **22 de julho de 2026**.
            - **Base econômica:** exportações brasileiras aos EUA no ano e meses selecionados.
            - **Chave de aproximação:** seis primeiros dígitos do HTSUS e da NCM.
            - **Potencialmente afetado:** SH6 sem correspondência localizada no Anexo II.
            - **Correspondência condicionada:** pode valer apenas para “Ex”, uso farmacêutico ou aeronaves civis.
            - **UF exportadora:** `SG_UF_NCM` informada nos dados SECEX; não representa necessariamente o local de produção.
            - **Categoria de uso:** classificação CGCE associada ao NCM.
            - **Interpretação jurídica:** a classificação HTSUS declarada e a decisão da autoridade aduaneira dos EUA controlam o tratamento efetivo.

            Valor com correspondência de isenção no recorte: **{format_compact(exemption_value, 'US$ ')}**.  
            Valor condicionado ou misto identificado: **{format_compact(conditioned_value, 'US$ ')}**.
            """
        )


def _quality(db_version: tuple[int, int]) -> None:
    _section_header(
        "Dados e atualização",
        "Qualidade e rastreabilidade da carga",
        "Acompanhe cobertura das dimensões, calendário e arquivos incorporados ao banco analítico.",
    )
    report, files = cached_quality(str(DATABASE), db_version)
    st.dataframe(
        report,
        use_container_width=True,
        hide_index=True,
        column_config={
            "VALOR": st.column_config.NumberColumn("Registros/arquivos", format="%.0f"),
            "PERCENTUAL": st.column_config.NumberColumn("% da fato", format="percent"),
        },
    )
    st.markdown("**Arquivos processados**")
    if not files.empty:
        files = files.copy()
        files["ARQUIVO"] = files["ARQUIVO"].map(lambda value: Path(value).name)
    st.dataframe(files, use_container_width=True, hide_index=True)


def main() -> None:
    _inject_css()
    if not DATABASE.exists():
        st.warning("O banco processado ainda não existe.")
        st.code("python run_etl.py\nstreamlit run app.py", language="bash")
        st.stop()
    db_version = database_token(DATABASE)
    state = _filters(db_version)
    st.sidebar.caption(
        f"Base ativa: {'web agregada' if DATABASE.name == 'comex_web.duckdb' else DATABASE.name}"
    )
    _hero(state)
    tab_overview, tab_hierarchy, tab_countries, tab_balance, tab_section301, tab_quality = st.tabs(
        [
            "Visão mensal",
            "Classificação",
            "Países",
            "Saldo por país",
            "Seção 301 EUA",
            "Qualidade",
        ]
    )
    with tab_overview:
        _overview(state, db_version)
    with tab_hierarchy:
        _hierarchy(state, db_version)
    with tab_countries:
        _countries(state, db_version)
    with tab_balance:
        _trade_balance(state, db_version)
    with tab_section301:
        _section301(state, db_version)
    with tab_quality:
        _quality(db_version)
    st.markdown(
        '<div class="footer-note">Dados: SECEX/Comex Stat · Elaboração própria · Valores em dólares FOB</div>',
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
