import { getRedisClient } from '$lib/redis';
import type { RequestHandler } from './$types';
import { json } from '@sveltejs/kit';

export const POST: RequestHandler = async ({ request }) => {
	const redis = await getRedisClient();
	const { conference_room, manager_extension } = await request.json();
	
	if (!conference_room || !manager_extension) {
		return json({ error: 'Missing conference_room or manager_extension' }, { status: 400 });
	}
	
	// Push eavesdrop command to Redis queue
	await redis.lPush('cmd:call_control', JSON.stringify({
		action: 'eavesdrop',
		conference_room,
		manager_extension
	}));
	
	return json({ success: true });
};
