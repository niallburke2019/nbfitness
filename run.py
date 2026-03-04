from app import create_app

app = create_app()

# ✅ ADD THIS HERE
@app.get("/health")
def health():
    return {"status": "ok"}, 200


if __name__ == "__main__":
    app.run(debug=True)