import os
import requests
import pandas as pd
from tqdm import tqdm

# ── Configurações ──────────────────────────────────────────────────────────────
OUTPUT_DIR = "graph_csvs"
CACHE_DIR = "imdb_raw"
COUNTRIES = {"US", "BR"}  # regiões a manter
TITLE_TYPE = "movie"  # apenas filmes (exclui séries, shorts, etc.)
MIN_VOTES = 50  # filmes com pelo menos N votos (evita lixo)

IMDB_BASE = "https://datasets.imdbws.com/"
FILES = [
    "title.basics.tsv.gz",
    "title.akas.tsv.gz",
    "title.ratings.tsv.gz",
    "title.principals.tsv.gz",
    "title.crew.tsv.gz",
    "name.basics.tsv.gz",
]

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(CACHE_DIR, exist_ok=True)


# ── Helpers ────────────────────────────────────────────────────────────────────
def download(filename: str) -> str:
    """Baixa o arquivo se ainda não estiver em cache."""
    path = os.path.join(CACHE_DIR, filename)
    if os.path.exists(path):
        print(f"  [cache] {filename}")
        return path

    url = IMDB_BASE + filename
    print(f"  [download] {filename} ...")
    r = requests.get(url, stream=True, timeout=120)
    r.raise_for_status()
    total = int(r.headers.get("content-length", 0))

    with open(path, "wb") as f, tqdm(
        total=total,
        unit="B",
        unit_scale=True,
        desc=filename,
    ) as bar:
        for chunk in r.iter_content(32768):
            f.write(chunk)
            bar.update(len(chunk))

    return path


def read_tsv(path: str, usecols=None) -> pd.DataFrame:
    r"""Lê TSV gzipado com tratamento de nulos do IMDb (\N)."""
    print(f"  [lendo] {os.path.basename(path)} ...")
    return pd.read_csv(
        path,
        sep="\t",
        na_values=r"\N",
        usecols=usecols,
        dtype=str,
        low_memory=False,
    )


def save(df: pd.DataFrame, name: str):
    path = os.path.join(OUTPUT_DIR, name)
    df.to_csv(path, index=False)
    print(f"  [salvo] {name}  ({len(df):,} linhas)")


# ── 1. Baixar arquivos ─────────────────────────────────────────────────────────
print("\n=== 1/6  Baixando arquivos do IMDb ===")
paths = {f: download(f) for f in FILES}


# ── 2. Filtrar filmes US/BR ────────────────────────────────────────────────────
print("\n=== 2/6  Filtrando filmes US & BR ===")

basics = read_tsv(
    paths["title.basics.tsv.gz"],
    usecols=[
        "tconst",
        "titleType",
        "primaryTitle",
        "startYear",
        "runtimeMinutes",
        "genres",
    ],
)
basics = basics[basics["titleType"] == TITLE_TYPE].copy()
print(f"  Filmes totais (tipo=movie): {len(basics):,}")

akas = read_tsv(
    paths["title.akas.tsv.gz"],
    usecols=["titleId", "region"],
)
# tconsts que aparecem em US ou BR
valid_ids = akas[akas["region"].isin(COUNTRIES)]["titleId"].unique()
basics = basics[basics["tconst"].isin(valid_ids)].copy()
print(f"  Após filtro US+BR: {len(basics):,}")


# ── 3. Filtrar por votos mínimos ───────────────────────────────────────────────
print("\n=== 3/6  Aplicando filtro de votos mínimos ===")

ratings = read_tsv(
    paths["title.ratings.tsv.gz"],
    usecols=["tconst", "averageRating", "numVotes"],
)
ratings["numVotes"] = pd.to_numeric(ratings["numVotes"], errors="coerce")
ratings = ratings[ratings["numVotes"] >= MIN_VOTES]

basics = basics[basics["tconst"].isin(ratings["tconst"])].copy()
print(f"  Após filtro de votos (>= {MIN_VOTES}): {len(basics):,}")

movie_ids = set(basics["tconst"])


# ── 4. Construir nós de filmes ─────────────────────────────────────────────────
print("\n=== 4/6  Construindo nós ===")

# Merge com ratings
movies_df = basics.merge(ratings, on="tconst", how="left")
movies_df = movies_df.rename(
    columns={
        "tconst": "movie_id",
        "primaryTitle": "title",
        "startYear": "year",
        "runtimeMinutes": "runtime_min",
        "genres": "genres",
        "averageRating": "avg_rating",
        "numVotes": "num_votes",
    }
)
movies_df["node_type"] = "Movie"
save(
    movies_df[
        [
            "movie_id",
            "node_type",
            "title",
            "year",
            "runtime_min",
            "genres",
            "avg_rating",
            "num_votes",
        ]
    ],
    "nodes_movies.csv",
)


