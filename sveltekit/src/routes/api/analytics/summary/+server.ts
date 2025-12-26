/**
 * Analytics Summary API
 * Returns key metrics for dashboard cards
 */

import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import getPostgresConnection from '$lib/postgres';

export const GET: RequestHandler = async ({ url }) => {
	const from = url.searchParams.get('from') || new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString();
	const to = url.searchParams.get('to') || new Date().toISOString();
	
	try {
		const sql = getPostgresConnection();
		
		// Get summary stats for date range
		const [summary] = await sql`
			SELECT 
				COUNT(*)::int as total_calls,
				COALESCE(AVG(duration), 0)::int as avg_duration,
				COALESCE(AVG(wait_time), 0)::int as avg_wait_time,
				COUNT(CASE WHEN status = 'completed' THEN 1 END)::int as completed_calls,
				COUNT(CASE WHEN status = 'abandoned' THEN 1 END)::int as abandoned_calls,
				COUNT(CASE WHEN agent_id IS NOT NULL THEN 1 END)::int as handled_calls
			FROM calls
			WHERE ended_at >= ${from}::timestamptz 
			  AND ended_at < ${to}::timestamptz
		`;
		
		// Calculate metrics
		const totalCalls = summary.total_calls || 0;
		const abandonRate = totalCalls > 0 
			? ((summary.abandoned_calls / totalCalls) * 100).toFixed(1)
			: '0.0';
		
		return json({
			success: true,
			data: {
				total_calls: totalCalls,
				completed_calls: summary.completed_calls || 0,
				abandoned_calls: summary.abandoned_calls || 0,
				handled_calls: summary.handled_calls || 0,
				avg_duration: summary.avg_duration || 0,
				avg_wait_time: summary.avg_wait_time || 0,
				abandon_rate: parseFloat(abandonRate),
				date_range: { from, to }
			}
		});
		
	} catch (error) {
		console.error('[Analytics] Summary query failed:', error);
		return json({
			success: false,
			error: 'Failed to fetch analytics summary'
		}, { status: 500 });
	}
};
