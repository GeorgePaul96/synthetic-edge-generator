import random


def derive_child(rng: random.Random) -> random.Random:
    """Deterministically derive a child RNG by drawing a 64-bit seed from the parent.

    Because traversal order is fixed, the master seed alone determines every value.
    """
    return random.Random(rng.getrandbits(64))
