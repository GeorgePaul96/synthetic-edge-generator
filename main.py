from edge_case_engine.engine import EdgeCaseEngine
from edge_case_engine.executor import FunctionExecutor

from type_handlers.float_handler import FloatHandler

from examples.example_functions import divide


def main():

    engine = EdgeCaseEngine()

    handlers = [
        FloatHandler(),
        FloatHandler()
    ]

    test_cases = engine.generate(handlers)

    executor = FunctionExecutor(divide)

    crashes = executor.execute(test_cases)

    print(f"\nTotal crashes found: {len(crashes)}")


if __name__ == "__main__":
    main()