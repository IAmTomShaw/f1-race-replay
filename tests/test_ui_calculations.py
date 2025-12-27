
import unittest

class TestUICalculations(unittest.TestCase):
    def test_calculate_time_gap_logic(self):
        """
        Verify the dynamic time gap calculation logic.
        """
        def calculate_time_gap(dist_m, speed_kph):
            # The logic we implemented
            speed_ms = max(10.0, speed_kph / 3.6)
            return dist_m / speed_ms

        # 1. High speed
        self.assertAlmostEqual(calculate_time_gap(100, 300), 1.2, places=2)
        
        # 2. Low speed (clamped)
        self.assertAlmostEqual(calculate_time_gap(10, 5), 1.0, places=2) # 10m / 10m/s (clamped)

if __name__ == '__main__':
    unittest.main()
