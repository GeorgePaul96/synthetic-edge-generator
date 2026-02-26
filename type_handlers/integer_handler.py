import sys


class IntegerHandler:

    def generate_edge_cases(self):

        return [
            0,
            1,
            -1,
            sys.maxsize,
            -sys.maxsize - 1
        ]