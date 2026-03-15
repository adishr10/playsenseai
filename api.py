from fastapi import FastAPI

from main import analyze_movie

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # allow all origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/analyze")
def analyze(movie: str):
    result = analyze_movie(movie)
    return result
