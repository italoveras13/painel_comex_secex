# Painel do Comércio Exterior

Aplicação para explorar arquivos brutos anuais de exportação e importação da
SECEX/Comex Stat, com histórico mensal, banda de mínima/máxima dos cinco anos
anteriores, média por dia útil, hierarquia de produtos, ranking de países e
saldo comercial bilateral. Inclui também uma triagem indicativa da exposição
das exportações aos Estados Unidos à ação da Seção 301 de julho de 2026.

As principais telas analíticas incluem:

- visão mensal com FOB, toneladas e valor médio em US$/kg, comparação anual,
  média histórica e tabela mensal;
- classificação com detalhamento dos principais NCM e parceiros de cada grupo;
- países com abertura por setor, categoria de uso e NCM comercializado;
- saldo bilateral com cartões responsivos, ranking de superávits e déficits;
- painel temático da Seção 301 com gráficos dimensionados para leitura em
  notebooks e monitores menores, incluindo a evolução mensal da tarifa efetiva
  cobrada pelos EUA sobre importações originárias do Brasil.

## Arquitetura

```text
painel_comex_secex/
├── app.py
├── run_etl.py
├── build_web_database.py        # gera a base agregada para publicação
├── requirements.txt
├── Dockerfile
├── .streamlit/config.toml
├── data/
│   ├── raw/
│   │   ├── exp/                 # EXP_AAAA.csv
│   │   ├── imp/                 # IMP_AAAA.csv
│   │   └── auxiliares/          # TABELAS_AUXILIARES.xlsx e dados_calendario.xlsx
│   └── processed/               # comex.duckdb e comex_web.duckdb (gerados)
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

A aba temática foi organizada em sete subabas:

- `Resumo executivo`: valor e tonelagem potencialmente afetados, exposição,
  prioridades e ranking dos SH6;
- `Tarifa efetiva`: série mensal de janeiro de 2019 a maio de 2026, calculada
  como direitos aduaneiros divididos pelo valor das importações para consumo,
  com indicadores, dados detalhados e download em CSV;
- `Setores e SH6`: análise por setor macro ou seção ISIC e detalhamento dos
  SH6 mais expostos dentro de cada setor;
- `Estados exportadores`: exportações totais de cada UF, vendas e participação
  dos EUA, valor potencialmente afetado, ranking de exposição e comparação
  entre dependência do mercado americano e alcance potencial das tarifas. A
  subaba permite selecionar uma UF e detalhar os SH6 ou NCM com maior exposição;
- `Categoria de uso`: tabelas por CGCE — bens de capital, intermediários, de
  consumo e combustíveis e lubrificantes — com abertura até o NCM;
- `Produtos NCM`: triagem detalhada e exportação em CSV;
- `Metodologia`: escopo, datas de referência e limitações do cruzamento SH6.

A análise setorial mostra o principal país cliente, a posição dos Estados
Unidos entre os destinos, a participação dos EUA nas exportações do grupo, o
valor sem correspondência de isenção e a exposição do setor (`valor
potencialmente afetado / exportações mundiais do setor`). Assim, valor absoluto
e dependência comercial podem ser avaliados separadamente. Pesos físicos são
apresentados em toneladas; `US$/kg` é mantido apenas como preço unitário.

A série tarifária vem do U.S. Census Bureau, International Trade API, e fica em
`data/reference/us_effective_tariff_brazil.csv`. Ela é independente do banco
DuckDB e, por isso, não exige refazer o ETL nem o `comex_web.duckdb`.

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

### Banco reduzido para publicação

Depois de concluir o ETL completo, gere uma base mensal agregada por fluxo,
NCM, país e UF exportadora:

```bash
python build_web_database.py
```

O comando cria `data/processed/comex_web.duckdb` sem alterar o
`comex.duckdb`. Antes de concluir, o script compara os totais de quantidade,
peso, FOB, frete e seguro entre os dois bancos. A saída informa a redução de
linhas e tamanho e também indica se o arquivo cabe no GitHub comum, se exige
Git LFS ou se permanece acima de 2 GB.

Caso a saída já exista e precise ser refeita:

```bash
python build_web_database.py --force
```

Ao atualizar de uma versão anterior do projeto, execute esse comando uma vez.
A UF passou a fazer parte da base web para permitir a análise dos estados
exportadores na aba Seção 301. Isso recria somente o banco web e não refaz o ETL
do `comex.duckdb` completo.

Por padrão, a geração limita o DuckDB a 2 GB de memória e permite o uso de
disco temporário. Em uma máquina com pouca memória, é possível reduzir esse
limite; o processamento ficará mais demorado:

```bash
python build_web_database.py --force --memory-limit 1GB --threads 2
```

O aplicativo escolhe automaticamente `comex_web.duckdb` quando ele existe e
volta ao banco completo quando não existe. A variável de ambiente
`COMEX_DATABASE` pode apontar explicitamente para outro caminho.

#### Envio ao GitHub

Se o arquivo final tiver até 100 MB, use o Git normalmente. Entre 100 MB e
2 GB, configure o Git LFS antes do commit:

```bash
git lfs install
git lfs track "data/processed/comex_web.duckdb"
git add .gitattributes data/processed/comex_web.duckdb
git commit -m "Adiciona banco agregado para publicação"
git push
```

Arquivos únicos acima de 2 GB não cabem no Git LFS dos planos GitHub Free e
Pro. Nesse caso, não faça o commit do banco: use um volume persistente em uma
plataforma como Railway/Render ou reduza adicionalmente a base.

#### Streamlit Community Cloud

Com o código e um banco compatível no GitHub, acesse `share.streamlit.io`,
escolha o repositório, a branch e `app.py` como arquivo principal. O deploy
instala as dependências de `requirements.txt` e disponibiliza uma URL
`streamlit.app`.

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

É adequado para demonstração se o repositório contiver apenas uma amostra ou o
`comex_web.duckdb` de tamanho moderado. O suporte ao download de objetos Git LFS
pode variar no ambiente de build; confira os logs do primeiro deploy. Se o
arquivo não for materializado, use Railway/Render com volume ou armazenamento
externo. Não versione CSVs brutos grandes nem dados que não possam ser públicos.
