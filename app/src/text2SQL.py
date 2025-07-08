import os
import logging
from typing import Dict, Any
from sqlalchemy import create_engine, text, inspect
import pandas as pd
from .utils import load_config

logger = logging.getLogger(__name__)

config = load_config()

def execute_sql_query(state: Dict[str, Any], db_engine) -> Dict[str, Any]:
    """Execute SQL query and return results"""
    try:
        sql_query = state.get("query", "")
        if not sql_query:
            state["result"] = []
            return state
        with db_engine.connect() as conn:
            result = conn.execute(text(sql_query))
            rows = result.fetchall()
            columns = result.keys()
            state["result"] = [dict(zip(columns, row)) for row in rows]
        return state
    except Exception as e:
        logger.error(f"Error executing SQL query: {e}")
        state["result"] = []
        return state

def load_outlet_data(csv_path: str) -> list:
    """Load outlet data from CSV file"""
    try:
        if os.path.exists(csv_path):
            df = pd.read_csv(csv_path)
            return df.to_dict('records')
        else:
            logger.warning(f"Outlet data file not found: {csv_path}")
            return []
    except Exception as e:
        logger.error(f"Error loading outlet data: {e}")
        return []
    
def is_db_empty(db_path: str) -> bool:
    """Check if a SQLite database is missing or contains no tables using SQLAlchemy."""
    if not os.path.exists(db_path):
        return True
    try:
        engine = create_engine(f"sqlite:///{db_path}")
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        return len(tables) == 0
    except Exception as e:
        print(f"Error inspecting database: {e}")
        return True

def save_outlets_to_sql(outlets, sql_path: str):
    """Save outlet rows to an SQL file from iterable of dicts (e.g. csv.DictReader)"""
        
    def safe_int(val, default=0):
        try:
            if pd.isna(val):
                return default
            return int(val)
        except Exception:
            return default

    def safe_float(val, default=0.0):
        try:
            if pd.isna(val):
                return default
            return float(val)
        except Exception:
            return default

    with open(sql_path, "w", encoding="utf-8") as f:
        f.write("CREATE TABLE outlets (id INTEGER PRIMARY KEY, name TEXT, address TEXT, link TEXT, reviews_count INTEGER, reviews_average FLOAT, phone_number TEXT, services TEXT, place_type TEXT, opens_at TEXT);\n")

        for i, row in enumerate(outlets):
            id = i + 1

            # Escape and format fields safely
            def esc(val):
                return str(val or "").replace("'", "''")

            f.write(
                f"INSERT INTO outlets VALUES ({id}, "
                f"'{esc(row.get('name'))}', "
                f"'{esc(row.get('address'))}', "
                f"'{esc(row.get('link'))}', "
                f"{safe_int(row.get('reviews_count', 0))}, "
                f"{safe_float(row.get('reviews_average', 0.0))}, "
                f"'{esc(row.get('phone_number'))}', "
                f"'{esc(row.get('services'))}', "
                f"'{esc(row.get('place_type'))}', "
                f"'{esc(row.get('opens_at'))}');\n"
            )

def create_outlet_db_from_csv(db_path: str, csv_path: str, sql_path: str = None, table_name: str = "outlets"):
    """Create SQLite DB from CSV or SQL if it does not exist"""
    if is_db_empty(db_path):
        logger.info(f"Database {db_path} not found. Creating from {csv_path} or {sql_path}...")

        if not os.path.exists(sql_path):
            df = pd.read_csv(csv_path, encoding='utf-8-sig')
            expanded_outlets_data = df.to_dict(orient='records')
            save_outlets_to_sql(expanded_outlets_data, sql_path)
        else:
            print("Outlets from zus website scraped to csv file.")

        logger.info(f"Initializing DB from SQL file: {sql_path}")
        with open(sql_path, "r", encoding="utf-8") as f:
            sql_script = f.read()
        
        engine = create_engine(f"sqlite:///{db_path}")
        with engine.begin() as conn:
            for stmt in [s.strip() for s in sql_script.split(";") if s.strip()]:
                conn.execute(text(stmt))
        logger.info(f"Database {db_path} created from SQL file successfully.")

    else:
        logger.info(f"Database {db_path} already exists.")

def initialize_database():
    """Initialize the SQL database connection, creating from CSV if missing, using config.json filepaths."""
    try:
        filepaths = config.get("filepaths", {})
        outlets_config = filepaths.get("outlets", {})
        csv_path = outlets_config.get("csv", "data/zus_outlets_final.csv")
        sql_path = outlets_config.get("sql", "data/zus_outlets.sql")
        db_path = outlets_config.get("db", "data/zus_outlets.db")

        create_outlet_db_from_csv(db_path, csv_path, sql_path, table_name="outlets")
        engine = create_engine(f"sqlite:///{db_path}")
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("Database connection established successfully")
        return engine
    except Exception as e:
        logger.error(f"Error initializing database: {e}")
        raise
