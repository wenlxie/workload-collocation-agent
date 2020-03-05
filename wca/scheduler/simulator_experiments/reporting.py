# Copyright (c) 2020 Intel Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import datetime
import itertools
import logging
import os
import statistics
from collections import Counter, defaultdict
from functools import partial, reduce
from typing import Dict, List

from dataclasses import dataclass

from wca.scheduler.algorithms.base import query_data_provider, sum_resources
from wca.scheduler.cluster_simulator import Resources, Node, ClusterSimulator, Task
from wca.scheduler.types import ResourceType as ResourceType, NodeName, AppName

log = logging.getLogger(__name__)


class AssignmentsCounts:
    def __init__(self, tasks: List[Task], nodes: List[Node]):
        per_node: Dict[NodeName, Counter]
        per_cluster: Counter
        unassigned: Counter

        # represents sum of all other siblings in the tree
        ALL = '__ALL__'

        # 1) assignments per node per app
        per_node: Dict[NodeName, Counter[AppName]] = {}
        for node in nodes:
            per_node[node.name] = Counter(Counter({ALL: 0}))
            for task in tasks:
                if task.assignment == node:
                    app_name = task.get_core_name()
                    per_node[node.name].update([app_name])
                    per_node[node.name].update([ALL])
        assert sum([leaf for node_assig in per_node.values()
                    for _, leaf in node_assig.items()]) == len(
            [task for task in tasks if task.assignment is not None]) * 2

        # 2) assignments per app (for the whole cluster)
        per_cluster: Counter[AppName] = Counter({ALL: 0})
        # 3) unassigned apps
        unassigned: Counter[AppName] = Counter({ALL: 0})
        for task in tasks:
            app_name = task.get_core_name()
            if task.assignment is not None:
                per_cluster.update([app_name])
                per_cluster.update([ALL])
            else:
                unassigned.update([app_name])
                unassigned.update([ALL])
        assert sum(per_cluster.values()) + sum(unassigned.values()) == len(tasks) * 2

        self.per_node = per_node
        self.per_cluster = per_cluster
        self.unassigned = unassigned


@dataclass
class IterationData:
    cluster_resource_usage: Resources
    per_node_resource_usage: Dict[Node, Resources]
    broken_assignments: Dict[Node, int]
    assignments_counts: AssignmentsCounts
    tasks_types_count: Dict[str, int]
    metrics: Dict[str, List[float]]


def get_total_capacity_and_demand(
        nodes_capacities, assigned_apps_counts, unassigend_apps_count, apps_spec):
    """ Sum of total cluster capacity and sum of all requirements of all scheduled tasks"""
    total_capacity = reduce(sum_resources, nodes_capacities.values())
    total_apps_count = defaultdict(int)
    for apps_count in list(assigned_apps_counts.values()) + [unassigend_apps_count]:
        for app, count in apps_count.items():
            total_apps_count[app] += count

    total_demand = defaultdict(int)
    for app, count in total_apps_count.items():
        app_spec = apps_spec[app]
        for res, value in app_spec.items():
            total_demand[res] += value * count
    total_demand = dict(total_demand)
    return total_capacity, total_demand, total_apps_count


