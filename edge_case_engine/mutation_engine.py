import random
import math


class MutationEngine:

    def __init__(self):
        self.max_mutations_per_value = 5

    def mutate_number(self, value):

        mutations = []

        # Sign flip
        mutations.append(-value)

        # Add epsilon
        mutations.append(value + 1e-15)

        # Subtract epsilon
        mutations.append(value - 1e-15)

        # Scale up
        mutations.append(value * 2)

        # Scale down
        mutations.append(value / 2 if value != 0 else value)

        # Convert to special floats
        mutations.append(float("inf"))
        mutations.append(float("-inf"))
        mutations.append(float("nan"))

        return mutations

    def mutate_case(self, case):

        mutated_cases = []

        for i, value in enumerate(case):

            if isinstance(value, (int, float)):

                mutations = self.mutate_number(value)

                for m in mutations:

                    new_case = list(case)
                    new_case[i] = m
                    mutated_cases.append(tuple(new_case))

        return mutated_cases

    def mutate_cases(self, test_cases):

        all_mutations = []

        for case in test_cases:

            mutated = self.mutate_case(case)
            all_mutations.extend(mutated)

        return all_mutations