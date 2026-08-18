"""Migration utility script to copy VALENCE GRC data from SQLite to PostgreSQL.

This script connects to SQLite using a synchronous engine, connects to PostgreSQL,
creates the target tables if they do not exist, and copies all data table by table.
"""
import os
import sys
from sqlalchemy import create_engine, MetaData, Table, select
from sqlalchemy.orm import sessionmaker

# Add src to python path to load models
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from grc_dashboard.db.models import Base

# Source and Target database URLs
SQLITE_URL = "sqlite:///./valence.db"
# Use mapped port 5435 from the host
POSTGRES_URL = os.getenv(
    "MIGRATION_DATABASE_URL",
    "postgresql://valence_admin:CHANGE_ME_DB_PASSWORD@localhost:5435/valence_grc"
)

def migrate():
    print(f"Connecting to source SQLite: {SQLITE_URL}")
    sqlite_engine = create_engine(SQLITE_URL)
    
    print(f"Connecting to target PostgreSQL: {POSTGRES_URL}")
    postgres_engine = create_engine(POSTGRES_URL)
    
    print("Creating tables on PostgreSQL if they do not exist...")
    Base.metadata.create_all(postgres_engine)
    
    sqlite_metadata = MetaData()
    sqlite_metadata.reflect(bind=sqlite_engine)
    
    # We want to copy data for all tables defined in our models
    table_names = list(Base.metadata.tables.keys())
    print(f"Found {len(table_names)} tables in models to migrate.")
    
    sqlite_session_factory = sessionmaker(bind=sqlite_engine)
    postgres_session_factory = sessionmaker(bind=postgres_engine)
    
    sqlite_session = sqlite_session_factory()
    postgres_session = postgres_session_factory()
    
    try:
        for name in table_names:
            if name not in sqlite_metadata.tables:
                print(f"Table '{name}' not found in SQLite. Skipping.")
                continue
                
            print(f"Migrating table '{name}'...")
            
            # Clear existing data in target table
            postgres_session.execute(Table(name, Base.metadata, autoload_with=postgres_engine).delete())
            postgres_session.commit()
            
            # Query all rows from SQLite
            sqlite_table = sqlite_metadata.tables[name]
            with sqlite_engine.connect() as sqlite_conn:
                rows = sqlite_conn.execute(select(sqlite_table)).fetchall()
            
            if not rows:
                print(f"Table '{name}' is empty. Skipping.")
                continue
                
            postgres_table = Table(name, Base.metadata, autoload_with=postgres_engine)
            
            # Convert Row objects to dicts
            insert_data = []
            for row in rows:
                row_dict = dict(row._mapping)
                # SQLite can sometimes return list/dict directly or as strings, SQLAlchemy JSON handles it.
                insert_data.append(row_dict)
                
            # Bulk insert into Postgres
            postgres_session.execute(postgres_table.insert(), insert_data)
            postgres_session.commit()
            print(f"Successfully migrated {len(insert_data)} rows for '{name}'.")
            
            # If the table has an integer primary key sequence in Postgres, reset it
            # We check if 'id' is an integer primary key
            pk_cols = [c for c in postgres_table.primary_key.columns if c.name == 'id']
            if pk_cols and pk_cols[0].type.python_type is int:
                # Find max id
                max_id_res = postgres_session.execute(select(postgres_table.c.id).order_by(postgres_table.c.id.desc())).first()
                if max_id_res and max_id_res[0] is not None:
                    max_id = max_id_res[0]
                    seq_name = f"{name}_id_seq"
                    # Check if sequence exists and reset it
                    try:
                        postgres_session.execute(f"SELECT setval('{seq_name}', {max_id})")
                        postgres_session.commit()
                        print(f"Reset sequence '{seq_name}' to {max_id}.")
                    except Exception as e:
                        # Sequence might not exist if it's not a serial column
                        postgres_session.rollback()
                        
        print("\nMigration completed successfully!")
        
    except Exception as e:
        postgres_session.rollback()
        print(f"\nError occurred during migration: {e}")
        raise e
    finally:
        sqlite_session.close()
        postgres_session.close()

if __name__ == "__main__":
    migrate()
