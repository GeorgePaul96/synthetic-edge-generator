from edge_case_engine.combinatorial import CombinatorialGenerator
from edge_case_engine.mutation import MutationEngine


class EdgeCaseEngine:

    def __init__(self):

        self.combinatorial = CombinatorialGenerator()
        self.mutation = MutationEngine()

    def generate(self, handlers):

        handler_cases = []

        for handler in handlers:

            cases = handler.generate_edge_cases()
            handler_cases.append(cases)

        combinations = self.combinatorial.generate(handler_cases)

        mutations = self.mutation.mutate(combinations)

        all_cases = combinations + mutations

        # Deduplicate
        unique_cases = list(set(all_cases))

        return unique_cases