import random


class MutationEngine:

    def mutate(self, test_cases):

        mutations = []

        for case in test_cases[:50]:

            case = list(case)

            index = random.randint(0, len(case) - 1)

            mutation_options = [
                None,
                "string",
                float("inf"),
                float("nan"),
                0,
                -1,
                1e308
            ]

            case[index] = random.choice(mutation_options)

            mutations.append(tuple(case))

        return mutations