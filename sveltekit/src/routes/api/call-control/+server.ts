import { getRedisClient } from '$lib/redis';
import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';

export const POST: RequestHandler = async ({ request }) => {
	const { action, callUuid, targetAgent, agentId } = await request.json();
	
	if (!action || !callUuid) {
		return json({ error: 'Missing action or callUuid' }, { status: 400 });
	}
	
	const redis = await getRedisClient();
	
	// Write control command to Redis
	const command = {
		action,
		call_uuid: callUuid,
		target_agent: targetAgent,
		agent_id: agentId,
		timestamp: Date.now()
	};
	
	await redis.lPush('cmd:call_control', JSON.stringify(command));
	
	console.log(`Queued call control: ${action} for ${callUuid}`);
	
	return json({ success: true });
};
