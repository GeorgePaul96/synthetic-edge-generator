from edge_case_engine.engine import EdgeCaseEngine

from type_handlers.integer_handler import IntegerHandler
from type_handlers.float_handler import FloatHandler
from type_handlers.string_handler import StringHandler


def main():

    engine = EdgeCaseEngine()

    handlers = [
        FloatHandler(),
        FloatHandler()
    ]

    edge_cases = engine.generate(handlers)

    print("\nGenerated edge cases:\n")

    for case in edge_cases:

        print(case)


if __name__ == "__main__":
    main()