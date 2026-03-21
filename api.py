from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from main import analyze_movie

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # allow all origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/movie")
def analyze(movie: str):
    result = analyze_movie(movie)
    return result