# ── 5. Gêneros como nós próprios ───────────────────────────────────────────────
all_genres = movies_df["genres"].dropna().str.split(",").explode().str.strip().unique()
genres_df = pd.DataFrame({"genre_id": all_genres, "node_type": "Genre", "name": all_genres})
save(genres_df, "nodes_genres.csv")

# Arestas filme → gênero
edges_genre = (
    movies_df[["movie_id", "genres"]]
    .dropna(subset=["genres"])
    .assign(genre=lambda d: d["genres"].str.split(","))
    .explode("genre")
)
edges_genre["genre"] = edges_genre["genre"].str.strip()
edges_genre = edges_genre[["movie_id", "genre"]].rename(columns={"movie_id": "src", "genre": "dst"})
edges_genre["relation"] = "HAS_GENRE"
save(edges_genre, "edges_has_genre.csv")


# ── 6. Pessoas (atores e diretores) ───────────────────────────────────────────
print("\n=== 5/6  Construindo nós de pessoas ===")

principals = read_tsv(
    paths["title.principals.tsv.gz"],
    usecols=["tconst", "nconst", "category"],
)
principals = principals[principals["tconst"].isin(movie_ids)].copy()

crew = read_tsv(
    paths["title.crew.tsv.gz"],
    usecols=["tconst", "directors"],
)
crew = crew[crew["tconst"].isin(movie_ids)].dropna(subset=["directors"]).copy()

# Atores
actors_edges = principals[principals["category"].isin(["actor", "actress"])][["tconst", "nconst"]].copy()
actors_edges.columns = ["dst", "src"]  # src=ator, dst=filme
actors_edges["relation"] = "ACTED_IN"

# Diretores (de title.crew)
dir_rows = []
for _, row in crew.iterrows():
    for nconst in str(row["directors"]).split(","):
        nconst = nconst.strip()
        if nconst and nconst != "nan":
            dir_rows.append({"src": nconst, "dst": row["tconst"], "relation": "DIRECTED"})

directors_edges = pd.DataFrame(dir_rows)

# Todos os nconsts relevantes
all_nconsts = set(actors_edges["src"]) | set(directors_edges["src"])

names = read_tsv(
    paths["name.basics.tsv.gz"],
    usecols=["nconst", "primaryName", "birthYear", "primaryProfession"],
)
names = names[names["nconst"].isin(all_nconsts)].copy()
names = names.rename(
    columns={
        "nconst": "person_id",
        "primaryName": "name",
        "birthYear": "birth_year",
        "primaryProfession": "profession",
    }
)
names["node_type"] = "Person"
save(names[["person_id", "node_type", "name", "birth_year", "profession"]], "nodes_persons.csv")

save(actors_edges[["src", "dst", "relation"]], "edges_acted_in.csv")
save(directors_edges[["src", "dst", "relation"]], "edges_directed.csv")


# ── Resumo final ───────────────────────────────────────────────────────────────
print("\n=== 6/6  Resumo dos arquivos gerados ===")
print(f"\n  Pasta de saída: ./{OUTPUT_DIR}/\n")

summary = {
    "nodes_movies.csv": "Nós — Filmes (movie_id, title, year, avg_rating, ...)",
    "nodes_persons.csv": "Nós — Atores & Diretores (person_id, name, ...)",
    "nodes_genres.csv": "Nós — Gêneros (genre_id, name)",
    "edges_acted_in.csv": "Arestas — Ator → Filme  (src, dst, relation)",
    "edges_directed.csv": "Arestas — Diretor → Filme (src, dst, relation)",
    "edges_has_genre.csv": "Arestas — Filme → Gênero  (src, dst, relation)",
}
for fname, desc in summary.items():
    fpath = os.path.join(OUTPUT_DIR, fname)
    if os.path.exists(fpath):
        with open(fpath, encoding="utf-8") as f:
            n = sum(1 for _ in f) - 1
        print(f"  {fname:<30} {n:>8,} linhas   {desc}")

print(
    """
Como usar no seu projeto:
──────────────────────────────────────────────────────────
# NetworkX
import networkx as nx, pandas as pd

G = nx.DiGraph()

movies  = pd.read_csv("graph_csvs/nodes_movies.csv")
persons = pd.read_csv("graph_csvs/nodes_persons.csv")
G.add_nodes_from(movies["movie_id"],  node_type="Movie")
G.add_nodes_from(persons["person_id"],node_type="Person")

for csv, rel in [("edges_acted_in.csv","ACTED_IN"),
                 ("edges_directed.csv","DIRECTED"),
                 ("edges_has_genre.csv","HAS_GENRE")]:
    df = pd.read_csv(f"graph_csvs/{csv}")
    G.add_edges_from(zip(df["src"], df["dst"]), relation=rel)

print(nx.info(G))
──────────────────────────────────────────────────────────
"""
)
