"""
Test suite for Race Incidents & Overtakes Tracker feature

Run with: python -m pytest tests/test_incidents.py -v
"""

import pytest
import numpy as np
from src.incident_detection import Incident, IncidentDetector


class TestIncident:
    """Test Incident data class"""
    
    def test_incident_creation(self):
        """Test basic incident object creation"""
        incident = Incident(
            frame_number=100,
            time_seconds=50.5,
            lap_number=5,
            incident_type='overtake',
            primary_driver='VER',
            secondary_driver='LEC',
            description='Position gain'
        )
        assert incident.frame_number == 100
        assert incident.primary_driver == 'VER'
        assert incident.secondary_driver == 'LEC'
        assert 'VER' in str(incident)
        assert 'LEC' in str(incident)
    
    def test_incident_without_secondary_driver(self):
        """Test incident with only primary driver (e.g., pit stop)"""
        incident = Incident(
            frame_number=200,
            time_seconds=100.0,
            lap_number=10,
            incident_type='pit_stop',
            primary_driver='HAM',
            description='Pit stop'
        )
        assert incident.secondary_driver is None
        assert 'HAM' in str(incident)
        assert 'pit_stop' in str(incident).lower()


class TestIncidentDetector:
    """Test IncidentDetector functionality"""
    
    def create_mock_frames(self, num_frames=50):
        """Create mock frame data for testing"""
        frames = []
        drivers = ['VER', 'LEC', 'SAI', 'HAM']
        
        for frame_idx in range(num_frames):
            driver_positions = {}
            # Simulate VER and LEC getting closer (overtake setup)
            if frame_idx < 20:
                # LEC ahead
                driver_positions['LEC'] = (100, 100, 5, 0.5)
                driver_positions['VER'] = (95, 95, 5, 0.0)
            else:
                # VER gains position
                driver_positions['VER'] = (105, 105, 5, 1.0)
                driver_positions['LEC'] = (98, 98, 5, 0.5)
            
            driver_positions['SAI'] = (80, 80, 4, 0.0)
            driver_positions['HAM'] = (70, 70, 4, 0.0)
            
            frame = {
                'frame_number': frame_idx,
                'time_seconds': float(frame_idx),
                'drivers': {code: {'x': x, 'y': y, 'lap': lap, 'dist': gap} 
                           for code, (x, y, lap, gap) in driver_positions.items()},
                'driver_positions': driver_positions,
                'driver_speeds': {code: 250.0 + np.sin(frame_idx / 10) * 50 for code in drivers}
            }
            frames.append(frame)
        
        return frames, drivers
    
    def test_detector_initialization(self):
        """Test incident detector can be initialized"""
        frames, drivers = self.create_mock_frames(20)
        detector = IncidentDetector(frames, drivers)
        assert detector.frames == frames
        assert detector.incidents == []
    
    def test_detect_all_incidents(self):
        """Test incident detection runs without error"""
        frames, drivers = self.create_mock_frames(50)
        detector = IncidentDetector(frames, drivers)
        incidents = detector.detect_all_incidents()
        
        # Should return a list
        assert isinstance(incidents, list)
        # Should be sorted by frame number
        if len(incidents) > 1:
            for i in range(len(incidents) - 1):
                assert incidents[i].frame_number <= incidents[i + 1].frame_number
    
    def test_get_incidents_for_driver(self):
        """Test filtering incidents by driver"""
        frames, drivers = self.create_mock_frames(50)
        detector = IncidentDetector(frames, drivers)
        detector.detect_all_incidents()
        
        # Get incidents for specific driver
        ver_incidents = detector.get_incidents_for_driver('VER')
        assert isinstance(ver_incidents, list)
        
        # All incidents should involve VER
        for incident in ver_incidents:
            assert incident.primary_driver == 'VER' or incident.secondary_driver == 'VER'
    
    def test_get_incidents_by_type(self):
        """Test filtering incidents by type"""
        frames, drivers = self.create_mock_frames(100)
        detector = IncidentDetector(frames, drivers)
        detector.detect_all_incidents()
        
        # Get incidents of specific type
        overtakes = detector.get_incidents_by_type('overtake')
        pit_stops = detector.get_incidents_by_type('pit_stop')
        
        assert isinstance(overtakes, list)
        assert isinstance(pit_stops, list)
        
        # All filtered incidents should match type
        for incident in overtakes:
            assert incident.incident_type == 'overtake'
        for incident in pit_stops:
            assert incident.incident_type == 'pit_stop'
    
    def test_pit_stop_detection(self):
        """Test pit stop detection from speed drop"""
        frames = []
        # Create frames with a sudden speed drop
        for i in range(50):
            frame = {
                'frame_number': i,
                'time_seconds': float(i),
                'drivers': {'VER': {'x': 100 + i, 'y': 100, 'lap': 10, 'dist': 1000}},
                'driver_positions': {'VER': (100 + i, 100, 10, 0.0)},
                'driver_speeds': {'VER': 300.0 if i < 20 else max(0.0, 300.0 - (i - 20) * 15)}
            }
            frames.append(frame)
        
        detector = IncidentDetector(frames, ['VER'])
        incidents = detector.detect_all_incidents()
        
        # Should detect pit stop from speed drop
        pit_stops = [i for i in incidents if i.incident_type == 'pit_stop']
        assert len(pit_stops) > 0
    
    def test_incident_deduplication(self):
        """Test that duplicate incidents aren't recorded"""
        frames, drivers = self.create_mock_frames(100)
        detector = IncidentDetector(frames, drivers)
        incidents = detector.detect_all_incidents()
        
        # Check no duplicate pit stops for same driver in close time
        pit_stops = [i for i in incidents if i.incident_type == 'pit_stop']
        for i, pit1 in enumerate(pit_stops):
            for pit2 in pit_stops[i + 1:]:
                if pit1.primary_driver == pit2.primary_driver:
                    # Different incidents should be > 5 seconds apart
                    assert abs(pit1.time_seconds - pit2.time_seconds) >= 5.0


