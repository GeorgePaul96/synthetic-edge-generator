import sys


class FloatHandler:

    def generate_edge_cases(self):

        return [
            0.0,
            -0.0,
            float("inf"),
            float("-inf"),
            float("nan"),
            sys.float_info.max,
            sys.float_info.min
        ]