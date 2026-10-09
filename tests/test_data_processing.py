
import unittest
import numpy as np
import pandas as pd

class TestDataProcessing(unittest.TestCase):
    
    def test_distance_accumulation(self):
        """
        Verify race distance accumulates correctly across laps.
        """
        # Logic mirroring src/f1_data.py fix
        laps_data = [
            # Lap 1: 0-100m
            {"d": np.array([0.0, 100.0])},
            # Lap 2: 0-100m (should become 100-200m)
            {"d": np.array([0.0, 100.0])}
        ]
        
        race_dist_all = []
        total_dist_so_far = 0.0
        
        for lap in laps_data:
            d_lap = lap["d"]
            race_d_lap = total_dist_so_far + d_lap
            race_dist_all.append(race_d_lap)
            if len(d_lap) > 0:
                total_dist_so_far += d_lap[-1]
                
        result = np.concatenate(race_dist_all)
        expected = np.array([0.0, 100.0, 100.0, 200.0])
        
        np.testing.assert_array_equal(result, expected)

    def test_generic_deduplication(self):
        """
        Verify the deduplication logic used for telemetry.
        """
        t_all = np.array([1.0, 10.0, 10.0, 20.0])
        lap_vals = np.array([1, 1, 2, 2]) # 10.0 has duplicate: Lap 1 and Lap 2
        
        # Logic from src/f1_data.py
        t_rev = t_all[::-1]
        _, uniq_idx_rev = np.unique(t_rev, return_index=True)
        keep_idxs = len(t_all) - 1 - uniq_idx_rev
        keep_idxs.sort()
        
        t_final = t_all[keep_idxs]
        laps_final = lap_vals[keep_idxs]
        
        # Should keep indices: 0 (1.0), 2 (10.0 Lap 2), 3 (20.0)
        # Should drop index 1 (10.0 Lap 1)
        
        expected_laps = np.array([1, 2, 2])
        np.testing.assert_array_equal(laps_final, expected_laps)

if __name__ == '__main__':
    unittest.main()
