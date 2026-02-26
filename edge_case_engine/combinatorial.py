import itertools


class CombinatorialGenerator:

    def generate(self, handler_cases):

        combinations = list(itertools.product(*handler_cases))

        return combinations