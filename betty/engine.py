import time

from betty.configs import EngineConfig
from betty.logging import logger
from betty.utils import log_from_loss_dict


class Engine:
    def __init__(self, config, problems, dependencies=None):
        # config
        self.config = config if config is not None else EngineConfig()
        self.train_iters = 0
        self.valid_step = 0
        self.global_step = 0

        # logger
        self.logger_type = None
        self.logger = None

        # problem
        self.problems = problems
        self._problem_name_dict = {}
        self.leaves = []

        # dependencies
        self.dependencies = dependencies

        # initialize
        self.initialize()

    def parse_config(self):
        """
        Parse EngineConfig.
        """
        self.train_iters = self.config.train_iters
        self.valid_step = self.config.valid_step
        self.logger_type = self.config.logger_type

    def train_step(self):
        for leaf in self.leaves:
            leaf.step(global_step=self.global_step)

    def run(self):
        """
        Execute multilevel optimization by running gradient descent for leaf problems.
        """
        self.train()
        for it in range(1, self.train_iters + 1):
            self.global_step += 1
            self.train_step()

            if it % self.valid_step == 0:
                if self.is_implemented('validation'):
                    self.eval()
                    validation_stats = self.validation() or {}
                    log_loss = log_from_loss_dict(validation_stats)
                    self.logger.info(
                        f'[Validation] [Global Step {self.global_step}] '
                        f'{log_loss}'
                    )
                    self.logger.log(validation_stats, tag='validation', step=self.global_step)
                    self.train()

    def initialize(self):
        """
        Initialize dependencies (computational graph) between problems.
        """
        # Parse config
        self.parse_config()
        self.logger = logger(logger_type=self.logger_type)
        self.logger.info('Initializing Multilevel Optimization...\n')
        start = time.time()

        # Parse dependency
        self.parse_dependency()

        # check & set multiplier for each problem
        for problem in self.problems:
            problem.add_logger(self.logger)
            problem.initialize()

        end = time.time()
        self.logger.info(f'Time spent on initialization: {end-start:.3f} (s)\n')

    def train(self):
        """
        Set invovled problems to train mode.
        """
        for problem in self.problems:
            problem.train()

    def eval(self):
        """
        Set involved problems to eval mode.
        """
        for problem in self.problems:
            problem.eval()

    def check_leaf(self, problem):
        """
        Check whether the given ``problem`` is a leaf problem or not.
        """
        for _, value_list in self.dependencies['l2u'].items():
            if problem in set(value_list):
                return False

        return True

    def find_paths(self, src, dst):
        results = []
        path = [src]
        self.dfs(src, dst, path, results)
        assert len(results) > 0, f'No path from {src.name} to {dst.name}!'

        for i, _ in enumerate(results):
            results[i].reverse()
            results[i].append(dst)

        return results

    def dfs(self, src, dst, path, results):
        if src is dst:
            assert len(path) > 1
            result = [node for node in path]
            results.append(result)
        else:
            for adj in self.dependencies['l2u'][src]:
                path.append(adj)
                self.dfs(adj, dst, path, results)
                path.pop()

    def parse_dependency(self, set_attr=True):
        """
        Parse user-provided ``u2l`` and ``l2u`` dependencies to figure out 1) topological order for
        multilevel optimization execution, and 2) backpropagation path(s) for each problem. A
        modified depth-first search algorithm is used.
        """
        # Parse upper-to-lower dependency
        for key, value_list in self.dependencies['u2l'].items():
            for value in value_list:
                # set the problelm attribute for key problem in value problem
                if set_attr:
                    value.set_problem_attr(key)

                # find all paths from low to high for backpropagation
                paths = self.find_paths(src=value, dst=key)
                key.add_paths(paths)

        # Parse lower-to-upper dependency
        for key, value_list in self.dependencies['l2u'].items():
            for value in value_list:
                # set the problelm attribute for key problem in value problem
                if set_attr:
                    value.set_problem_attr(key)

                # add value problem to parents of key problem for backpropgation
                key.add_parent(value)
                value.add_child(key)

        # Parse problems
        for problem in self.problems:
            if set_attr:
                self.set_problem_attr(problem)
            if self.check_leaf(problem):
                problem.leaf = True
                self.leaves.append(problem)

    def set_dependency(self, dependencies, set_attr=False):
        self.dependencies = dependencies
        self.leaves = []

        # clear existing dependencies
        for problem in self.problems:
            problem.leaf = False
            problem.clear_dependencies()

        self.parse_dependency(set_attr=set_attr)

    def set_problem_attr(self, problem):
        """
        Set class attribute for the given ``problem`` based on their names
        """
        name = problem.name
        if name not in self._problem_name_dict:
            assert not hasattr(self, name), f'Problem already has an attribute named {name}!'
            self._problem_name_dict[name] = 0
            setattr(self, name, problem)
        elif self._problem_name_dict[name] == 0:
            # rename first problem
            first_problem = getattr(self, name)
            delattr(self, name)
            setattr(self, name + '_0', first_problem)

            self._problem_name_dict[name] += 1
            name = name + '_' + str(self._problem_name_dict[name])
            setattr(self, name, problem)
        else:
            self._problem_name_dict[name] += 1
            name = name + '_' + str(self._problem_name_dict[name])
            setattr(self, name, problem)

        return name

    def is_implemented(self, fn_name):
        """
        Check whether ``fn_name`` method is implemented in the class.
        """
        return callable(getattr(self, fn_name, None))
