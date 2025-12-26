"""
PostgreSQL/TimescaleDB Connection Pool
Provides thread-safe database access for analytics storage.
"""

import os
import logging
from contextlib import contextmanager
import psycopg2
from psycopg2 import pool, extras

logger = logging.getLogger(__name__)

# Database connection pool (lazy initialization)
_connection_pool = None


def get_connection_pool():
    """
    Get or create PostgreSQL connection pool.
    Thread-safe, uses SimpleConnectionPool for single-threaded or
    ThreadedConnectionPool for multi-threaded applications.
    
    Returns:
        psycopg2.pool.ThreadedConnectionPool: Connection pool instance
    """
    global _connection_pool
    
    if _connection_pool is None:
        database_url = os.getenv('DATABASE_URL', 'postgresql://freecalls:freecalls_secure_password@localhost:5432/freecalls')
        
        logger.info(f"Initializing PostgreSQL connection pool...")
        
        try:
            # Create pool with 5-20 connections
            _connection_pool = psycopg2.pool.ThreadedConnectionPool(
                minconn=5,
                maxconn=20,
                dsn=database_url
            )
            
            logger.info("PostgreSQL connection pool created successfully")
            
        except Exception as e:
            logger.error(f"Failed to create PostgreSQL connection pool: {e}")
            raise
    
    return _connection_pool


@contextmanager
def get_db_connection():
    """
    Context manager for getting database connection from pool.
    
    Usage:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM calls LIMIT 1")
                row = cur.fetchone()
    
    Yields:
        psycopg2.connection: Database connection
    """
    pool = get_connection_pool()
    conn = pool.getconn()
    
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"Database transaction failed: {e}")
        raise
    finally:
        pool.putconn(conn)


def insert_call_analytics(call_uuid: str, call_data: dict) -> bool:
    """
    Insert call analytics record into TimescaleDB.
    
    Args:
        call_uuid: Unique call identifier
        call_data: Dictionary containing all call metadata
        
    Returns:
        bool: True if inserted successfully, False otherwise
    """
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO calls (
                        call_uuid, caller_id, agent_id, duration, wait_time, status,
                        conference_room, conference_participants, supervisor_id,
                        recording_path, parked_at, bridged_at, ended_at
                    ) VALUES (
                        %(call_uuid)s, %(caller_id)s, %(agent_id)s, %(duration)s, %(wait_time)s, %(status)s,
                        %(conference_room)s, %(conference_participants)s, %(supervisor_id)s,
                        %(recording_path)s, %(parked_at)s, %(bridged_at)s, %(ended_at)s
                    )
                    ON CONFLICT (call_uuid, ended_at) DO NOTHING
                """, {
                    'call_uuid': call_uuid,
                    'caller_id': call_data.get('caller_id'),
                    'agent_id': call_data.get('agent_id'),
                    'duration': call_data.get('duration', 0),
                    'wait_time': call_data.get('wait_time', 0),
                    'status': call_data.get('status', 'completed'),
                    'conference_room': call_data.get('conference_room', ''),
                    'conference_participants': call_data.get('conference_participants', ''),
                    'supervisor_id': call_data.get('supervisor_id', ''),
                    'recording_path': call_data.get('recording_path', ''),
                    'parked_at': call_data.get('parked_at'),
                    'bridged_at': call_data.get('bridged_at'),
                    'ended_at': call_data.get('ended_at')
                })
                
                # Log what we're inserting for debugging
                logger.info(f"Inserting analytics - participants: {call_data.get('conference_participants', 'NONE')}, supervisor: {call_data.get('supervisor_id', 'NONE')}")
        
        logger.debug(f"Call {call_uuid} analytics inserted into TimescaleDB")
        return True
        
    except Exception as e:
        logger.error(f"Failed to insert call {call_uuid} analytics: {e}")
        return False


def test_connection():
    """
    Test database connection and print version info.
    
    Returns:
        bool: True if connection successful
    """
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT version();")
                version = cur.fetchone()
                logger.info(f"PostgreSQL version: {version[0]}")
                
                # Check if TimescaleDB is installed
                cur.execute("SELECT extversion FROM pg_extension WHERE extname='timescaledb';")
                result = cur.fetchone()
                if result:
                    logger.info(f"TimescaleDB version: {result[0]}")
                else:
                    logger.warning("TimescaleDB extension not found!")
                
                return True
                
    except Exception as e:
        logger.error(f"Database connection test failed: {e}")
        return False


# Test connection on import (optional, can be removed in production)
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_connection()
