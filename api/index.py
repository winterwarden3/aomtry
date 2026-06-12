from app import create_app

app = create_app()

# Vercel serverless handler (explicit)
application = app

# For local development
if __name__ == "__main__":
    app.run()