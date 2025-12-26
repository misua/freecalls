<script lang="ts">
	import { Doughnut } from 'svelte-chartjs';
	import { Chart as ChartJS, ArcElement, Tooltip, Legend } from 'chart.js';

	ChartJS.register(ArcElement, Tooltip, Legend);

	export let summary: {
		completed_calls: number;
		abandoned_calls: number;
		total_calls: number;
	};

	$: chartData = {
		labels: ['Completed', 'Abandoned', 'Missed'],
		datasets: [
			{
				data: [
					summary.completed_calls,
					summary.abandoned_calls,
					summary.total_calls - summary.completed_calls - summary.abandoned_calls
				],
				backgroundColor: [
					'rgba(34, 197, 94, 0.8)',
					'rgba(251, 146, 60, 0.8)',
					'rgba(239, 68, 68, 0.8)'
				],
				borderColor: ['rgb(34, 197, 94)', 'rgb(251, 146, 60)', 'rgb(239, 68, 68)'],
				borderWidth: 2
			}
		]
	};

	const options = {
		responsive: true,
		maintainAspectRatio: false,
		plugins: {
			legend: {
				position: 'bottom' as const
			},
			title: {
				display: true,
				text: 'Call Status Distribution'
			},
			tooltip: {
				callbacks: {
					label: (context: any) => {
						const label = context.label || '';
						const value = context.parsed || 0;
						const total = summary.total_calls;
						const percentage = total > 0 ? ((value / total) * 100).toFixed(1) : '0.0';
						return `${label}: ${value} (${percentage}%)`;
					}
				}
			}
		}
	};
</script>

<div class="bg-white rounded-lg shadow p-6">
	<div class="h-80 flex items-center justify-center">
		<Doughnut data={chartData} {options} />
	</div>
</div>
