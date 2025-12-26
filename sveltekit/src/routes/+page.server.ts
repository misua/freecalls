import { getRedisClient } from '$lib/redis';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async () => {
	const redis = await getRedisClient();
	
	// Get all parked calls
	const callUuids = await redis.zRange('calls:parked', 0, -1);
	
	const calls = await Promise.all(
		callUuids.map(async (uuid) => {
			const data = await redis.hGetAll(`call:${uuid}`);
			return {
				uuid,
				...data,
				parked_at: parseInt(data.parked_at || '0')
			};
		})
	);
	
	// Get agents and their active calls
	const agentIds = ['1000', '1001', '1002', '1006', '1007', '1008', '1009', '1010'];
	const managerIds = ['1004', '1005'];
	const allUserIds = [...agentIds, ...managerIds];
	
	const agents = await Promise.all(
		agentIds.map(async (id) => {
			const activeCall = await redis.hGetAll(`agent:${id}:active_call`);
			const isRegistered = await redis.exists(`user:${id}:registered`);
			
			// Parse conference_with if it exists (stored as JSON string)
			let conferenceWith = null;
			if (activeCall.conference_with) {
				try {
					conferenceWith = JSON.parse(activeCall.conference_with);
				} catch (e) {
					console.error('Failed to parse conference_with:', e);
				}
			}
			
			// Status: online (registered, no call), on-call (registered with call), offline (not registered)
			let status = 'offline';
			if (isRegistered) {
				status = activeCall.call_uuid ? 'on-call' : 'online';
			}
			
			return {
				id,
				name: `Agent ${id}`,
				status,
				activeCall: activeCall.call_uuid ? {
					call_uuid: activeCall.call_uuid,
					caller_number: activeCall.caller_number,
					caller_name: activeCall.caller_name,
					bridged_at: parseInt(activeCall.bridged_at || '0'),
					conference_with: conferenceWith,
					conference_room: activeCall.conference_room
				} : null
			};
		})
	);
	
	// Get manager statuses (registered and availability)
	const managers = await Promise.all(
		managerIds.map(async (id) => {
			const activeCall = await redis.hGetAll(`agent:${id}:active_call`);
			const isRegistered = await redis.exists(`user:${id}:registered`);
			
			// Status: online (registered, no call), on-call (registered with call), offline (not registered)
			let status = 'offline';
			if (isRegistered) {
				status = activeCall.call_uuid ? 'on-call' : 'online';
			}
			
			return {
				id,
				name: `Manager ${id}`,
				status,
				activeCall: activeCall.call_uuid ? {
					call_uuid: activeCall.call_uuid,
					caller_number: activeCall.caller_number,
					caller_name: activeCall.caller_name,
					bridged_at: parseInt(activeCall.bridged_at || '0')
				} : null
			};
		})
	);
	
	return {
		calls,
		agents,
		managers
	};
};
