<script lang="ts">
	import CallCard from '$lib/components/CallCard.svelte';
	import AgentCard from '$lib/components/AgentCard.svelte';
	import ConferenceCard from '$lib/components/ConferenceCard.svelte';
	import { onMount } from 'svelte';
	
	export let data;
	
	let calls = data.calls;
	let agents = data.agents;
	let managers = data.managers;
	let conferences: Array<{
		room: string;
		caller_number: string;
		caller_name: string;
		agents: string[];
		started_at: number;
	}> = [];
	
	// Connect to SSE for real-time updates
	onMount(() => {
		const eventSource = new EventSource('/api/call-events');
		
		eventSource.onmessage = (event) => {
			const update = JSON.parse(event.data);
			
			if (update.event === 'call_parked') {
				// Add new call to list with parsed timestamp
				calls = [...calls, {
					...update.data,
					parked_at: parseInt(update.data.parked_at || '0')
				}];
			} else if (update.event === 'call_ended') {
				// Remove call from list
				calls = calls.filter(c => c.uuid !== update.data.uuid);
			} else if (update.event === 'call_bridged') {
				// Remove call from parked list
				calls = calls.filter(c => c.uuid !== update.data.uuid);
				
				// Update agent status to on-call
				agents = agents.map(a => 
					a.id === update.data.agent_id 
						? { 
							...a, 
							status: 'on-call',
							activeCall: {
								call_uuid: update.data.uuid,
								caller_number: update.data.caller_number,
								caller_name: update.data.caller_name,
								bridged_at: update.data.bridged_at
							}
						}
						: a
				);
			} else if (update.event === 'agent_available') {
				// Clear agent active call
				agents = agents.map(a =>
					a.id === update.data.agent_id
						? { ...a, status: 'available', activeCall: null }
						: a
				);
				
				// Also clear for managers
				managers = managers.map(m =>
					m.id === update.data.agent_id
						? { ...m, status: 'available', activeCall: null }
						: m
				);
				
				// Remove any conferences involving this agent
				conferences = conferences.filter(c => !c.agents.includes(update.data.agent_id));
			} else if (update.event === 'user_registered') {
				// User/agent registered - update to online status
				const userId = update.data.user_id;
				agents = agents.map(a =>
					a.id === userId
						? { ...a, status: a.activeCall ? 'on-call' : 'online' }
						: a
				);
				
				// Also update managers
				managers = managers.map(m =>
					m.id === userId
						? { ...m, status: m.activeCall ? 'on-call' : 'online' }
						: m
				);
			} else if (update.event === 'user_unregistered') {
				// User/agent unregistered - update to offline status
				const userId = update.data.user_id;
				agents = agents.map(a =>
					a.id === userId
						? { ...a, status: 'offline', activeCall: null }
						: a
				);
				
				// Also update managers
				managers = managers.map(m =>
					m.id === userId
						? { ...m, status: 'offline', activeCall: null }
						: m
				);
			} else if (update.type === 'conference_created') {
				// Add new conference to the list
				conferences = [...conferences, {
					room: update.room,
					caller_number: update.caller,
					caller_name: update.caller,
					agents: update.agents || [],
					started_at: Math.floor(Date.now() / 1000)
				}];
				
				// Update both agents to show conference info
				const conferenceAgents = update.agents || [];
				agents = agents.map(a => {
					if (conferenceAgents.includes(a.id) && a.activeCall) {
						return {
							...a,
							activeCall: {
								...a.activeCall,
								conference_with: conferenceAgents,
								conference_room: update.room
							}
						};
					}
					return a;
				});
			}
		};
		
		return () => {
			eventSource.close();
		};
	});
</script>

<div class="min-h-screen bg-gray-100 p-8">
	<div class="max-w-7xl mx-auto">
		<div class="flex items-center justify-between mb-8">
			<h1 class="text-3xl font-bold text-gray-900">FreeCalls Dashboard</h1>
			
			<!-- Analytics Link -->
			<a 
				href="/dashboard/analytics"
				class="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
			>
				<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
					<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
				</svg>
				Analytics
			</a>
		</div>
		
		<!-- Active Conferences Section (Full Width) -->
		{#if conferences.length > 0}
			<div class="mb-8">
				<h2 class="text-xl font-semibold text-gray-700 mb-4">
					🎙️ Active Conferences ({conferences.length})
				</h2>
				<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
					{#each conferences as conference (conference.room)}
						<ConferenceCard {conference} {managers} />
					{/each}
				</div>
			</div>
		{/if}
		
		<div class="grid grid-cols-2 gap-8">
			<!-- Parked Calls Column -->
			<div>
				<h2 class="text-xl font-semibold text-gray-700 mb-4">
					Parked Calls ({calls.length})
				</h2>
				
				<div class="space-y-4">
					{#if calls.length === 0}
						<div class="bg-white rounded-lg shadow p-6 text-center text-gray-500">
							No calls waiting. Call extension 5000 to test.
						</div>
					{/if}
					
					{#each calls as call (call.uuid)}
						<CallCard {call} />
					{/each}
				</div>
			</div>
			
			<!-- Agents Column -->
			<div>
				<h2 class="text-xl font-semibold text-gray-700 mb-4">
					Agents ({agents.length})
				</h2>
				
				<div class="space-y-4">
					{#each agents as agent (agent.id)}
						<AgentCard {agent} />
					{/each}
				</div>
			</div>
		</div>
		
		<!-- Managers Section -->
		<div class="mt-8">
			<h2 class="text-xl font-semibold text-gray-700 mb-4">
				👔 Managers ({managers.length})
			</h2>
			<div class="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-4">
				{#each managers as manager (manager.id)}
					<div class="bg-white rounded-lg shadow p-4 border-2 {manager.status === 'on-call' ? 'border-blue-400' : manager.status === 'online' ? 'border-gray-200' : 'border-gray-300 opacity-60'}">
						<div class="text-center">
							<p class="text-lg font-bold text-gray-900">{manager.id}</p>
							<p class="text-xs text-gray-600 mb-2">{manager.name}</p>
							<span class="inline-block px-2 py-1 rounded-full text-xs font-medium {manager.status === 'on-call' ? 'bg-blue-100 text-blue-800' : manager.status === 'online' ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-600'}">
								{manager.status === 'on-call' ? 'On Call' : manager.status === 'online' ? 'Online' : 'Offline'}
							</span>
						</div>
					</div>
				{/each}
			</div>
		</div>
	</div>
</div>
