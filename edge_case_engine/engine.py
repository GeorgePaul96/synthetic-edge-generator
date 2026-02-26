from edge_case_engine.combinatorial import CombinatorialGenerator


class EdgeCaseEngine:

    def __init__(self):

        self.combinatorial = CombinatorialGenerator()

    def generate(self, handlers):

        handler_cases = []

        for handler in handlers:

            cases = handler.generate_edge_cases()

            handler_cases.append(cases)

        combinations = self.combinatorial.generate(handler_cases)

        return combinations