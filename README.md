# ZUS API Deployment

This repository contains the production-ready deployment setup for the ZUS Coffee Chatbot API, designed for scalable, secure, and efficient web API hosting.

## 🚀 Overview
- **Framework:** FastAPI (Python 3.11+)
- **Containerization:** Docker
- **Cloud Deployment:** Render (sync deployment)
- **Vector Search:** Pinecone
- **Database:** SQLite (auto-generated from CSV)
- **API Docs:** OpenAPI/Swagger at `/docs`

## 📦 Directory Structure
```
zus-api-deployment/
├── app/                # FastAPI app and source code
├── data/               # Data files (CSV, SQL, DB)
├── Dockerfile          # Production Docker build
├── render.yaml         # Render deployment config
├── requirements.txt    # Python dependencies
├── .dockerignore       # Docker build exclusions
├── .gitignore          # Git exclusions
└── README.md           # This file
```

## 🌐 Quick Start (Local)
1. **Clone the repository**
   ```bash
   git clone https://github.com/EASONTAN03/zus-api-deployment.git
   cd zus-api-deployment
   ```
2. **Create a Python environment**
   ```bash
   conda create -n zus-api python=3.11
   conda activate zus-api
   pip install -r requirements.txt
   ```
3. **Set environment variables** (or use a `.env` file)
   ```env
   OPENAI_API_KEY=your-openai-key
   PINECONE_API_KEY=your-pinecone-key
   PINECONE_ENVIRONMENT=your-pinecone-environment
   SECRET_KEY=your-secret-key
   ```
4. **Run the API**
   ```bash
   cd app
   uvicorn app:app --host 0.0.0.0 --port 8000 --reload
   ```
5. **Access the API**
   - Docs: [http://localhost:8000/docs](http://localhost:8000/docs)
   - Health: [http://localhost:8000/api/v1/health](http://localhost:8000/api/v1/health)

## 🐳 Docker Usage
1. **Build the image**
   ```bash
   docker build -t zus-api .
   ```
2. **Run the container**
   ```bash
   docker run -p 8000:8000 \
     -e OPENAI_API_KEY=your-key \
     -e PINECONE_API_KEY=your-key \
     -e PINECONE_ENVIRONMENT=your-env \
     -e SECRET_KEY=your-secret \
     zus-api
   ```

## ☁️ Render Deployment
- **Automatic deployment** via `render.yaml`
- **Health checks** and **auto-restart**
- **Environment variables** managed in Render dashboard

## 🔑 Environment Variables
- `OPENAI_API_KEY` (required)
- `PINECONE_API_KEY` (required)
- `PINECONE_ENVIRONMENT` (required)
- `SECRET_KEY` (required)
- `CORS_ORIGINS` (optional, default: `*`)
- `LOG_LEVEL` (optional, default: `INFO`)

## 🛠️ API Endpoints
- `GET /api/v1/health` — Health check
- `POST /api/v1/chat` — Conversational endpoint
- `GET /api/v1/products` — Product search
- `GET /api/v1/outlets` — Outlet/location search
- `POST /api/v1/register` — User registration
- `POST /api/v1/login` — User login

## 📝 Notes
- The SQLite DB is auto-generated from CSV if missing.
- Pinecone and OpenAI keys are required for full functionality.
- For development, use `--reload` with Uvicorn; for production, use Gunicorn as in the Dockerfile.

## 📄 License
MIT License. See LICENSE for details. 