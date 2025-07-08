import os
import logging
from fastapi import FastAPI, Request, Response, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import uvicorn
from src.utils import setup_logging
from fastapi.responses import JSONResponse
from datetime import datetime, timedelta
import jwt
from src.rate_limit import pwd_context, load_users, save_users

# Load environment variables
load_dotenv()

# Configure logging
setup_logging()
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="ZUS Coffee Chatbot API",
    description="A conversational AI chatbot for ZUS Coffee products and outlets",
    version="1.0.0"
)

# CORS setup
cors_origins = os.getenv("CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security headers middleware
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response: Response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=()"
    return response

# Global variables for models (will be initialized in startup)
embedding_model = None
product_summary_chain = None
outlet_write_query_chain = None
outlet_summary_chain = None
pinecone_index = None
outlets_sql_db = None

# Utility to create JWT
def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=15))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

@app.on_event("startup")
async def startup_event():
    """Initialize models and connections on startup"""
    global embedding_model, product_summary_chain, outlet_write_query_chain, outlet_summary_chain, pinecone_index, outlets_sql_db
    
    try:
        # Import here to avoid circular imports
        from src.vectorstore import initialize_vectorstore, get_openai_embedding
        from src.openai_chain import initialize_chains
        from src.text2SQL import initialize_database
        
        logger.info("Initializing vector store...")
        pinecone_index = await initialize_vectorstore()
        
        logger.info("Initializing embedding model...")
        embedding_model = get_openai_embedding
        
        logger.info("Initializing OpenAI chains...")
        product_summary_chain, outlet_write_query_chain, outlet_summary_chain, intent_chain = await initialize_chains()
        
        logger.info("Initializing database...")
        outlets_sql_db = initialize_database()
        
        # Set global variables in router
        from src.router import set_global_variables
        set_global_variables(
            embedding_model, 
            product_summary_chain, 
            outlet_write_query_chain, 
            outlet_summary_chain, 
            pinecone_index, 
            outlets_sql_db,
            intent_chain
        )
        
        logger.info("All components initialized successfully!")
        
    except Exception as e:
        logger.error(f"Error during startup: {e}")
        raise

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "ZUS Coffee Chatbot API",
        "version": "1.0.0",
        "status": "running"
    }

# Include router
from src.router import router
app.include_router(router, prefix="/api/v1")

# Registration endpoint
@app.post("/register")
def register(username: str = Form(...), password: str = Form(...)):
    users = load_users()
    if username in users:
        raise HTTPException(status_code=400, detail="Username already exists")
    hashed_pw = pwd_context.hash(password)
    users[username] = {"username": username, "hashed_password": hashed_pw}
    save_users(users)
    return JSONResponse(content={"msg": "Registration successful"})

# Login route
@app.post("/login")
def login(username: str = Form(...), password: str = Form(...)):
    users = load_users()
    user = users.get(username)
    if not user or not pwd_context.verify(password, user["hashed_password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_access_token(data={"sub": username})
    return JSONResponse(content={"access_token": token, "token_type": "bearer"})

if __name__ == "__main__":
    # Get port from environment variable (for Render)
    port = int(os.environ.get("PORT", 8000))
    
    # Run the application
    uvicorn.run(
        "app:app",
        host="0.0.0.0",  # Bind to all interfaces
        port=port,
        reload=False  # Disable reload in production
    )
