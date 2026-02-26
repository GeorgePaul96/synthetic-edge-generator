class FunctionExecutor:

    def __init__(self, function):

        self.function = function

        self.crashes = []

    def execute(self, test_cases):

        print(f"\nTesting function: {self.function.__name__}\n")

        for case in test_cases:

            try:

                self.function(*case)

            except Exception as e:

                crash = {
                    "input": case,
                    "error": type(e).__name__,
                    "message": str(e)
                }

                self.crashes.append(crash)

                print("Crash found!")
                print(f"Input: {case}")
                print(f"Error: {type(e).__name__}")
                print()

        print("Testing complete.")

        return self.crashes