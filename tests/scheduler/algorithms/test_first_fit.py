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
from wca.scheduler.algorithms.first_fit import FirstFit
from wca.scheduler.types import ExtenderArgs
from tests.scheduler.algorithms.simulator import Simulator
from tests.scheduler.algorithms.node import Node


def test():
    simulator = Simulator(
        tasks=[],
        nodes=[Node.create_apache_pass(), Node.create_standard()],
        algorithm=FirstFit()
    )

    extender_args = ExtenderArgs(
            Nodes={


                },
            Pod={

                },
            NodeNames={

                }
            )

    simulator.run(extender_args)
