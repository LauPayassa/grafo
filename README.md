# IMDb Movie Graph Exporter (US & BR)

Script em Python para baixar os datasets públicos do IMDb, filtrar filmes dos EUA e Brasil e exportar CSVs prontos para grafos (NetworkX, Neo4j, PyG, etc.).

## O que o script gera

- `nodes_movies.csv` — nós de filmes
- `nodes_persons.csv` — nós de atores e diretores
- `nodes_genres.csv` — nós de gêneros
- `edges_acted_in.csv` — arestas ator → filme
- `edges_directed.csv` — arestas diretor → filme
- `edges_has_genre.csv` — arestas filme → gênero

Os arquivos são salvos em `graph_csvs/`.

## Requisitos

- Python 3.9+
- Dependências:

```bash
pip install pandas requests tqdm
```

## Como usar

```bash
python imdb_graph_export.py
```

Na primeira execução os arquivos originais do IMDb são baixados e armazenados em `imdb_raw/`.
Nas próximas execuções, o cache local é reutilizado automaticamente.

## Filtros aplicados

- Apenas títulos com `titleType = movie`
- Apenas títulos com presença regional em `US` ou `BR` (`title.akas`)
- Apenas filmes com pelo menos `50` votos (`title.ratings`)

## Estrutura dos dados exportados

### Nós

- `nodes_movies.csv`
  - `movie_id`, `node_type`, `title`, `year`, `runtime_min`, `genres`, `avg_rating`, `num_votes`
- `nodes_persons.csv`
  - `person_id`, `node_type`, `name`, `birth_year`, `profession`
- `nodes_genres.csv`
  - `genre_id`, `node_type`, `name`

### Arestas

- `edges_acted_in.csv`
  - `src` (ator/atriz), `dst` (filme), `relation=ACTED_IN`
- `edges_directed.csv`
  - `src` (diretor), `dst` (filme), `relation=DIRECTED`
- `edges_has_genre.csv`
  - `src` (filme), `dst` (gênero), `relation=HAS_GENRE`

## Exemplo rápido com NetworkX

```python
import networkx as nx
import pandas as pd

G = nx.DiGraph()

movies = pd.read_csv("graph_csvs/nodes_movies.csv")
persons = pd.read_csv("graph_csvs/nodes_persons.csv")
genres = pd.read_csv("graph_csvs/nodes_genres.csv")

G.add_nodes_from(movies["movie_id"], node_type="Movie")
G.add_nodes_from(persons["person_id"], node_type="Person")
G.add_nodes_from(genres["genre_id"], node_type="Genre")

for csv, relation in [
    ("edges_acted_in.csv", "ACTED_IN"),
    ("edges_directed.csv", "DIRECTED"),
    ("edges_has_genre.csv", "HAS_GENRE"),
]:
    edges = pd.read_csv(f"graph_csvs/{csv}")
    G.add_edges_from(zip(edges["src"], edges["dst"]), relation=relation)
```

## Observação

Os datasets do IMDb mudam com frequência. O número de linhas exportadas depende da versão disponível no momento da execução.
