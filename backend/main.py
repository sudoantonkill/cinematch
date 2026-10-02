"""Spark-powered API for CineMatch movie discovery."""

from contextlib import asynccontextmanager
import json
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

import numpy as np
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from pyspark.ml.evaluation import RegressionEvaluator
from pyspark.ml.recommendation import ALS
from pyspark.sql import SparkSession, functions as F

DATA_DIR = Path(__file__).resolve().parent.parent / "ml-latest-small"

spark: SparkSession | None = None
als_model = None
movies_df = None
ratings_df = None
movie_titles: dict[int, str] = {}
poster_cache: dict[int, str | None] = {}
movie_vectors: dict[int, np.ndarray] = {}
model_metrics: dict[str, float] = {}
catalog_stats: dict[str, int] = {}


class DiscoveryRequest(BaseModel):
    movie_ids: list[int] = Field(min_length=1, max_length=5)
    num_recommendations: int = Field(default=12, ge=1, le=24)


class UserRecommendationRequest(BaseModel):
    user_id: int
    num_recommendations: int = Field(default=12, ge=1, le=24)


def require_ready() -> None:
    if als_model is None or movies_df is None:
        raise HTTPException(status_code=503, detail="The recommendation model is still warming up.")


def movie_payload(row, score: float | None = None, selected_genres: set[str] | None = None) -> dict:
    genres = [genre for genre in row.genres.split("|") if genre != "(no genres listed)"]
    item = {
        "movieId": row.movieId,
        "title": row.title,
        "genres": row.genres,
        "posterUrl": f"http://localhost:8000/posters/{row.movieId}",
    }
    if score is not None:
        item["match"] = round(max(0.0, min(100.0, score * 100)), 1)
        shared = [genre for genre in genres if selected_genres and genre in selected_genres]
        genre_line = f"Shares {', '.join(shared[:2])} with your selections." if shared else f"Brings a {genres[0] if genres else 'distinct'} perspective into your profile."
        item["whySelected"] = f"Its audience-rating pattern is a {item['match']}% match for your taste profile."
        item["highlights"] = [
            f"{genres[0] if genres else 'Cinema'} is at the heart of this pick.",
            genre_line,
            "Chosen from a cluster of viewers whose ratings resemble yours.",
        ]
    return item


