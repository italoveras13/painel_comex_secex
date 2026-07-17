# Painel SECEX em Streamlit

Aplicação para explorar arquivos brutos anuais de exportação e importação da
SECEX/Comex Stat, com histórico mensal, banda de mínima/máxima dos cinco anos
anteriores, média por dia útil, hierarquia de produtos, ranking de países e
saldo comercial bilateral. Inclui também uma triagem indicativa da exposição
das exportações aos Estados Unidos à ação da Seção 301 de julho de 2026.

## Arquitetura

```text
painel_comex_secex/
├── app.py
├── run_etl.py
├── requirements.txt
├── Dockerfile
├── .streamlit/config.toml
├── data/
│   ├── raw/
│   │   ├── exp/                 # EXP_AAAA.csv
│   │   ├── imp/                 # IMP_AAAA.csv
│   │   └── aux/                 # TABELAS_AUXILIARES.xlsx e dados_calendario.xlsx
│   └── processed/               # comex.duckdb (gerado)
├── src/
│   ├── auxiliary.py             # descoberta e normalização das planilhas
│   ├── charts.py                # Plotly + fallback Matplotlib
│   ├── etl.py                   # carga incremental e joins
│   ├── queries.py               # consultas analíticas parametrizadas
│   └── utils.py
└── tests/
    └── smoke_test.py
```

O NCM possui 8 dígitos e é descendente do SH6. Por isso, o drill-down usado é
`Setor → Categoria de uso → SH2 → SH4 → SH6 → NCM`, que é consistente com a
classificação oficial e contém todos os níveis pedidos. As descrições de SH2 e
SH4 são localizadas automaticamente nas abas que contenham `NO_SH2_POR` e
`NO_SH4_POR`.

O painel também calcula, para cada parceiro, `saldo = exportações − importações`
e classifica o resultado como superávit, déficit ou zerado. Esse cálculo sempre
combina os dois fluxos, mesmo quando a barra lateral estiver em um fluxo
específico.

### Aba Seção 301 EUA

A aba cruza as exportações brasileiras destinadas aos Estados Unidos com as
2.126 linhas HTSUS do Anexo II de `Brazil 301 Final Action FRN 7-15-2026 final`,
consolidadas em 1.229 códigos SH6 dos capítulos 01–97. Os arquivos de referência
estão em `data/reference/` e são carregados diretamente pelo app.

As situações exibidas são:

- `Sem correspondência - potencialmente afetado`: não foi localizada linha
  isenta no mesmo SH6;
- `Correspondência com isenção no SH6`: existe ao menos uma linha HTSUS listada
  no Anexo II dentro do mesmo SH6;
- `Correspondência condicionada no SH6`: a linha está marcada como `Ex`,
  `Pharma` ou `Aircraft`;
- `Correspondência mista no SH6`: o SH6 reúne linhas sem limitação explícita e
  outras condicionadas.

O resultado é uma triagem, pois HTSUS e NCM compartilham os seis primeiros
dígitos, mas seus desdobramentos nacionais não são equivalentes. Exceções
baseadas em regimes dos capítulos 98/99 e condições de entrada não podem ser
integralmente identificadas por SH6.

A aba também traz uma análise de impacto por setor macro e por seção ISIC. Ela
mostra o principal país cliente, a posição dos Estados Unidos entre os destinos,
a participação dos EUA nas exportações do grupo, o valor sem correspondência de
isenção e a exposição do setor (`valor potencialmente afetado / exportações
mundiais do setor`). Assim, valor absoluto e dependência comercial podem ser
avaliados separadamente.

Para auditar ou refazer a extração com o PDF original:

```bash
python scripts/extract_section301_pdf.py "caminho/Brazil 301 Final Action FRN 7-15-2026 final.pdf"
```

## 1. Preparação dos dados

1. Copie `EXP_AAAA.csv` para `data/raw/exp/`.
2. Copie `IMP_AAAA.csv` para `data/raw/imp/`.
3. Copie `TABELAS_AUXILIARES.xlsx` e `dados_calendario.xlsx` para
   `data/raw/auxiliares/`. O nome `auxiliares` é usado porque `AUX` é um nome
   reservado do Windows.
4. Crie o ambiente e instale as dependências:

```bash
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
```

5. Execute o ETL:

```bash
python run_etl.py
```

O ETL identifica automaticamente as abas do arquivo auxiliar pelas colunas,
sem depender do nome da aba. Os códigos são tratados como texto e completados
com zeros à esquerda (`NCM=8`, `país=3`, `unidade=2`, `SH6=6`, `SH4=4`,
`SH2=2`). A tabela de fatos mantém o arquivo de origem e a carga só é refeita
quando tamanho ou data de modificação do CSV mudar. Use `--rebuild` para uma
reconstrução completa.

## 2. Execução

```bash
streamlit run app.py
```

O app abre por padrão em `http://localhost:8501`.

## 3. Regra do gráfico histórico

Para um ano selecionado `t`, a linha mostra os meses de `t`. A banda cinza usa,
para cada mês, o mínimo e o máximo observados entre `t-5` e `t-1`. Se a base
tiver menos de cinco anos anteriores, a interface informa quantos anos foram
efetivamente usados. Em “média diária”, o total mensal é dividido pelos dias
úteis do mês, calculados a partir de `DIA_UTIL`.

## 4. Ranking de países

O ranking usa o mesmo recorte de fluxo, meses e produto da tela. A participação
é calculada sobre o total do recorte no ano selecionado. As variações de 1 e 2
anos comparam os mesmos meses; quando a base de comparação é zero ou ausente, o
resultado permanece nulo em vez de produzir infinito.

## 5. Cache e desempenho

- DuckDB persiste a base tratada em disco e evita concatenar CSVs a cada clique.
- O ETL é incremental por arquivo.
- `st.cache_data` memoriza consultas agregadas; cada consulta abre uma conexão
  DuckDB curta e somente leitura, evitando compartilhar conexão entre sessões.
- A data de modificação de `comex.duckdb` entra na chave do cache, invalidando
  resultados após nova carga.
- Nenhum DataFrame de milhões de linhas é enviado ao navegador.

Para bases de 5–10 anos, prefira SSD e pelo menos 8 GB de RAM. Rode o ETL fora
do processo web em produção e publique apenas o banco DuckDB pronto.

## 6. Deploy

### Docker (recomendado)

```bash
docker build -t painel-comex .
docker run --rm -p 8501:8501 -v "$PWD/data:/app/data" painel-comex
```

O mesmo contêiner pode ser usado em Render, Railway, Fly.io, Azure Web App ou
uma VM. Para dezenas de milhões de linhas, uma VM/serviço com disco persistente
é mais adequado que o plano gratuito do Streamlit Community Cloud.

### Streamlit Community Cloud

É adequado para demonstração se o repositório contiver apenas uma amostra ou um
`comex.duckdb` agregado e de tamanho moderado. Não versione CSVs brutos grandes
nem dados que não possam ser públicos.
