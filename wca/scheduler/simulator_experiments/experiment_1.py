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
import logging
from logging import DEBUG

from wca.logger import TRACE
from wca.scheduler.algorithms.bar import BAR
from wca.scheduler.algorithms.fit import Fit
from wca.scheduler.algorithms.hierbar import HierBAR
from wca.scheduler.algorithms.least_used import LeastUsed
from wca.scheduler.algorithms.least_used_bar import LeastUsedBAR
from wca.scheduler.algorithms.nop_algorithm import NOPAlgorithm
from wca.scheduler.algorithms.static_assigner import StaticAssigner
from wca.scheduler.simulator_experiments.generic_experiment import experiments_iterator
from wca.scheduler.simulator_experiments.nodes_generators import prepare_nodes
from wca.scheduler.simulator_experiments.nodesets import (
    NODES_DEFINITIONS_2TYPES, NODES_DEFINITIONS_3TYPES)
from wca.scheduler.simulator_experiments.task_generators import TaskGeneratorEqual, \
    TaskGeneratorClasses
from wca.scheduler.simulator_experiments.tasksets import TASK_DEFINITIONS__ARTIFICIAL_2, \
    taskset_dimensions
from wca.scheduler.simulator_experiments.tasksets import TASK_DEFINITIONS__ARTIFICIAL_3TYPES
from wca.scheduler.types import WSS, MEM, CPU, MEMBW_WRITE, MEMBW_READ, MEMBW

x = DEBUG, TRACE  # to not be auto removed during import cleanup

log = logging.getLogger(__name__)

DIM5 = {CPU, MEM, MEMBW_READ, MEMBW_WRITE, WSS}
DIM4 = {CPU, MEM, MEMBW_READ, MEMBW_WRITE}
DIM2 = {CPU, MEM}


def experiment_debug():
    task_scale = 1
    cluster_scale = 1
    nodes_dimensions = DIM4
    experiments_iterator(
        'debug',
        [30 * task_scale],
        [
            (TaskGeneratorEqual,
             dict(task_definitions=TASK_DEFINITIONS__ARTIFICIAL_3TYPES, replicas=10 * task_scale)),
        ],
        [
            prepare_nodes(NODES_DEFINITIONS_2TYPES,
                          dict(aep=2 * cluster_scale, dram=6 * cluster_scale),
                          nodes_dimensions, ),
        ],
        [
            (LeastUsedBAR, dict(alias='BAR__LU_OFF', dimensions=DIM4, least_used_weight=0)),
        ],
    )


def experiment_bar():
    task_scale = 1
    cluster_scale = 1
    nodes_dimensions = DIM4

    experiments_iterator(
        'bar_weights',
        [30 * task_scale, ],
        [
            (TaskGeneratorClasses, dict(task_definitions=taskset_dimensions(nodes_dimensions,
                                                                            TASK_DEFINITIONS__ARTIFICIAL_2),
                                        counts=dict(mbw=20 * task_scale, cpu=5 * task_scale,
                                                    mem=5 * task_scale))),
        ],
        [
            prepare_nodes(NODES_DEFINITIONS_2TYPES,
                          dict(aep=2 * cluster_scale, dram=6 * cluster_scale), nodes_dimensions),
        ],
        [
            (LeastUsedBAR,
             dict(alias='BAR__LU_ON__WEIGHTS_UNEQUAL', dimensions=DIM4, least_used_weight=1,
                  bar_weights={MEM: 0.5})),
            (LeastUsedBAR,
             dict(alias='BAR__LU_ON__WEIGHTS_EQUAL', dimensions=DIM4, least_used_weight=1)),
            (LeastUsedBAR,
             dict(alias='BAR__LU_ON__WEIGHTS_100x', dimensions=DIM4, least_used_weight=100)),
            (LeastUsedBAR, dict(alias='BAR__LU_OFF', dimensions=DIM4, least_used_weight=0)),
        ],
    )


