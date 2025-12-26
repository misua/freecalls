import postgres from 'postgres';

const DATABASE_URL = process.env.DATABASE_URL || 'postgresql://freecalls:freecalls_secure_password@timescaledb:5432/freecalls';

// Create a singleton postgres instance with connection pooling
let sql: ReturnType<typeof postgres> | null = null;

/**
 * Get a PostgreSQL connection instance (singleton pattern)
 * Uses connection pooling with max 10 connections
 * Connects to TimescaleDB for analytics queries
 */
function getPostgresConnection() {
	if (!sql) {
		sql = postgres(DATABASE_URL, {
			max: 10, // Maximum number of connections in the pool
			idle_timeout: 20, // Close idle connections after 20 seconds
			max_lifetime: 60 * 30, // Max connection lifetime: 30 minutes
			connect_timeout: 30, // Connection timeout: 30 seconds
			prepare: true, // Enable prepared statements for better performance
			onnotice: () => {} // Silence NOTICE messages
		});
	}
	return sql;
}

/**
 * Close all database connections
 * Call this during graceful shutdown
 */
export async function closePostgresConnection() {
	if (sql) {
		await sql.end({ timeout: 5 });
		sql = null;
	}
}

// Export as default for easy importing
export default getPostgresConnection;
