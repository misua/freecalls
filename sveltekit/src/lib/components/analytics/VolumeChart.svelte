<script lang="ts">
	import { Line } from 'svelte-chartjs';
	import {
		Chart as ChartJS,
		CategoryScale,
		LinearScale,
		PointElement,
		LineElement,
		Title,
		Tooltip,
		Legend,
		Filler
	} from 'chart.js';

	// Register Chart.js components
	ChartJS.register(
		CategoryScale,
		LinearScale,
		PointElement,
		LineElement,
		Title,
		Tooltip,
		Legend,
		Filler
	);

	export let volumeData: Array<{
		timestamp: string;
		total: number;
		completed: number;
		abandoned: number;
	}> = [];

	$: chartData = {
		labels: volumeData.map((d) => {
			const date = new Date(d.timestamp);
			return date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
		}),
		datasets: [
			{
				label: 'Total Calls',
				data: volumeData.map((d) => d.total),
				borderColor: 'rgb(59, 130, 246)',
				backgroundColor: 'rgba(59, 130, 246, 0.1)',
				fill: true,
				tension: 0.4
			},
			{
				label: 'Completed',
				data: volumeData.map((d) => d.completed),
				borderColor: 'rgb(34, 197, 94)',
				backgroundColor: 'rgba(34, 197, 94, 0.1)',
				fill: false,
				tension: 0.4
			},
			{
				label: 'Abandoned',
				data: volumeData.map((d) => d.abandoned),
				borderColor: 'rgb(251, 146, 60)',
				backgroundColor: 'rgba(251, 146, 60, 0.1)',
				fill: false,
				tension: 0.4
			}
		]
	};

	const options = {
		responsive: true,
		maintainAspectRatio: false,
		plugins: {
			legend: {
				position: 'top' as const
			},
			title: {
				display: true,
				text: 'Call Volume Over Time'
			},
			tooltip: {
				mode: 'index' as const,
				intersect: false
			}
		},
		scales: {
			y: {
				beginAtZero: true,
				ticks: {
					precision: 0
				}
			}
		}
	};
</script>

<div class="bg-white rounded-lg shadow p-6">
	<div class="h-80">
		<Line data={chartData} {options} />
	</div>
</div>