def experiment_full(task_scale=1, cluster_scale=1):
    nodes_dimensions = DIM4
    experiments_iterator(
        'intel_demo_local',
        [30 * task_scale],
        [
            (TaskGeneratorEqual,
             dict(task_definitions=TASK_DEFINITIONS__ARTIFICIAL_3TYPES, replicas=10 * task_scale)),
            (TaskGeneratorClasses, dict(task_definitions=TASK_DEFINITIONS__ARTIFICIAL_3TYPES,
                                        counts=dict(mbw=3 * task_scale, cpu=12 * task_scale,
                                                    mem=15 * task_scale))),
            (TaskGeneratorClasses, dict(task_definitions=TASK_DEFINITIONS__ARTIFICIAL_3TYPES,
                                        counts=dict(mbw=20 * task_scale, cpu=5 * task_scale,
                                                    mem=5 * task_scale))),
            (TaskGeneratorClasses, dict(task_definitions=TASK_DEFINITIONS__ARTIFICIAL_3TYPES,
                                        counts=dict(mbw=30 * task_scale, cpu=0 * task_scale,
                                                    mem=0 * task_scale))),
            (TaskGeneratorClasses, dict(task_definitions=TASK_DEFINITIONS__ARTIFICIAL_3TYPES,
                                        counts=dict(mbw=0 * task_scale, cpu=0 * task_scale,
                                                    mem=30 * task_scale))),
        ],
        [
            prepare_nodes(NODES_DEFINITIONS_2TYPES, dict(aep=0, dram=6 * cluster_scale),
                          nodes_dimensions),
            prepare_nodes(NODES_DEFINITIONS_2TYPES,
                          dict(aep=2 * cluster_scale, dram=6 * cluster_scale), nodes_dimensions),
            prepare_nodes(NODES_DEFINITIONS_2TYPES, dict(aep=0, dram=8 * cluster_scale),
                          nodes_dimensions),
            prepare_nodes(NODES_DEFINITIONS_2TYPES, dict(aep=cluster_scale, dram=cluster_scale),
                          nodes_dimensions, ),
        ],
        [
            (NOPAlgorithm, {}),
            (Fit, dict(dimensions=DIM2)),
            (Fit, dict(dimensions=DIM4)),
            (LeastUsed, dict(dimensions=DIM2)),
            (LeastUsed, dict(dimensions=DIM4)),
            (BAR, dict(dimensions=DIM2)),
            (HierBAR, dict(dimensions=DIM2)),
            (LeastUsedBAR,
             dict(alias='kubernetes_baseline', dimensions={CPU, MEM})),
            (LeastUsedBAR, dict(alias='BAR__LU_OFF', dimensions=DIM4, least_used_weight=0)),
            (LeastUsedBAR,
             dict(alias='BAR__LU_ON__WEIGHTS_EQUAL', dimensions=DIM4, least_used_weight=1)),
            (LeastUsedBAR,
             dict(alias='BAR__LU_ON__WEIGHTS_UNEQUAL', dimensions=DIM4, least_used_weight=1,
                  bar_weights={MEM: 0.5})),
        ],
    )


def experiment_static_assigner():
    nodes_dimensions = DIM4
    targeted_assigned_apps_counts = \
        {'aep_0': {CPU: 1, MEM: 2, MEMBW: 2},
         'dram_0': {CPU: 1, MEM: 0, MEMBW: 0}}

    experiments_iterator(
        'static_assigner',
        [6],
        [
            (TaskGeneratorClasses,
             dict(task_definitions=taskset_dimensions(nodes_dimensions,
                                                      TASK_DEFINITIONS__ARTIFICIAL_2),
                  counts=dict(mbw=2, cpu=2, mem=2))),
        ],
        [
            prepare_nodes(NODES_DEFINITIONS_2TYPES,
                          dict(aep=1, dram=1),
                          nodes_dimensions,
                          ),
        ],
        [
            (StaticAssigner,
             dict(alias='StaticAssigner',
                  targeted_assigned_apps_counts=targeted_assigned_apps_counts)),
        ],
    )


def experiment_hierbar():
    nodes_dimensions = DIM4
    iterations = 60
    experiments_iterator(
        'hierbar',
        [iterations],
        [
            (TaskGeneratorEqual,
             dict(task_definitions=TASK_DEFINITIONS__ARTIFICIAL_3TYPES, replicas=10)),
            (TaskGeneratorClasses, dict(task_definitions=taskset_dimensions(nodes_dimensions,
                                                                            TASK_DEFINITIONS__ARTIFICIAL_3TYPES),
                                        counts=dict(mem=30))),  # AEP
            (TaskGeneratorClasses, dict(task_definitions=taskset_dimensions(nodes_dimensions,
                                                                            TASK_DEFINITIONS__ARTIFICIAL_3TYPES),
                                        counts=dict(mbw=30))),  # no AEP
            (TaskGeneratorClasses, dict(task_definitions=taskset_dimensions(nodes_dimensions,
                                                                            TASK_DEFINITIONS__ARTIFICIAL_3TYPES),
                                        counts=dict(cpu=5, mem=5, mbw=20))),
            (TaskGeneratorClasses, dict(task_definitions=taskset_dimensions(nodes_dimensions,
                                                                            TASK_DEFINITIONS__ARTIFICIAL_3TYPES),
                                        counts=dict(cpu=5, mem=20, mbw=5))),
        ],
        [
            prepare_nodes(NODES_DEFINITIONS_3TYPES, dict(aep=2, sml=4, big=2), nodes_dimensions)
        ],
        [
            (LeastUsedBAR, dict(dimensions=DIM2, alias='native')),
            (HierBAR, dict(dimensions=nodes_dimensions)),
            (HierBAR, dict(dimensions=nodes_dimensions, merge_threshold=1, alias='extender')),
        ],
    )


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.WARN, format='%(levelname)s:%(module)s:%(funcName)s:%(lineno)d %(message)s')
    logging.getLogger('wca.algorithms').setLevel(logging.INFO)
    # logging.getLogger('wca.scheduler.cluster_simulator').setLevel(logging.DEBUG)
    experiment_bar()
    experiment_hierbar()
    experiment_debug()
    experiment_static_assigner()
    # experiment_full() # takes about 30 seconds
