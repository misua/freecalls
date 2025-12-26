<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	
	export let agent: any;
	
	let isDragOver = false;
	let callDuration = 0;
	let intervalId: any;
	
	// Update call duration timer
	$: if (agent.activeCall) {
		if (!intervalId) {
			intervalId = setInterval(() => {
				const now = Math.floor(Date.now() / 1000);
				callDuration = now - agent.activeCall.bridged_at;
			}, 1000);
			// Initialize immediately
			const now = Math.floor(Date.now() / 1000);
			callDuration = now - agent.activeCall.bridged_at;
		}
	} else {
		if (intervalId) {
			clearInterval(intervalId);
			intervalId = null;
		}
		callDuration = 0;
	}
	
	onDestroy(() => {
		if (intervalId) {
			clearInterval(intervalId);
		}
	});
	
	function formatDuration(seconds: number): string {
		const mins = Math.floor(seconds / 60);
		const secs = seconds % 60;
		return `${mins}:${secs.toString().padStart(2, '0')}`;
	}
	
	async function handleHold() {
		try {
			const response = await fetch('/api/call-control', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ 
					action: 'hold',
					callUuid: agent.activeCall.call_uuid 
				})
			});
			if (response.ok) {
				console.log('Call on hold');
			}
		} catch (error) {
			console.error('Hold failed:', error);
		}
	}
	
	async function handleResume() {
		try {
			const response = await fetch('/api/call-control', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ 
					action: 'resume',
					callUuid: agent.activeCall.call_uuid 
				})
			});
			if (response.ok) {
				console.log('Call resumed');
			}
		} catch (error) {
			console.error('Resume failed:', error);
		}
	}
	
	async function handleTransfer(targetAgent: string) {
		try {
			const response = await fetch('/api/call-control', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ 
					action: 'transfer',
					callUuid: agent.activeCall.call_uuid,
					targetAgent 
				})
			});
			if (response.ok) {
				console.log(`Transferred to ${targetAgent}`);
			}
		} catch (error) {
			console.error('Transfer failed:', error);
		}
	}
	
	async function handleHangup() {
		try {
			const response = await fetch('/api/call-control', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ 
					action: 'hangup',
					callUuid: agent.activeCall.call_uuid,
					agentId: agent.id
				})
			});
			if (response.ok) {
				console.log('Call ended');
			}
		} catch (error) {
			console.error('Hangup failed:', error);
		}
	}
	
	async function handleConference(targetAgent: string) {
		try {
			const response = await fetch('/api/call-control', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ 
					action: 'conference',
					callUuid: agent.activeCall.call_uuid,
					targetAgent 
				})
			});
			if (response.ok) {
				console.log(`Added ${targetAgent} to conference`);
			}
		} catch (error) {
			console.error('Conference failed:', error);
		}
	}
	
	let showTransferMenu = false;
	let showConferenceMenu = false;
	
	async function handleDrop(event: DragEvent) {
		event.preventDefault();
		isDragOver = false;
		
		if (event.dataTransfer) {
			const callUuid = event.dataTransfer.getData('callUuid');
			
			if (callUuid) {
				// Call assign API
				try {
					const response = await fetch('/api/assign', {
						method: 'POST',
						headers: { 'Content-Type': 'application/json' },
						body: JSON.stringify({ callUuid, agentId: agent.id })
					});
					
					if (response.ok) {
						console.log(`Assigned call ${callUuid} to agent ${agent.id}`);
					} else {
						console.error('Failed to assign call');
					}
				} catch (error) {
					console.error('Error assigning call:', error);
				}
			}
		}
	}
	
	function handleDragOver(event: DragEvent) {
		event.preventDefault();
		isDragOver = true;
	}
	
	function handleDragLeave() {
		isDragOver = false;
	}
</script>

<div
	class="bg-white rounded-lg shadow-md p-6 border-2 transition-all"
	class:border-green-500={isDragOver}
	class:bg-green-50={isDragOver}
	class:border-gray-200={!isDragOver && agent.status === 'available'}
	class:border-blue-500={agent.status === 'on-call'}
	class:bg-blue-50={agent.status === 'on-call'}
	on:drop={handleDrop}
	on:dragover={handleDragOver}
	on:dragleave={handleDragLeave}
