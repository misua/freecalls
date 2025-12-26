import { getRedisClient } from '$lib/redis';
import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';

export const POST: RequestHandler = async ({ request }) => {
	const { callUuid, agentId } = await request.json();
	
	if (!callUuid || !agentId) {
		return json({ error: 'Missing callUuid or agentId' }, { status: 400 });
	}
	
	const redis = await getRedisClient();
	
	// Write bridge command to Redis
	// Format: call_uuid:agent_id
	await redis.lPush('cmd:bridge', `${callUuid}:${agentId}`);
	
	console.log(`Queued bridge command: ${callUuid} -> ${agentId}`);
	
	return json({ success: true });
};