def generate_subexperiment_report(
        exp_name: str,
        exp_dir: str,
        subtitle: str,
        iterations_data: List[IterationData],
        task_gen,
        algorithm,
        charts,
        extra_charts
) -> dict:
    extra_metrics = algorithm.get_metrics_names()
    iterations = [0 for _ in range(len(iterations_data))]
    cpu_usage = [iter_.cluster_resource_usage.data[ResourceType.CPU] for iter_ in iterations_data]
    mem_usage = [iter_.cluster_resource_usage.data[ResourceType.MEM] for iter_ in iterations_data]

    if ResourceType.MEMBW_READ in iterations_data[0].cluster_resource_usage.data:
        membw_usage = [iter_.cluster_resource_usage.data[ResourceType.MEMBW_READ]
                       for iter_ in iterations_data]
    else:
        membw_usage = [iter_.cluster_resource_usage.data[ResourceType.MEMBW] for iter_ in
                       iterations_data]

    # ------------------ Text report -----------------------

    with open('{}/{}.txt'.format(exp_dir, subtitle), 'w') as fref:
        # Total demand and total capacity based from data from scheduler
        nodes_capacities, assigned_apps_counts, apps_spec, unassigend_apps_count = \
            query_data_provider(algorithm.data_provider, algorithm.dimensions)

        total_capacity, total_demand, total_apps_count = \
            get_total_capacity_and_demand(nodes_capacities, assigned_apps_counts,
                                          unassigend_apps_count, apps_spec)
        fref.write('Total capacity: %s\n' % total_capacity)
        fref.write('Total demand: %s\n' % total_demand)
        ideal_utilization = {}  # for each resource
        for r in total_demand:
            if r in total_capacity:
                ideal_utilization[r] = total_demand[r] / total_capacity[r]
        fref.write('Ideal possible utilization %%: %s\n' % ideal_utilization)

        total_tasks_dict = dict(iterations_data[-1].tasks_types_count)
        fref.write("Scheduled tasks (might not be successfully assigned): {}\n"
                   .format(total_tasks_dict))
        # Check consistency of iterations data and data provider.
        if total_apps_count != total_tasks_dict:
            fref.write(
                "!Scheduled tasks different from total_apps_count from query! total_apps_count={}\n"
                    .format(dict(total_apps_count)))
            assert False, 'should not happen!'

        scheduled_tasks = sum(total_tasks_dict.values())
        assignments_counts = iterations_data[-1].assignments_counts
        fref.write("Unassigned tasks: {}\n".format(dict(assignments_counts.unassigned)))
        broken_assignments = sum(iterations_data[-1].broken_assignments.values())
        fref.write("Broken assignments: {}\n".format(broken_assignments))

        total_nodes = len(assignments_counts.per_node.keys())
        node_names = assignments_counts.per_node.keys()
        nodes_info = ','.join('%s=%d' % (node_type, len(list(nodes))) for node_type, nodes
                              in itertools.groupby(sorted(node_names), lambda x: x.split('_')[0]))
        fref.write(
            "\nAssigned tasks per cluster: {}\n".format(dict(assignments_counts.per_cluster)))

        assigned_tasks = dict(assignments_counts.per_cluster)['__ALL__']

        fref.write("Assigned tasks per node:\n")
        for node, counters in assignments_counts.per_node.items():
            fref.write("   {}: {}\n".format(node, ' '.join(
                '%s=%d' % (k, v) for k, v in sorted(dict(counters).items()) if k != '__ALL__')))

        rounded_last_iter_resources = \
            map(partial(round, ndigits=2), (cpu_usage[-1], mem_usage[-1], membw_usage[-1],))
        cpu_util, mem_util, bw_util = rounded_last_iter_resources
        fref.write("\nresource_usage(cpu, mem, membw_flat) = ({}, {}, {})\n".format(
            cpu_util, mem_util, bw_util))
        nodes_avg_var = []
        nodes_utilization = []
        nodes_utilization_avg = []
        for node, usages in iterations_data[-1].per_node_resource_usage.items():
            rounded_last_iter_resources = map(
                partial(round, ndigits=2),
                (usages.data[ResourceType.CPU], usages.data[ResourceType.MEM],
                 usages.data[ResourceType.MEMBW_READ],))
            fref.write(
                "  {}: = ({}, {}, {})\n".format(
                    node.name, *rounded_last_iter_resources))
            nodes_utilization.extend(
                [usages.data[ResourceType.CPU], usages.data[ResourceType.MEM],
                 usages.data[ResourceType.MEMBW_READ]])
            nodes_utilization_avg.append(
                (usages.data[ResourceType.CPU] + usages.data[ResourceType.MEM] + usages.data[
                    ResourceType.MEMBW_READ]) / 3)
            nodes_avg_var.append(statistics.variance(
                [usages.data[ResourceType.CPU], usages.data[ResourceType.MEM],
                 usages.data[ResourceType.MEMBW_READ]]))

        util_var = statistics.variance(nodes_utilization)

        available_metrics = {m.split('{')[0] for iterdata in iterations_data for m in
                             iterdata.metrics}
        fref.write("\n\nAvailable metrics: {}\n".format(', '.join(sorted(available_metrics))))
        fref.write("Start of experiment: {}\n".format(
            datetime.datetime.strftime(datetime.datetime.now(), '%Y%m%d_%H%M')))
        fref.write("Iterations: {}\n".format(len(iterations_data)))

    # ----------------------- Stats --------------------------------------

    stats = {}
    stats['TASKS'] = str(task_gen)  # sum(total_tasks_dict.values())
    stats['NODES'] = '%s(%s)' % (total_nodes, nodes_info)
    stats['ALGO'] = str(algorithm)
    stats['balance'] = 1 - util_var
    stats['cpu_util%'] = cpu_util * 100
    stats['mem_util%'] = mem_util * 100
    stats['bw_util%'] = bw_util * 100

    if any('aep' in node.name for node, _ in iterations_data[-1].per_node_resource_usage.items()):
        stats['cpu_util(AEP)%'] = 100 * statistics.mean(
            resources.data[ResourceType.CPU] for node, resources in
            iterations_data[-1].per_node_resource_usage.items() if 'aep' in node.name)
        stats['mem_util(AEP)%'] = 100 * statistics.mean(
            resources.data[ResourceType.MEM] for node, resources in
            iterations_data[-1].per_node_resource_usage.items() if 'aep' in node.name)
        stats['bw_util(AEP)%'] = 100 * statistics.mean(
            resources.data[ResourceType.MEMBW_READ] for node, resources in
            iterations_data[-1].per_node_resource_usage.items() if 'aep' in node.name)
    else:
        stats['cpu_util(AEP)%'] = float('nan')
        stats['mem_util(AEP)%'] = float('nan')
        stats['bw_util(AEP)%'] = float('nan')

    stats['scheduled'] = scheduled_tasks
    stats['assigned%'] = int((assigned_tasks / scheduled_tasks) * 100)
    stats['assigned_broken%'] = int((broken_assignments / scheduled_tasks) * 100)
    stats['utilization%'] = int(((cpu_util + mem_util + bw_util) / 3) * 100)

    # Chart report

    if charts:
        generate_charts(cpu_usage, exp_dir,
                        extra_metrics if extra_charts else None,
                        iterations,
                        iterations_data, mem_usage,
                        membw_usage, subtitle, exp_name)

    return stats


