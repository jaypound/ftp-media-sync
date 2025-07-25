import os
import logging

logger = logging.getLogger(__name__)

# Check which database backend to use
USE_POSTGRESQL = os.getenv('USE_POSTGRESQL', 'false').lower() == 'true'

if USE_POSTGRESQL:
    logger.info("Using PostgreSQL database backend")
    from database_postgres import PostgreSQLDatabaseManager
    import getpass
    
    # Create global instance with PostgreSQL
    default_pg_conn = f'postgresql://{getpass.getuser()}@localhost/ftp_media_sync'
    db_manager = PostgreSQLDatabaseManager(
        connection_string=os.getenv(
            'DATABASE_URL',
            default_pg_conn
        )
    )
else:
    logger.info("Using MongoDB database backend")
    # Import original MongoDB implementation
    from database_mongo import DatabaseManager
    
    # Create global instance with MongoDB
    db_manager = DatabaseManager(
        connection_string=os.getenv(
            'MONGODB_URI',
            'mongodb://localhost:27017/'
        ),
        database_name=os.getenv('MONGODB_DATABASE', 'castus')
    )