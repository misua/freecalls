/**
 * Recent Calls API
 * Returns paginated list of recent calls with full details
 */

import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import getPostgresConnection from '$lib/postgres';

export const GET: RequestHandler = async ({ url }) => {
	const limit = parseInt(url.searchParams.get('limit') || '50', 10);
	const offset = parseInt(url.searchParams.get('offset') || '0', 10);
	const status = url.searchParams.get('status'); // filter by status
	const agentId = url.searchParams.get('agent_id'); // filter by agent
	
	try {
		const sql = getPostgresConnection();
		
		// Build dynamic query with filters
		let whereConditions = [];
		let params: any = { limit, offset };
		
		if (status) {
			whereConditions.push('status = ${status}');
			params.status = status;
		}
		
		if (agentId) {
			whereConditions.push('agent_id = ${agentId}');
			params.agentId = agentId;
		}
		
		const whereClause = whereConditions.length > 0 
			? `WHERE ${whereConditions.join(' AND ')}`
			: '';
		
		// Get recent calls with pagination
		const recentCalls = await sql`
			SELECT 
				call_uuid,
				caller_id,
				agent_id,
				duration,
				wait_time,
				status,
				conference_room,
				supervisor_id,
				recording_path,
				ended_at,
				created_at
			FROM calls
			${whereClause ? sql.unsafe(whereClause) : sql``}
			ORDER BY ended_at DESC
			LIMIT ${limit}
			OFFSET ${offset}
		`;
		
		// Get total count for pagination
		const [countResult] = await sql`
			SELECT COUNT(*)::int as total
			FROM calls
			${whereClause ? sql.unsafe(whereClause) : sql``}
		`;
		
		// Format response
		const formattedCalls = recentCalls.map(row => ({
			call_uuid: row.call_uuid,
			caller_id: row.caller_id,
			agent_id: row.agent_id,
			duration: row.duration,
			wait_time: row.wait_time,
			status: row.status,
			conference_room: row.conference_room || null,
			supervisor_id: row.supervisor_id || null,
			recording_path: row.recording_path || null,
			ended_at: row.ended_at?.toISOString(),
			created_at: row.created_at?.toISOString()
		}));
		
		return json({
			success: true,
			data: {
				calls: formattedCalls,
				pagination: {
					total: countResult.total || 0,
					limit,
					offset,
					has_more: (offset + limit) < (countResult.total || 0)
				}
			}
		});
		
	} catch (error) {
		console.error('[Analytics] Recent calls query failed:', error);
		return json({
			success: false,
			error: 'Failed to fetch recent calls'
		}, { status: 500 });
	}
};