def generate_charts(cpu_usage, exp_dir, extra_metrics, iterations, iterations_data, mem_usage,
                    membw_usage, subtitle, title):
    """Generate charts if optional libraries are available!"""
    try:
        import matplotlib.pyplot as plt
        import seaborn as sns
        import pandas as pd
        import numpy as np
    except ImportError:
        # No installed packages required for report generation.
        log.warning(
            'matplotlib, seaborn, pandas or numpy not installed, charts will not be generated!')
        exit(1)
    extra_metrics = extra_metrics or []
    plt.style.use('ggplot')
    number_of_metrics = len(extra_metrics)
    fig, axs = plt.subplots(2 + number_of_metrics)
    fig.set_size_inches(20, 20 + 6 * number_of_metrics)
    axs[0].plot(iterations, cpu_usage, 'r--')
    axs[0].plot(iterations, mem_usage, 'b--')
    axs[0].plot(iterations, membw_usage, 'g--')
    axs[0].legend(['cpu usage', 'mem usage', 'membw usage'])
    # ---
    axs[0].set_title('{} {}'.format(title, subtitle), fontsize=10)
    # ---
    axs[0].set_xlim(iterations.min(), iterations.max())
    axs[0].set_ylim(0, 1)
    broken_assignments = \
        np.array([sum(list(iter_.broken_assignments.values())) for iter_ in iterations_data])
    axs[1].plot(iterations, broken_assignments, 'g--')
    axs[1].legend(['broken assignments'])
    axs[1].set_ylabel('')
    axs[1].set_xlim(iterations.min(), iterations.max())
    axs[1].set_ylim(broken_assignments.min() - 1, broken_assignments.max() + 1)
    # Visualize metrics
    for pidx, filter in enumerate(extra_metrics):
        dicts = []
        for iteration, idata in enumerate(iterations_data):
            d = {k.split('{')[1][:-1]: v
                 for k, v in idata.metrics.items() if k.startswith(filter)}
            if not d:
                log.warning('metric %s not found: available: %s', filter,
                            ', '.join([m.split('{')[0] for m in idata.metrics.keys()]))
            dicts.append(d)

        from matplotlib.markers import MarkerStyle
        df = pd.DataFrame(dicts)
        try:
            x = sns.lineplot(data=df,
                             markers=MarkerStyle.filled_markers,
                             dashes=False,
                             ax=axs[2 + pidx])
        except ValueError:
            x = sns.lineplot(data=df,
                             dashes=False,
                             ax=axs[2 + pidx])
        x.set_title(filter)
        x.set_xlim(iterations.min(), iterations.max())

    fig.savefig('{}/{}.png'.format(exp_dir, subtitle))


