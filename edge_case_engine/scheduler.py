import random
from typing import List, Dict, Any, Tuple

class PowerScheduler:
    """
    Implements coverage-guided seed prioritization.
    Assigns 'energy' to corpus entries based on execution speed and path rarity.
    """
    def __init__(self):
        # Maps coverage IDs (path signatures) to global hit counts
        self.global_edge_frequencies: Dict[str, int] = {}

    def update_frequencies(self, coverage_id: str) -> None:
        """Tracks how often a specific execution path is hit."""
        self.global_edge_frequencies[coverage_id] = self.global_edge_frequencies.get(coverage_id, 0) + 1

    def calculate_energy(self, exec_time_ms: float, coverage_id: str) -> float:
        """
        Calculates the energy score of a seed.
        Energy = Base * SpeedMultiplier * RarityMultiplier
        """
        base_energy = 100.0

        # 1. Speed Multiplier: Penalize slow inputs to maximize iterations/sec
        safe_exec_time = max(exec_time_ms, 0.001)
        speed_multiplier = min(1.0, 1.0 / safe_exec_time)

        # 2. Rarity Multiplier: Reward inputs that hit rare execution paths
        freq = self.global_edge_frequencies.get(coverage_id, 1)
        rarity_score = 1.0 / freq
        
        # Scale the rarity score appropriately
        energy = base_energy * speed_multiplier * (rarity_score * 10)
        
        # Ensure every seed retains a minimum baseline chance of selection
        return max(1.0, round(energy, 2))

    def choose_next_seed(self, interesting_inputs: List[Dict[str, Any]]) -> Tuple[Any, float]:
        """
        Selects the next seed using Roulette Wheel Selection (weighted by energy).
        Returns the input tuple and its energy score.
        """
        if not interesting_inputs:
            return None, 1.0

        energies = [entry.get("energy", 1.0) for entry in interesting_inputs]
        
        # O(N) selection based on dynamic weights
        selected = random.choices(interesting_inputs, weights=energies, k=1)[0]
        return selected["input"], selected.get("energy", 1.0)

    def determine_mutation_stack_depth(self, energy: float) -> int:
        """
        Havoc Mode: Determines how many mutations to stack sequentially.
        High energy seeds get aggressively mutated.
        """
        # Base of 1 mutation, up to 16 stacked mutations for high energy seeds
        max_mutations = min(16, max(1, int(energy / 10)))
        return random.randint(1, max_mutations)