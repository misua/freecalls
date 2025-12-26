/**
 * Call Volume API
 * Returns call volume over time with dynamic bucketing
 */

import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import getPostgresConnection from '$lib/postgres';

export const GET: RequestHandler = async ({ url }) => {
	const from = url.searchParams.get('from') || new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString();
	const to = url.searchParams.get('to') || new Date().toISOString();
	const interval = url.searchParams.get('interval') || 'hour'; // hour, day, week
	
	try {
		const sql = getPostgresConnection();
		
		// Map interval to PostgreSQL interval
		const intervalMap: Record<string, string> = {
			hour: '1 hour',
			day: '1 day',
			week: '7 days'
		};
		
		const bucketInterval = intervalMap[interval] || '1 hour';
		
		// Query call volume with time bucketing
		const volumeData = await sql`
			SELECT 
				time_bucket(${bucketInterval}::interval, ended_at) as time_bucket,
				COUNT(*)::int as call_count,
				COUNT(CASE WHEN status = 'completed' THEN 1 END)::int as completed,
				COUNT(CASE WHEN status = 'abandoned' THEN 1 END)::int as abandoned
			FROM calls
			WHERE ended_at >= ${from}::timestamptz 
			  AND ended_at < ${to}::timestamptz
			GROUP BY time_bucket
			ORDER BY time_bucket ASC
		`;
		
		// Format response
		const formattedData = volumeData.map(row => ({
			timestamp: row.time_bucket.toISOString(),
			total: row.call_count,
			completed: row.completed,
			abandoned: row.abandoned
		}));
		
		return json({
			success: true,
			data: {
				interval,
				volume: formattedData
			}
		});
		
	} catch (error) {
		console.error('[Analytics] Volume query failed:', error);
		return json({
			success: false,
			error: 'Failed to fetch call volume data'
		}, { status: 500 });
	}
};
