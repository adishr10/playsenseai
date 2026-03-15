from fastapi import FastAPI
from main import analyze_movie

app = FastAPI()

@app.get("/analyze")
def analyze(movie: str):
    result = analyze_movie(movie)
    return result