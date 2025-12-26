<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	
	export let call: any;
	
	let counter = 0;
	let intervalId: any;
	
	onMount(() => {
		// Simple counter to test reactivity
		intervalId = setInterval(() => {
			counter += 1;
		}, 1000);
	});
	
	onDestroy(() => {
		if (intervalId) {
			clearInterval(intervalId);
		}
	});
	
	function handleDragStart(event: DragEvent) {
		if (event.dataTransfer) {
			event.dataTransfer.effectAllowed = 'move';
			event.dataTransfer.setData('callUuid', call.uuid);
		}
	}
</script>

<div
	class="bg-white rounded-lg shadow-md p-6 cursor-move hover:shadow-lg transition-shadow border-l-4 border-blue-500"
	draggable="true"
	on:dragstart={handleDragStart}
>
	<div class="flex justify-between items-start mb-2">
		<div>
			<h3 class="text-lg font-semibold text-gray-900">{call.caller_name}</h3>
			<p class="text-sm text-gray-600">{call.caller_id}</p>
		</div>
		<span class="text-xs bg-blue-100 text-blue-800 px-2 py-1 rounded">
			Parked
		</span>
	</div>
	
	<div class="mt-4 text-sm text-gray-500">
		⏱️ Counter: {counter}s (parked_at: {call.parked_at})
	</div>
</div>