def generate_experiment_report(stats_dicts, exp_dir):
    try:
        import pandas as pd
    except ImportError:
        # No installed packages required for report generation.
        print('numpy and matplotlib are required!')
        exit(1)
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', 200)
    df = pd.DataFrame(stats_dicts)
    output = df.to_string(formatters={
        'balance': '{:,.2f}'.format,
        'assigned_broken%': '{:,.0f}%'.format,
        'assigned%': '{:,.0f}%'.format,
        'cpu_util(AEP)%': '{:,.0f}%'.format,
        'mem_util(AEP)%': '{:,.0f}%'.format,
        'bw_util(AEP)%': '{:,.0f}%'.format,
        'cpu_util%': '{:,.0f}%'.format,
        'mem_util%': '{:,.0f}%'.format,
        'bw_util%': '{:,.0f}%'.format,
        'scheduled': '{:,.0f}'.format,
        'util_var_avg': '{:,.0%}'.format,
        'util_avg_var': '{:,.0%}'.format,
        'util_var': '{:,.0%}'.format,
        'utilization%': '{:,.0f}%'.format,
    })
    print(output)
    df.reset_index()

    def p(val, aggr):
        _pivot_ui(
            df,
            totals=True,
            row_totals=False,
            rows=['TASKS', 'NODES'],
            cols=['ALGO'],
            vals=[val], aggregatorName=aggr,
            rendererName='Heatmap',
            outfile_path=os.path.join(exp_dir, 'summary_%s.html' % val.replace('%', '')),
            rendererOptions=dict(
                rowTotals=False,
                colTotals=False,
            )
        )

    p('utilization%', 'Average')
    p('balance', 'Average')
    p('broken%', 'Average')


def wrapper_iteration_finished_callback(iterations_data: List[IterationData]):
    def iteration_finished_callback(iteration: int, simulator: ClusterSimulator):
        per_node_resource_usage = simulator.per_node_resource_usage(True)
        cluster_resource_usage = simulator.cluster_resource_usage(True)
        broken_assignments = simulator.rough_assignments_per_node.copy()
        assignments_counts = AssignmentsCounts(simulator.tasks, simulator.nodes)
        tasks_types_count = Counter([task.get_core_name() for task in simulator.tasks])

        metrics_registry = simulator.algorithm.get_metrics_registry()
        if metrics_registry is not None:
            metrics = metrics_registry.as_dict()
        else:
            metrics = {}

        iterations_data.append(IterationData(
            cluster_resource_usage, per_node_resource_usage,
            broken_assignments, assignments_counts, tasks_types_count,
            metrics=metrics,
        ))

    return iteration_finished_callback


def _pivot_ui(df, totals=True, row_totals=True, **options):
    """ Interactive pivot table for data analysis.
    # Example options:
    rows=['x', 'y'),
    cols=['z, 'v'),
    vals=['percentile/99th',],
    aggregatorName='First',
    rendererName='Heatmap'
    """
    try:
        from pivottablejs import pivot_ui
    except ImportError:
        log.warning("Error: cannot import pivottablejs, Pivottable will not be generated'!")
        return
    iframe = pivot_ui(df, **options)
    if not totals:
        with open(iframe.src) as f:
            replaced_html = f.read().replace(
                '</style>', '.pvtTotal, .pvtTotalLabel, .pvtGrandTotal {display: none}</style>')
        with open(iframe.src, "w") as f:
            f.write(replaced_html)
    if not row_totals:
        with open(iframe.src) as f:
            replaced_html = f.read().replace(
                '</style>', '.rowTotal, .pvtRowTotalLabel, .pvtGrandTotal {display: none}</style>')
        with open(iframe.src, "w") as f:
            f.write(replaced_html)
    return iframe
