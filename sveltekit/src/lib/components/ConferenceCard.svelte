<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	
	export let conference: {
		room: string;
		caller_number: string;
		caller_name: string;
		agents: string[];
		started_at: number;
	};
	
	export let managers: Array<{
		id: string;
		name: string;
		status: string;
		activeCall: any;
	}> = [];
	
	let duration = 0;
	let interval: number;
	let eavesdropping = false;
	
	function getManagerStatus(extensionId: string) {
		const manager = managers.find(m => m.id === extensionId);
		if (!manager || manager.status === 'offline') return 'offline';
		return manager.status === 'on-call' ? 'busy' : 'online';
	}
	
	function getManagerButtonClass(extensionId: string) {
		const status = getManagerStatus(extensionId);
		if (eavesdropping) return 'bg-gray-300 text-gray-500 cursor-not-allowed';
		if (status === 'busy') return 'bg-red-400 text-white cursor-not-allowed opacity-50';
		if (status === 'offline') return 'bg-gray-400 text-gray-700 cursor-not-allowed opacity-50';
		return 'bg-blue-500 text-white hover:bg-blue-600';
	}
	
	function isManagerDisabled(extensionId: string) {
		const status = getManagerStatus(extensionId);
		return eavesdropping || status === 'busy' || status === 'offline';
	}
	
	function updateDuration() {
		const now = Math.floor(Date.now() / 1000);
		duration = now - conference.started_at;
	}
	
	function formatDuration(seconds: number): string {
		const mins = Math.floor(seconds / 60);
		const secs = seconds % 60;
		return `${mins}:${secs.toString().padStart(2, '0')}`;
	}
	
	async function startEavesdrop(extension: string) {
		eavesdropping = true;
		try {
			const response = await fetch('/api/eavesdrop', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({
					conference_room: conference.room,
					manager_extension: extension
				})
			});
			if (!response.ok) {
				alert('Failed to start eavesdrop');
				eavesdropping = false;
			}
		} catch (error) {
			alert('Error starting eavesdrop: ' + error);
			eavesdropping = false;
		}
	}
	
	onMount(() => {
		updateDuration();
		interval = setInterval(updateDuration, 1000) as unknown as number;
	});
	
	onDestroy(() => {
		if (interval) clearInterval(interval);
	});
</script>

<div class="bg-gradient-to-br from-purple-50 to-purple-100 rounded-lg shadow-md p-4 border-2 border-purple-300">
	<div class="flex items-center justify-between mb-3">
		<div class="flex items-center gap-2">
			<span class="text-2xl">🎙️</span>
			<div>
				<h3 class="text-sm font-bold text-purple-900">Conference Room {conference.room}</h3>
				<p class="text-xs text-purple-700">Active 3-way call</p>
			</div>
		</div>
		<div class="text-right">
			<p class="text-lg font-mono text-purple-900">{formatDuration(duration)}</p>
			<p class="text-xs text-purple-600">duration</p>
		</div>
	</div>
	
	<div class="space-y-2">
		<!-- Original Caller -->
		<div class="bg-white rounded p-2 border border-purple-200">
			<p class="text-xs text-purple-600 font-medium">📞 Original Caller</p>
			<p class="text-sm font-semibold text-gray-900">{conference.caller_name}</p>
			<p class="text-xs text-gray-600">{conference.caller_number}</p>
		</div>
		
		<!-- Agents in Conference -->
		<div class="bg-white rounded p-2 border border-purple-200">
			<p class="text-xs text-purple-600 font-medium mb-1">👥 Agents Connected</p>
			<div class="flex gap-2">
				{#each conference.agents as agent}
					<span class="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-purple-200 text-purple-900">
						Agent {agent}
					</span>
				{/each}
			</div>
		</div>
		
		<!-- Manager Controls -->
		<div class="mt-3 pt-2 border-t border-purple-200">
			<p class="text-xs text-purple-600 font-medium mb-2">🎧 Manager Eavesdrop</p>
			<div class="grid grid-cols-4 gap-1">
				<button
					on:click={() => startEavesdrop('1000')}
					disabled={isManagerDisabled('1000')}
					class="px-2 py-1 rounded text-xs font-medium transition-colors {getManagerButtonClass('1000')}"
				>
					1000
				</button>
				<button
					on:click={() => startEavesdrop('1004')}
					disabled={isManagerDisabled('1004')}
					class="px-2 py-1 rounded text-xs font-medium transition-colors {getManagerButtonClass('1004')}"
				>
					1004
				</button>
				<button
					on:click={() => startEavesdrop('1005')}
					disabled={isManagerDisabled('1005')}
					class="px-2 py-1 rounded text-xs font-medium transition-colors {getManagerButtonClass('1005')}"
				>
					1005
				</button>
				<button
					on:click={() => startEavesdrop('1006')}
					disabled={isManagerDisabled('1006')}
					class="px-2 py-1 rounded text-xs font-medium transition-colors {getManagerButtonClass('1006')}"
				>
					1006
				</button>
				<button
					on:click={() => startEavesdrop('1007')}
					disabled={isManagerDisabled('1007')}
					class="px-2 py-1 rounded text-xs font-medium transition-colors {getManagerButtonClass('1007')}"
				>
					1007
				</button>
				<button
					on:click={() => startEavesdrop('1008')}
					disabled={isManagerDisabled('1008')}
					class="px-2 py-1 rounded text-xs font-medium transition-colors {getManagerButtonClass('1008')}"
				>
					1008
				</button>
				<button
					on:click={() => startEavesdrop('1009')}
					disabled={isManagerDisabled('1009')}
					class="px-2 py-1 rounded text-xs font-medium transition-colors {getManagerButtonClass('1009')}"
				>
					1009
				</button>
				<button
					on:click={() => startEavesdrop('1010')}
					disabled={isManagerDisabled('1010')}
					class="px-2 py-1 rounded text-xs font-medium transition-colors {getManagerButtonClass('1010')}"
				>
					1010
				</button>
			</div>
		</div>
	</div>
</div>