class TestIncidentsPanelComponent:
    """Test incidents UI component"""
    
    def test_panel_initialization(self):
        """Test panel can be created"""
        from src.ui_components_incidents import IncidentsPanelComponent
        panel = IncidentsPanelComponent(left=20, top=600)
        assert panel.visible == True
        assert panel.filtered_incidents == []
    
    def test_set_incidents(self):
        """Test setting incidents on panel"""
        from src.ui_components_incidents import IncidentsPanelComponent
        panel = IncidentsPanelComponent()
        
        incidents = [
            Incident(0, 0.0, 1, 'overtake', 'VER', 'LEC', 'Test'),
            Incident(100, 50.0, 5, 'pit_stop', 'HAM'),
        ]
        
        panel.set_incidents(incidents)
        assert len(panel.filtered_incidents) == 2
    
    def test_incident_filtering(self):
        """Test incident type filtering"""
        from src.ui_components_incidents import IncidentsPanelComponent
        panel = IncidentsPanelComponent()
        
        incidents = [
            Incident(0, 0.0, 1, 'overtake', 'VER', 'LEC'),
            Incident(100, 50.0, 5, 'pit_stop', 'HAM'),
            Incident(200, 100.0, 10, 'overtake', 'SAI', 'RUS'),
        ]
        
        panel.set_incidents(incidents)
        assert len(panel.filtered_incidents) == 3
        
        # Filter to overtakes only
        panel.filter_type = 'overtake'
        panel.filter_incidents()
        assert len(panel.filtered_incidents) == 2
        
        # All filtered should be overtakes
        for incident in panel.filtered_incidents:
            assert incident.incident_type == 'overtake'
    
    def test_incident_navigation(self):
        """Test selecting next/previous incidents"""
        from src.ui_components_incidents import IncidentsPanelComponent
        panel = IncidentsPanelComponent()
        
        incidents = [
            Incident(10, 5.0, 1, 'overtake', 'VER', 'LEC'),
            Incident(100, 50.0, 5, 'overtake', 'SAI', 'RUS'),
            Incident(200, 100.0, 10, 'overtake', 'ALO', 'STR'),
        ]
        
        panel.set_incidents(incidents)
        
        # Should return frame numbers
        frame = panel.select_next_incident()
        assert frame == 10
        
        frame = panel.select_next_incident()
        assert frame == 100
        
        frame = panel.select_prev_incident()
        assert frame == 10
    
    def test_panel_visibility_toggle(self):
        """Test toggling panel visibility"""
        from src.ui_components_incidents import IncidentsPanelComponent
        panel = IncidentsPanelComponent(visible=True)
        assert panel.visible == True
        
        panel.toggle_visibility()
        assert panel.visible == False
        
        panel.toggle_visibility()
        assert panel.visible == True


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