>
	<div class="flex items-center justify-between">
		<div>
			<h3 class="text-lg font-semibold text-gray-900">{agent.name}</h3>
			<p class="text-sm text-gray-600">Extension: {agent.id}</p>
		</div>
		<span 
			class="text-xs px-3 py-1 rounded-full font-medium"
			class:bg-green-100={agent.status === 'online'}
			class:text-green-800={agent.status === 'online'}
			class:bg-blue-100={agent.status === 'on-call'}
			class:text-blue-800={agent.status === 'on-call'}
			class:bg-gray-100={agent.status === 'offline'}
			class:text-gray-600={agent.status === 'offline'}
		>
			{agent.status === 'on-call' ? 'On Call' : agent.status === 'online' ? 'Online' : 'Offline'}
		</span>
	</div>
	
	{#if agent.activeCall}
		<div class="mt-4 pt-4 border-t border-gray-200">
			<div class="flex items-center justify-between mb-3">
				<div class="flex-1">
					<p class="text-sm font-medium text-gray-900">📞 {agent.activeCall.caller_name}</p>
					<p class="text-xs text-gray-600">{agent.activeCall.caller_number}</p>
					{#if agent.activeCall.conference_with && agent.activeCall.conference_with.length > 0}
						<p class="text-xs text-purple-600 font-medium mt-1">
							🎙️ Conference with: {agent.activeCall.conference_with.filter(a => a !== agent.id).join(', ')}
						</p>
					{/if}
				</div>
				<div class="text-right">
					<p class="text-sm font-mono text-blue-600">{formatDuration(callDuration)}</p>
					<p class="text-xs text-gray-500">call duration</p>
				</div>
			</div>
			
			<!-- Call Control Buttons -->
			<div class="flex gap-2 flex-wrap">
				<button
					on:click={handleHold}
					class="flex-1 min-w-[70px] px-2 py-1.5 text-xs font-medium text-white bg-yellow-500 hover:bg-yellow-600 rounded transition"
					title="Put call on hold"
				>
					⏸ Hold
				</button>
				
				<button
					on:click={handleResume}
					class="flex-1 min-w-[70px] px-2 py-1.5 text-xs font-medium text-white bg-green-500 hover:bg-green-600 rounded transition"
					title="Resume call"
				>
					▶ Resume
				</button>
				
				<div class="relative flex-1 min-w-[70px]">
					<button
						on:click={() => showTransferMenu = !showTransferMenu}
						class="w-full px-2 py-1.5 text-xs font-medium text-white bg-blue-500 hover:bg-blue-600 rounded transition"
						title="Transfer call"
					>
						⇄ Transfer
					</button>
					
					{#if showTransferMenu}
						<div class="absolute bottom-full mb-1 left-0 bg-white border border-gray-300 rounded shadow-lg z-10 min-w-[120px]">
							<button
								on:click={() => { handleTransfer('1000'); showTransferMenu = false; }}
								class="block w-full text-left px-3 py-2 text-xs hover:bg-gray-100"
								disabled={agent.id === '1000'}
							>
								→ Agent 1000
							</button>
							<button
								on:click={() => { handleTransfer('1001'); showTransferMenu = false; }}
								class="block w-full text-left px-3 py-2 text-xs hover:bg-gray-100"
								disabled={agent.id === '1001'}
							>
								→ Agent 1001
							</button>
							<button
								on:click={() => { handleTransfer('1002'); showTransferMenu = false; }}
								class="block w-full text-left px-3 py-2 text-xs hover:bg-gray-100"
								disabled={agent.id === '1002'}
							>
								→ Agent 1002
							</button>
						</div>
					{/if}
				</div>
				
				<div class="relative flex-1 min-w-[70px]">
					<button
						on:click={() => showConferenceMenu = !showConferenceMenu}
						class="w-full px-2 py-1.5 text-xs font-medium text-white bg-purple-500 hover:bg-purple-600 rounded transition"
						title="Add agent to conference"
					>
						👥 Add
					</button>
					
					{#if showConferenceMenu}
						<div class="absolute bottom-full mb-1 left-0 bg-white border border-gray-300 rounded shadow-lg z-10 min-w-[120px]">
							<button
								on:click={() => { handleConference('1000'); showConferenceMenu = false; }}
								class="block w-full text-left px-3 py-2 text-xs hover:bg-gray-100"
								disabled={agent.id === '1000'}
							>
								+ Agent 1000
							</button>
							<button
								on:click={() => { handleConference('1001'); showConferenceMenu = false; }}
								class="block w-full text-left px-3 py-2 text-xs hover:bg-gray-100"
								disabled={agent.id === '1001'}
							>
								+ Agent 1001
							</button>
							<button
								on:click={() => { handleConference('1002'); showConferenceMenu = false; }}
								class="block w-full text-left px-3 py-2 text-xs hover:bg-gray-100"
								disabled={agent.id === '1002'}
							>
								+ Agent 1002
							</button>
						</div>
					{/if}
				</div>
				
				<button
					on:click={handleHangup}
					class="flex-1 min-w-[70px] px-2 py-1.5 text-xs font-medium text-white bg-red-500 hover:bg-red-600 rounded transition"
					title="End call"
				>
					✖ End
				</button>
			</div>
		</div>
	{:else if isDragOver}
		<div class="mt-4 text-sm text-green-600 font-medium">
			Drop to assign call →
		</div>
	{/if}
</div>
