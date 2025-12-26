/**
 * Agent Performance API
 * Returns top agents by calls handled
 */

import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import getPostgresConnection from '$lib/postgres';

export const GET: RequestHandler = async ({ url }) => {
	const from = url.searchParams.get('from') || new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString();
	const to = url.searchParams.get('to') || new Date().toISOString();
	const limit = parseInt(url.searchParams.get('limit') || '10', 10);
	
	try {
		const sql = getPostgresConnection();
		
		// Get top agents for date range
		const agentStats = await sql`
			SELECT 
				agent_id,
				COUNT(*)::int as calls_handled,
				COALESCE(AVG(duration), 0)::int as avg_duration,
				SUM(duration)::int as total_talk_time,
				COALESCE(AVG(wait_time), 0)::int as avg_wait_time,
				COUNT(CASE WHEN status = 'completed' THEN 1 END)::int as completed_calls
			FROM calls
			WHERE agent_id IS NOT NULL
			  AND ended_at >= ${from}::timestamptz 
			  AND ended_at < ${to}::timestamptz
			GROUP BY agent_id
			ORDER BY calls_handled DESC
			LIMIT ${limit}
		`;
		
		// Format response
		const formattedData = agentStats.map(row => ({
			agent_id: row.agent_id,
			calls_handled: row.calls_handled,
			avg_duration: row.avg_duration,
			total_talk_time: row.total_talk_time,
			avg_wait_time: row.avg_wait_time,
			completed_calls: row.completed_calls,
			completion_rate: row.calls_handled > 0 
				? ((row.completed_calls / row.calls_handled) * 100).toFixed(1)
				: '0.0'
		}));
		
		return json({
			success: true,
			data: {
				agents: formattedData
			}
		});
		
	} catch (error) {
		console.error('[Analytics] Agents query failed:', error);
		return json({
			success: false,
			error: 'Failed to fetch agent performance data'
		}, { status: 500 });
	}
};
