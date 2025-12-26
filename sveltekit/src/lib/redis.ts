import { createClient } from 'redis';

const REDIS_URL = process.env.REDIS_URL || 'redis://localhost:6379';

let client: ReturnType<typeof createClient> | null = null;

export async function getRedisClient() {
	if (!client) {
		client = createClient({ url: REDIS_URL });
		client.on('error', (err) => console.error('Redis Client Error', err));
		await client.connect();
	}
	return client;
}
