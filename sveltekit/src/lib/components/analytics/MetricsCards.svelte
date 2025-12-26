<script lang="ts">
	export let summary: {
		total_calls: number;
		avg_duration: number;
		avg_wait_time: number;
		abandon_rate: number;
	};

	function formatDuration(seconds: number): string {
		const mins = Math.floor(seconds / 60);
		const secs = seconds % 60;
		return `${mins}m ${secs}s`;
	}
</script>

<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
	<!-- Total Calls -->
	<div class="bg-white rounded-lg shadow p-6">
		<div class="flex items-center justify-between">
			<div>
				<p class="text-sm font-medium text-gray-600">Total Calls</p>
				<p class="text-3xl font-bold text-gray-900 mt-2">{summary.total_calls}</p>
			</div>
			<div class="bg-blue-100 rounded-full p-3">
				<svg
					class="w-6 h-6 text-blue-600"
					fill="none"
					stroke="currentColor"
					viewBox="0 0 24 24"
				>
					<path
						stroke-linecap="round"
						stroke-linejoin="round"
						stroke-width="2"
						d="M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z"
					/>
				</svg>
			</div>
		</div>
	</div>

	<!-- Avg Duration -->
	<div class="bg-white rounded-lg shadow p-6">
		<div class="flex items-center justify-between">
			<div>
				<p class="text-sm font-medium text-gray-600">Avg Duration</p>
				<p class="text-3xl font-bold text-gray-900 mt-2">
					{formatDuration(summary.avg_duration)}
				</p>
			</div>
			<div class="bg-green-100 rounded-full p-3">
				<svg
					class="w-6 h-6 text-green-600"
					fill="none"
					stroke="currentColor"
					viewBox="0 0 24 24"
				>
					<path
						stroke-linecap="round"
						stroke-linejoin="round"
						stroke-width="2"
						d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"
					/>
				</svg>
			</div>
		</div>
	</div>

	<!-- Avg Wait Time -->
	<div class="bg-white rounded-lg shadow p-6">
		<div class="flex items-center justify-between">
			<div>
				<p class="text-sm font-medium text-gray-600">Avg Wait Time</p>
				<p class="text-3xl font-bold text-gray-900 mt-2">
					{formatDuration(summary.avg_wait_time)}
				</p>
			</div>
			<div class="bg-yellow-100 rounded-full p-3">
				<svg
					class="w-6 h-6 text-yellow-600"
					fill="none"
					stroke="currentColor"
					viewBox="0 0 24 24"
				>
					<path
						stroke-linecap="round"
						stroke-linejoin="round"
						stroke-width="2"
						d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
					/>
				</svg>
			</div>
		</div>
	</div>

	<!-- Abandon Rate -->
	<div class="bg-white rounded-lg shadow p-6">
		<div class="flex items-center justify-between">
			<div>
				<p class="text-sm font-medium text-gray-600">Abandon Rate</p>
				<p class="text-3xl font-bold text-gray-900 mt-2">{summary.abandon_rate}%</p>
			</div>
			<div class="bg-red-100 rounded-full p-3">
				<svg
					class="w-6 h-6 text-red-600"
					fill="none"
					stroke="currentColor"
					viewBox="0 0 24 24"
				>
					<path
						stroke-linecap="round"
						stroke-linejoin="round"
						stroke-width="2"
						d="M6 18L18 6M6 6l12 12"
					/>
				</svg>
			</div>
		</div>
	</div>
</div>
