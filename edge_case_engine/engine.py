class EdgeCaseEngine:

    def __init__(self):

        pass

    def generate(self, handlers):

        all_cases = []

        for handler in handlers:

            cases = handler.generate_edge_cases()

            all_cases.extend(cases)

        return all_cases