from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pandas as pd
import streamlit as st

from src.charts import (
    balance_status_plotly,
    country_ranking_plotly,
    monthly_matplotlib,
    monthly_plotly,
    prepare_monthly_profile,
    trade_balance_plotly,
)
from src.queries import (
    LEVELS,
    FilterState,
    available_months,
    available_years,
    country_ranking,
    database_token,
    filter_options,
    hierarchy_table,
    monthly_history,
    quality_report,
    summary_metrics,
    trade_balance_by_country,
)
from src.utils import MONTH_NAMES, format_compact


PROJECT_DIR = Path(__file__).resolve().parent
DATABASE = PROJECT_DIR / "data" / "processed" / "comex.duckdb"


st.set_page_config(
    page_title="Painel SECEX",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded",
)


def _inject_css() -> None:
    st.markdown(
        """
        <style>
        :root {
            --brand: #175C3A;
            --brand-dark: #0E3D27;
            --brand-soft: #E7F2EB;
            --ink: #14251B;
            --muted: #66736B;
            --line: #DDE6DF;
            --surface: #FFFFFF;
            --canvas: #F5F8F5;
        }
        [data-testid="stAppViewContainer"] {
            background: radial-gradient(circle at 92% 2%, #E3F1E8 0, transparent 28%), var(--canvas);
        }
        [data-testid="stHeader"] { background: rgba(245,248,245,.82); }
        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, #F0F6F1 0%, #F8FAF8 100%);
            border-right: 1px solid var(--line);
        }
        [data-testid="stSidebar"] h2 { color: var(--brand-dark); letter-spacing: -.02em; }
        .block-container { max-width: 1480px; padding-top: 1.4rem; padding-bottom: 3rem; }
        .hero-panel {
            background: linear-gradient(125deg, #0D3B26 0%, #17613D 55%, #2A7B50 100%);
            color: white;
            border-radius: 22px;
            padding: 2rem 2.2rem 1.8rem;
            margin-bottom: 1.2rem;
            box-shadow: 0 18px 45px rgba(15, 64, 40, .18);
            position: relative;
            overflow: hidden;
        }
        .hero-panel:after {
            content: ""; position: absolute; width: 280px; height: 280px;
            border: 1px solid rgba(255,255,255,.13); border-radius: 50%;
            right: -65px; top: -125px; box-shadow: 0 0 0 40px rgba(255,255,255,.035);
        }
        .hero-kicker { font-size: .76rem; font-weight: 700; letter-spacing: .16em; opacity: .76; }
        .hero-title { font-size: clamp(2rem, 4vw, 3.15rem); line-height: 1.04; font-weight: 750; letter-spacing: -.045em; margin: .45rem 0 .7rem; }
        .hero-subtitle { max-width: 780px; font-size: 1rem; opacity: .84; margin-bottom: 1.1rem; }
        .hero-chip { display: inline-block; padding: .38rem .72rem; margin: .15rem .35rem .1rem 0; border-radius: 999px; background: rgba(255,255,255,.13); border: 1px solid rgba(255,255,255,.18); font-size: .82rem; }
        .section-heading { margin: .35rem 0 1rem; }
        .section-kicker { color: var(--brand); text-transform: uppercase; letter-spacing: .12em; font-size: .72rem; font-weight: 750; }
        .section-title { color: var(--ink); font-size: 1.65rem; font-weight: 720; letter-spacing: -.025em; margin-top: .18rem; }
        .section-description { color: var(--muted); font-size: .93rem; margin-top: .25rem; }
        div[data-testid="stMetric"] {
            background: rgba(255,255,255,.94); border: 1px solid var(--line);
            border-radius: 16px; padding: 1rem 1.1rem;
            box-shadow: 0 8px 24px rgba(24, 62, 39, .055);
        }
        div[data-testid="stMetric"] label { color: var(--muted); font-weight: 620; }
        div[data-testid="stMetricValue"] { color: var(--brand-dark); letter-spacing: -.035em; }
        [data-testid="stVerticalBlockBorderWrapper"] {
            background: rgba(255,255,255,.88); border-color: var(--line) !important;
            border-radius: 18px; box-shadow: 0 8px 26px rgba(24, 62, 39, .045);
        }
        .stTabs [data-baseweb="tab-list"] { gap: .45rem; border-bottom: 1px solid var(--line); }
        .stTabs [data-baseweb="tab"] { height: 3.2rem; padding: 0 1rem; border-radius: 10px 10px 0 0; font-weight: 620; }
        .stTabs [aria-selected="true"] { background: var(--brand-soft); color: var(--brand-dark); }
        .stButton > button, .stDownloadButton > button {
            border-radius: 10px; border-color: #B8CCBE; color: var(--brand-dark); font-weight: 650;
        }
        div[data-testid="stDataFrame"] { border: 1px solid var(--line); border-radius: 14px; overflow: hidden; }
        .footer-note { color: #758078; font-size: .78rem; text-align: center; padding-top: 2rem; }
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
            <div class="hero-kicker">INTELIGÊNCIA DE COMÉRCIO EXTERIOR</div>
            <div class="hero-title">Painel SECEX</div>
            <div class="hero-subtitle">Análise integrada das exportações e importações brasileiras por produto, classificação econômica e parceiro comercial.</div>
            <span class="hero-chip">{flow}</span>
            <span class="hero-chip">Ano {state.year}</span>
            <span class="hero-chip">{months}</span>
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
def cached_balance(
    database: str,
    state: FilterState,
    db_version: tuple[int, int],
) -> pd.DataFrame:
    return trade_balance_by_country(Path(database), state)


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
        "PANORAMA MENSAL",
        "Evolução do fluxo selecionado",
        "Compare o ano escolhido com a faixa observada nos cinco anos anteriores.",
    )
    metrics = cached_summary(str(DATABASE), state, db_version)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Valor FOB", format_compact(metrics["VL_FOB"], "US$ "))
    c2.metric("Peso líquido", format_compact(metrics["KG_LIQUIDO"], "") + " kg")
    c3.metric("FOB por kg", "—" if pd.isna(metrics["FOB_POR_KG"]) else f"US$ {metrics['FOB_POR_KG']:,.3f}")
    c4.metric("NCMs no recorte", f"{int(metrics['NCMS'] or 0):,}".replace(",", "."))

    with st.container(border=True):
        left, right = st.columns([1.5, 1], vertical_alignment="bottom")
        metric_label = left.radio("Métrica do gráfico", ["Valor FOB", "Peso líquido"], horizontal=True)
        metric = "VL_FOB" if metric_label == "Valor FOB" else "KG_LIQUIDO"
        daily_average = right.toggle("Média por dia útil", value=False)
        history, historical_years = cached_history(
            str(DATABASE), state, metric, daily_average, db_version
        )
        profile = prepare_monthly_profile(history, state.year, state.months)
        if profile["ATUAL"].notna().sum() == 0:
            st.warning("Não há observações para o recorte selecionado.")
            return
        if not historical_years:
            st.info("A base ainda não possui anos anteriores para formar a banda histórica.")
        elif len(historical_years) < 5:
            st.info(
                f"A banda usa {len(historical_years)} ano(s) disponível(is): "
                + ", ".join(map(str, historical_years))
            )
        try:
            figure = monthly_plotly(profile, state.year, metric_label, daily_average)
            st.plotly_chart(figure, use_container_width=True, config={"displaylogo": False})
        except ImportError:
            st.pyplot(monthly_matplotlib(profile, state.year, metric_label, daily_average))


def _hierarchy(state: FilterState, db_version: tuple[int, int]) -> None:
    _section_header(
        "CLASSIFICAÇÃO DE PRODUTOS",
        "Composição do comércio exterior",
        "Navegue das grandes categorias até o NCM. Os níveis SH são exibidos com sua descrição em português.",
    )
    with st.container(border=True):
        level = st.selectbox("Nível de agregação", list(LEVELS), index=0)
        table = cached_hierarchy(str(DATABASE), state, level, db_version)
        display = table.copy()

        def readable_classification(row: pd.Series) -> str:
            code = "" if pd.isna(row["CODIGO"]) else str(row["CODIGO"])
            description = "" if pd.isna(row["DESCRICAO"]) else str(row["DESCRICAO"]).strip()
            if level in {"Setor", "Categoria de uso"}:
                return description or code or "Não classificado"
            if not description or description == code:
                return f"{level} {code} — descrição não localizada"
            return f"{description} ({level} {code})"

        display.insert(0, "CLASSIFICACAO", display.apply(readable_classification, axis=1))
        visible_columns = [
            "CLASSIFICACAO",
            "KG_LIQUIDO",
            "VL_FOB",
            "PARTICIPACAO_FOB",
            "FOB_POR_KG",
        ]
        st.dataframe(
            display[visible_columns],
            use_container_width=True,
            hide_index=True,
            height=520,
            column_config={
                "CLASSIFICACAO": st.column_config.TextColumn("Classificação", width="large"),
                "KG_LIQUIDO": st.column_config.NumberColumn("Peso líquido (kg)", format="localized"),
                "VL_FOB": st.column_config.NumberColumn("Valor FOB (US$)", format="localized"),
                "PARTICIPACAO_FOB": st.column_config.NumberColumn("Participação no FOB", format="percent"),
                "FOB_POR_KG": st.column_config.NumberColumn("Valor médio (US$/kg)", format="%.4f"),
            },
        )
        st.caption(
            "A quantidade estatística foi retirada da visualização porque pode somar unidades diferentes entre produtos. "
            "Ela continua disponível no arquivo baixado."
        )
        st.download_button(
            "Baixar classificação em CSV",
            data=table.to_csv(index=False, sep=";", decimal=",", encoding="utf-8-sig"),
            file_name=f"comex_{state.flow.lower()}_{state.year}_{level.lower().replace(' ', '_')}.csv",
            mime="text/csv",
        )


def _countries(state: FilterState, db_version: tuple[int, int]) -> None:
    role = "destino" if state.flow == "EXP" else "origem"
    _section_header(
        "PARCEIROS COMERCIAIS",
        f"Principais países de {role}",
        "Ranking, participação e comparação com o mesmo período de anos anteriores.",
    )
    with st.container(border=True):
        col1, col2 = st.columns(2)
        metric_label = col1.radio(
            "Ordenar por", ["Valor FOB", "Peso líquido"], horizontal=True, key="country_metric"
        )
        top_n = col2.slider("Quantidade de países", min_value=5, max_value=30, value=15, step=5)
        metric = "VL_FOB" if metric_label == "Valor FOB" else "KG_LIQUIDO"
        raw_table = cached_ranking(str(DATABASE), state, metric, top_n, db_version)
        if raw_table.empty:
            st.info("Não há países para o recorte selecionado.")
            return
        st.plotly_chart(
            country_ranking_plotly(raw_table, metric_label, state.flow),
            use_container_width=True,
            config={"displaylogo": False},
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


def _trade_balance(state: FilterState, db_version: tuple[int, int]) -> None:
    _section_header(
        "SALDO BILATERAL",
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
    overall_status = "Superávit" if total_balance > 0 else "- Déficit" if total_balance < 0 else "Zerado"
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Exportações", format_compact(total_exports, "US$ "))
    c2.metric("Importações", format_compact(total_imports, "US$ "))
    c3.metric("Saldo comercial", format_compact(total_balance, "US$ "), delta=overall_status)
    c4.metric("Corrente de comércio", format_compact(total_exports + total_imports, "US$ "))

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
            )
        with status_col:
            st.plotly_chart(
                balance_status_plotly(balance),
                use_container_width=True,
                config={"displaylogo": False},
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


def _quality(db_version: tuple[int, int]) -> None:
    _section_header(
        "GOVERNANÇA DOS DADOS",
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
    _hero(state)
    tab_overview, tab_hierarchy, tab_countries, tab_balance, tab_quality = st.tabs(
        ["Visão mensal", "Classificação", "Países", "Saldo por país", "Qualidade"]
    )
    with tab_overview:
        _overview(state, db_version)
    with tab_hierarchy:
        _hierarchy(state, db_version)
    with tab_countries:
        _countries(state, db_version)
    with tab_balance:
        _trade_balance(state, db_version)
    with tab_quality:
        _quality(db_version)
    st.markdown(
        '<div class="footer-note">Fonte: SECEX/Comex Stat · Elaboração própria · Valores em dólares FOB</div>',
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
