<script lang="ts">
	import { onMount } from 'svelte';
	import MetricsCards from '$lib/components/analytics/MetricsCards.svelte';
	import VolumeChart from '$lib/components/analytics/VolumeChart.svelte';
	import AgentPerformanceChart from '$lib/components/analytics/AgentPerformanceChart.svelte';
	import CallStatusChart from '$lib/components/analytics/CallStatusChart.svelte';
	import RecentCallsTable from '$lib/components/analytics/RecentCallsTable.svelte';

	// Date range state
	let dateRange = 'today';
	let customFrom = '';
	let customTo = '';

	// Data state
	let summary = {
		total_calls: 0,
		avg_duration: 0,
		avg_wait_time: 0,
		abandon_rate: 0,
		completed_calls: 0,
		abandoned_calls: 0
	};

	let volumeData: any[] = [];
	let agentData: any[] = [];
	let recentCalls: any[] = [];

	let loading = true;
	let error = '';

	// Calculate date range
	function getDateRange() {
		const now = new Date();
		let from: Date;
		let to = new Date(); // Don't reuse now - create fresh instance

		switch (dateRange) {
			case 'today':
				from = new Date();
				from.setHours(0, 0, 0, 0);
				break;
			case 'yesterday':
				from = new Date();
				from.setDate(from.getDate() - 1);
				from.setHours(0, 0, 0, 0);
				to = new Date(from);
				to.setHours(23, 59, 59, 999);
				break;
			case 'week':
				from = new Date();
				from.setDate(from.getDate() - 7);
				break;
			case 'month':
				from = new Date();
				from.setDate(from.getDate() - 30);
				break;
			case 'custom':
				if (!customFrom || !customTo) {
					from = new Date();
					from.setHours(0, 0, 0, 0);
				} else {
					from = new Date(customFrom);
					to = new Date(customTo);
				}
				break;
			default:
				from = new Date();
				from.setHours(0, 0, 0, 0);
		}

		return {
			from: from.toISOString(),
			to: to.toISOString()
		};
	}

	// Fetch analytics data
	async function fetchAnalytics() {
		loading = true;
		error = '';

		try {
			const { from, to } = getDateRange();
			const interval = dateRange === 'today' || dateRange === 'yesterday' ? 'hour' : 'day';

			// Fetch all data in parallel
			const [summaryRes, volumeRes, agentsRes, recentRes] = await Promise.all([
				fetch(`/api/analytics/summary?from=${from}&to=${to}`),
				fetch(`/api/analytics/volume?from=${from}&to=${to}&interval=${interval}`),
				fetch(`/api/analytics/agents?from=${from}&to=${to}&limit=10`),
				fetch(`/api/analytics/recent?limit=20`)
			]);

			if (!summaryRes.ok || !volumeRes.ok || !agentsRes.ok || !recentRes.ok) {
				throw new Error('Failed to fetch analytics data');
			}

			const summaryData = await summaryRes.json();
			const volumeResult = await volumeRes.json();
			const agentsResult = await agentsRes.json();
			const recentResult = await recentRes.json();

			if (summaryData.success) {
				summary = summaryData.data;
			}

			if (volumeResult.success) {
				volumeData = volumeResult.data.volume;
			}

			if (agentsResult.success) {
				agentData = agentsResult.data.agents;
			}

			if (recentResult.success) {
				recentCalls = recentResult.data.calls;
			}

			loading = false;
		} catch (err) {
			console.error('Analytics fetch error:', err);
			error = err instanceof Error ? err.message : 'Failed to load analytics';
			loading = false;
		}
	}

	// Refresh button handler
	function handleRefresh() {
		fetchAnalytics();
	}

	// Auto-refresh every 30 seconds
	onMount(() => {
		fetchAnalytics();

		const interval = setInterval(() => {
			fetchAnalytics();
		}, 30000);

		return () => clearInterval(interval);
	});

	// Re-fetch when date range changes
	$: if (dateRange || customFrom || customTo) {
		fetchAnalytics();
	}
</script>

<svelte:head>
	<title>Analytics Dashboard - FreeCalls</title>
</svelte:head>

<div class="min-h-screen bg-gray-100 p-6">
	<!-- Header -->
	<div class="mb-6 flex items-center justify-between">
		<div>
			<h1 class="text-3xl font-bold text-gray-900">Analytics Dashboard</h1>
			<p class="text-sm text-gray-500 mt-1">Real-time call center performance metrics</p>
		</div>

		<div class="flex items-center gap-4">
			<!-- Date Range Selector -->
			<select
				bind:value={dateRange}
				class="px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
			>
				<option value="today">Today</option>
				<option value="yesterday">Yesterday</option>
				<option value="week">Last 7 Days</option>
				<option value="month">Last 30 Days</option>
				<option value="custom">Custom Range</option>
			</select>

			<!-- Custom Date Inputs -->
			{#if dateRange === 'custom'}
				<input
					type="date"
					bind:value={customFrom}
					class="px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
				/>
				<input
					type="date"
					bind:value={customTo}
					class="px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
				/>
			{/if}

			<!-- Refresh Button -->
			<button
				on:click={handleRefresh}
				class="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
			>
				<svg
					class="w-5 h-5"
					fill="none"
					stroke="currentColor"
					viewBox="0 0 24 24"
				>
					<path
						stroke-linecap="round"
						stroke-linejoin="round"
						stroke-width="2"
						d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
					/>
				</svg>
			</button>

			<!-- Back to Dashboard -->
			<a
				href="/"
				class="px-4 py-2 bg-gray-600 text-white rounded-lg hover:bg-gray-700 transition-colors"
			>
				← Back
			</a>
		</div>
	</div>

	{#if error}
		<div class="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded mb-6">
			{error}
		</div>
	{/if}

	{#if loading}
		<div class="flex items-center justify-center h-64">
			<div class="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
		</div>
	{:else}
		<!-- Metrics Cards -->
		<MetricsCards {summary} />

		<!-- Charts Grid -->
		<div class="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
			<VolumeChart {volumeData} />
			<AgentPerformanceChart {agentData} />
		</div>

		<div class="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-6">
			<div class="lg:col-span-1">
				<CallStatusChart {summary} />
			</div>
			<div class="lg:col-span-2">
				<!-- Placeholder for additional chart or info -->
				<div class="bg-white rounded-lg shadow p-6 h-full">
					<h3 class="text-lg font-semibold text-gray-900 mb-4">Quick Stats</h3>
					<div class="space-y-4">
						<div class="flex justify-between">
							<span class="text-gray-600">Handled Calls:</span>
							<span class="font-semibold">{summary.completed_calls}</span>
						</div>
						<div class="flex justify-between">
							<span class="text-gray-600">Abandoned:</span>
							<span class="font-semibold text-orange-600">{summary.abandoned_calls}</span>
						</div>
						<div class="flex justify-between">
							<span class="text-gray-600">Active Agents:</span>
							<span class="font-semibold">{agentData.length}</span>
						</div>
					</div>
				</div>
			</div>
		</div>

		<!-- Recent Calls Table -->
		<RecentCallsTable calls={recentCalls} />
	{/if}
</div>

<style>
	:global(body) {
		margin: 0;
		padding: 0;
	}
</style>
