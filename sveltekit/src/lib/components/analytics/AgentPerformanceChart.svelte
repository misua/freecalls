<script lang="ts">
	import { Bar } from 'svelte-chartjs';
	import {
		Chart as ChartJS,
		CategoryScale,
		LinearScale,
		BarElement,
		Title,
		Tooltip,
		Legend
	} from 'chart.js';

	ChartJS.register(CategoryScale, LinearScale, BarElement, Title, Tooltip, Legend);

	export let agentData: Array<{
		agent_id: string;
		calls_handled: number;
		avg_duration: number;
		completion_rate: string;
	}> = [];

	$: chartData = {
		labels: agentData.map((d) => d.agent_id),
		datasets: [
			{
				label: 'Calls Handled',
				data: agentData.map((d) => d.calls_handled),
				backgroundColor: 'rgba(59, 130, 246, 0.8)',
				borderColor: 'rgb(59, 130, 246)',
				borderWidth: 1
			}
		]
	};

	const options = {
		indexAxis: 'y' as const,
		responsive: true,
		maintainAspectRatio: false,
		plugins: {
			legend: {
				display: false
			},
			title: {
				display: true,
				text: 'Top Agents by Calls Handled'
			},
			tooltip: {
				callbacks: {
					afterLabel: (context: any) => {
						const index = context.dataIndex;
						const agent = agentData[index];
						return [
							`Avg Duration: ${Math.floor(agent.avg_duration / 60)}m ${agent.avg_duration % 60}s`,
							`Completion Rate: ${agent.completion_rate}%`
						];
					}
				}
			}
		},
		scales: {
			x: {
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
		<Bar data={chartData} {options} />
	</div>
</div>
