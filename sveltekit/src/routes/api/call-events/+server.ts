import { getRedisClient } from '$lib/redis';
import type { RequestHandler } from './$types';

export const GET: RequestHandler = async () => {
	const redis = await getRedisClient();
	
	const encoder = new TextEncoder();
	let subscriber: any = null;
	let isClosed = false;
	let messageHandler: ((message: string) => void) | null = null;
	
	// Create SSE stream with proper cleanup
	const stream = new ReadableStream({
		async start(controller) {
			try {
				subscriber = redis.duplicate();
				await subscriber.connect();
				
				// Define message handler
				messageHandler = (message: string) => {
					if (!isClosed) {
						try {
							controller.enqueue(encoder.encode(`data: ${message}\n\n`));
						} catch (e) {
							// Stream closed
							isClosed = true;
						}
					}
				};
				
				// Subscribe to call events
				await subscriber.subscribe('call_events', messageHandler);
			} catch (error) {
				console.error('SSE setup error:', error);
				isClosed = true;
				try {
					controller.close();
				} catch (e) {
					// Already closed
				}
			}
		},
		
		async cancel() {
			// Called when client disconnects
			isClosed = true;
			if (subscriber) {
				try {
					await subscriber.unsubscribe('call_events');
					await subscriber.disconnect();
					await subscriber.quit();
				} catch (e) {
					// Ignore cleanup errors
				}
			}
		}
	});
	
	return new Response(stream, {
		headers: {
			'Content-Type': 'text/event-stream',
			'Cache-Control': 'no-cache',
			'Connection': 'keep-alive'
		}
	});
};