def initialize_spark_and_model() -> None:
    """Train the notebook's tuned ALS model and prepare a small serving index."""
    global spark, als_model, movies_df, ratings_df, movie_titles, poster_cache, movie_vectors, model_metrics, catalog_stats

    if not DATA_DIR.exists():
        raise FileNotFoundError(f"MovieLens data was not found at {DATA_DIR}")

    spark = (
        SparkSession.builder.appName("CineMatch-Recommendations")
        .config("spark.driver.host", "127.0.0.1")
        .config("spark.sql.shuffle.partitions", "8")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")
    ratings_df = spark.read.csv(str(DATA_DIR / "ratings.csv"), header=True, inferSchema=True).cache()
    movies_df = spark.read.csv(str(DATA_DIR / "movies.csv"), header=True, inferSchema=True).cache()
    ratings_df.count()
    movies_df.count()
    movie_titles = {int(row.movieId): row.title for row in movies_df.select("movieId", "title").collect()}
    poster_cache = {}

    # Parameters are the tuned version in the accompanying notebook.
    train_data, test_data = ratings_df.randomSplit([0.8, 0.2], seed=42)
    als = ALS(maxIter=20, regParam=0.15, rank=10, userCol="userId", itemCol="movieId",
              ratingCol="rating", coldStartStrategy="drop", seed=42)
    als_model = als.fit(train_data)
    predictions = als_model.transform(test_data)
    model_metrics = {
        name: float(RegressionEvaluator(metricName=name, labelCol="rating", predictionCol="prediction").evaluate(predictions))
        for name in ("rmse", "mse", "mae", "r2")
    }

    # ALS turns every movie into a latent-factor vector. Keeping this compact index
    # in memory makes interactive multi-title discovery immediate after Spark trains.
    movie_vectors = {int(row.id): np.asarray(row.features, dtype=float)
                     for row in als_model.itemFactors.select("id", "features").collect()}
    catalog_stats = {"movies": movies_df.count(), "ratings": ratings_df.count(),
                     "users": ratings_df.select("userId").distinct().count()}
    print(f"CineMatch ready — RMSE: {model_metrics['rmse']:.4f}")


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        initialize_spark_and_model()
    except Exception as error:
        print(f"Model initialization failed: {error}")
    yield
    if spark is not None:
        spark.stop()


app = FastAPI(title="CineMatch API", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173", "http://localhost:5174"],
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


@app.get("/")
async def root():
    return {"name": "CineMatch API", "status": "ready" if als_model is not None else "warming_up"}


@app.get("/health")
async def health():
    return {"ready": als_model is not None, "catalog": catalog_stats}


@app.get("/metrics")
async def get_metrics():
    require_ready()
    return {**model_metrics, "model": "ALS collaborative filtering",
            "parameters": {"rank": 10, "maxIter": 20, "regParam": 0.15}}


@app.get("/movies")
async def search_movies(q: str = Query("", max_length=100),
                        limit: int = Query(18, ge=1, le=48)):
    """Search server-side so the browser never downloads the full catalogue."""
    require_ready()
    query = q.strip().lower()
    results = movies_df
    if query:
        results = results.filter(F.lower(F.concat_ws(" ", F.col("title"), F.col("genres"))).contains(query))
    rows = results.orderBy(F.col("title").asc()).limit(limit).collect()
    return {"movies": [movie_payload(row) for row in rows]}


@app.get("/featured")
async def featured_movies(limit: int = Query(12, ge=1, le=24)):
    require_ready()
    popular = (ratings_df.groupBy("movieId").agg(F.count("rating").alias("rating_count"), F.avg("rating").alias("average_rating"))
               .filter(F.col("rating_count") >= 40).orderBy(F.desc("average_rating"), F.desc("rating_count")).limit(limit))
    rows = popular.join(movies_df, "movieId").orderBy(F.desc("average_rating"), F.desc("rating_count")).collect()
    return {"movies": [{**movie_payload(row), "rating": round(row.average_rating, 1)} for row in rows]}


@app.get("/posters/{movie_id}")
def poster(movie_id: int):
    """Resolve a public Wikimedia poster on demand, then cache and redirect to it."""
    require_ready()
    title = movie_titles.get(movie_id)
    if title is None:
        raise HTTPException(status_code=404, detail="Movie not found")
    if movie_id not in poster_cache:
        base_title = title.rsplit(" (", 1)[0]
        poster_url = None
        for candidate in (f"{base_title} (film)", base_title):
            try:
                request = Request(
                    f"https://en.wikipedia.org/api/rest_v1/page/summary/{quote(candidate.replace(' ', '_'))}",
                    headers={"User-Agent": "CineMatch/1.0 (local movie discovery project)"},
                )
                with urlopen(request, timeout=5) as response:
                    data = json.loads(response.read().decode("utf-8"))
                poster_url = data.get("thumbnail", {}).get("source")
                if poster_url:
                    break
            except Exception:
                continue
        poster_cache[movie_id] = poster_url
    if not poster_cache[movie_id]:
        raise HTTPException(status_code=404, detail="Poster unavailable")
    return RedirectResponse(url=poster_cache[movie_id], status_code=307)


@app.post("/discover")
async def discover(request: DiscoveryRequest):
    """Find related films using cosine similarity in the ALS latent-factor space."""
    require_ready()
    seed_ids = list(dict.fromkeys(request.movie_ids))
    if any(movie_id not in movie_vectors for movie_id in seed_ids):
        raise HTTPException(status_code=404, detail="One or more selected movies cannot be modeled from available ratings.")
    seed = np.mean([movie_vectors[movie_id] for movie_id in seed_ids], axis=0)
    seed_norm = np.linalg.norm(seed)
    if seed_norm == 0:
        raise HTTPException(status_code=422, detail="These selections do not have enough signal to build a taste profile.")
    similarities = []
    for movie_id, vector in movie_vectors.items():
        if movie_id not in seed_ids:
            denominator = np.linalg.norm(vector) * seed_norm
            if denominator:
                similarities.append((movie_id, float(np.dot(vector, seed) / denominator)))
    score_by_id = dict(sorted(similarities, key=lambda item: item[1], reverse=True)[:request.num_recommendations])
    selected_rows = movies_df.filter(F.col("movieId").isin(seed_ids)).collect()
    selected_genres = {genre for row in selected_rows for genre in row.genres.split("|")}
    details = movies_df.filter(F.col("movieId").isin(list(score_by_id))).collect()
    recommendations = [movie_payload(row, score_by_id[row.movieId], selected_genres) for row in details]
    recommendations.sort(key=lambda movie: score_by_id[movie["movieId"]], reverse=True)
    return {"recommendations": recommendations, "based_on": seed_ids, "method": "ALS latent-factor similarity"}


@app.post("/recommendations")
async def recommendations_for_user(request: UserRecommendationRequest):
    """Notebook-style top-N recommendations for an existing MovieLens user."""
    require_ready()
    user = spark.createDataFrame([(request.user_id,)], ["userId"])
    results = als_model.recommendForUserSubset(user, request.num_recommendations).collect()
    if not results:
        raise HTTPException(status_code=404, detail="That MovieLens user ID has no recommendation profile.")
    scored = {int(item.movieId): float(item.rating) for item in results[0].recommendations}
    details = movies_df.filter(F.col("movieId").isin(list(scored))).collect()
    recommendations = [movie_payload(row, min(1, max(0, scored[row.movieId] / 5))) for row in details]
    recommendations.sort(key=lambda movie: scored[movie["movieId"]], reverse=True)
    return {"user_id": request.user_id, "recommendations": recommendations}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
