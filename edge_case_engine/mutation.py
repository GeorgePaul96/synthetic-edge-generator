import random


class MutationEngine:

    def mutate(self, test_cases):
        """Applies a single mutation to a batch of test cases (Baseline)."""
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

    def havoc_mutate(self, test_cases, stack_depth=1):
        """
        Havoc Mode: Applies multiple sequential mutations to the same input.
        High energy seeds receive a higher stack_depth from the scheduler.
        """
        mutations = []

        for case in test_cases[:50]:
            
            case = list(case)
            
            # Apply N mutations sequentially to the same input
            for _ in range(stack_depth):
                
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
                
                # Overwrite the value at the chosen index
                case[index] = random.choice(mutation_options)

            # Append the heavily mutated case
            mutations.append(tuple(case))

        return mutations