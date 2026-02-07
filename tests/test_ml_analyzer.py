"""
Tests for ML Sleep Analyzer

Tests clustering, trend analysis, and recommendation generation.
"""

import unittest
from datetime import datetime, timedelta
import numpy as np
from firmware.processing.ml_analyzer import (
    SleepMLAnalyzer,
    NightlySummary,
    SleepQuality,
    format_analysis_report
)


class TestSleepMLAnalyzer(unittest.TestCase):
    """Test suite for ML sleep analysis"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.analyzer = SleepMLAnalyzer()
    
    def test_empty_data(self):
        """Test analysis with empty data"""
        analysis = self.analyzer.analyze([])
        
        self.assertEqual(len(analysis.nights), 0)
        self.assertEqual(analysis.trend_direction, "stable")
        self.assertIn("insufficient", analysis.recommendations[0].lower())
    
    def test_single_night(self):
        """Test analysis with single night data"""
        readings = self._generate_night_data(
            datetime.now() - timedelta(days=1),
            sleep_hours=7.5,
            restlessness=20
        )
        
        analysis = self.analyzer.analyze(readings)
        
        self.assertEqual(len(analysis.nights), 1)
        self.assertIsNotNone(analysis.nights[0].sleep_quality)
        self.assertGreater(analysis.nights[0].efficiency, 0)
    
    def test_multiple_nights_clustering(self):
        """Test that clustering works with multiple nights"""
        readings = []
        base_date = datetime.now() - timedelta(days=7)
        
        # Generate 7 nights with varying quality
        for day in range(7):
            # Alternate between good and poor sleep
            sleep_hours = 8.0 if day % 2 == 0 else 5.0
            restlessness = 15 if day % 2 == 0 else 60
            
            night_readings = self._generate_night_data(
                base_date + timedelta(days=day),
                sleep_hours=sleep_hours,
                restlessness=restlessness
            )
            readings.extend(night_readings)
        
        analysis = self.analyzer.analyze(readings, n_clusters=2)
        
        # Should have 7 nights
        self.assertEqual(len(analysis.nights), 7)
        
        # All nights should have quality assigned
        for night in analysis.nights:
            self.assertIsNotNone(night.sleep_quality)
        
        # Should have recommendations
        self.assertGreater(len(analysis.recommendations), 0)
    
    def test_trend_analysis(self):
        """Test trend detection"""
        readings = []
        base_date = datetime.now() - timedelta(days=7)
        
        # Generate nights with improving quality (more sleep, less restlessness)
        for day in range(7):
            sleep_hours = 6.0 + (day * 0.3)  # Improving sleep duration
            restlessness = 50 - (day * 5)  # Decreasing restlessness
            
            night_readings = self._generate_night_data(
                base_date + timedelta(days=day),
                sleep_hours=sleep_hours,
                restlessness=restlessness
            )
            readings.extend(night_readings)
        
        analysis = self.analyzer.analyze(readings)
        
        # Trend should be improving or stable
        self.assertIn(analysis.trend_direction, ["improving", "stable"])
        self.assertIsNotNone(analysis.trend_slope)
    
    def test_recommendations_low_sleep(self):
        """Test recommendations for low sleep duration"""
        readings = []
        base_date = datetime.now() - timedelta(days=5)
        
        # Generate nights with very low sleep
        for day in range(5):
            night_readings = self._generate_night_data(
                base_date + timedelta(days=day),
                sleep_hours=5.0,  # Below recommended 7-9 hours
                restlessness=30
            )
            readings.extend(night_readings)
        
        analysis = self.analyzer.analyze(readings)
        
        # Should recommend increasing sleep duration
        recs_text = " ".join(analysis.recommendations).lower()
        self.assertTrue(
            "hours" in recs_text or "duration" in recs_text or "sleep time" in recs_text,
            f"Expected sleep duration recommendation, got: {analysis.recommendations}"
        )
    
    def test_recommendations_high_restlessness(self):
        """Test recommendations for high restlessness"""
        readings = []
        base_date = datetime.now() - timedelta(days=5)
        
        # Generate nights with high restlessness
        for day in range(5):
            night_readings = self._generate_night_data(
                base_date + timedelta(days=day),
                sleep_hours=7.0,
                restlessness=70  # High restlessness
            )
            readings.extend(night_readings)
        
        analysis = self.analyzer.analyze(readings)
        
        # Should mention restlessness or environmental factors
        recs_text = " ".join(analysis.recommendations).lower()
        self.assertTrue(
            "restless" in recs_text or "environmental" in recs_text,
            f"Expected restlessness recommendation, got: {analysis.recommendations}"
        )
    
    def test_weekend_pattern_detection(self):
        """Test weekend sleep pattern detection"""
        readings = []
        # Start from a Sunday (day 6 in Python's weekday())
        base_date = datetime(2024, 1, 7)  # Sunday
        
        # Generate 7 days with more sleep on weekends
        for day in range(7):
            is_weekend = (base_date + timedelta(days=day)).weekday() >= 5
            sleep_hours = 9.0 if is_weekend else 6.0
            
            night_readings = self._generate_night_data(
                base_date + timedelta(days=day),
                sleep_hours=sleep_hours,
                restlessness=25
            )
            readings.extend(night_readings)
        
        analysis = self.analyzer.analyze(readings)
        
        # Should detect weekend pattern
        self.assertTrue(
            analysis.insights.get("sleeps_more_on_weekends", False),
            "Should detect weekend sleep pattern"
        )
        
        # Should recommend addressing social jetlag
        recs_text = " ".join(analysis.recommendations).lower()
        self.assertTrue(
            "weekend" in recs_text or "social jetlag" in recs_text,
            f"Expected weekend recommendation, got: {analysis.recommendations}"
        )
    
    def test_insights_generation(self):
        """Test that insights are properly generated"""
        readings = []
        base_date = datetime.now() - timedelta(days=5)
        
        for day in range(5):
            night_readings = self._generate_night_data(
                base_date + timedelta(days=day),
                sleep_hours=7.0,
                restlessness=30
            )
            readings.extend(night_readings)
        
        analysis = self.analyzer.analyze(readings)
        
        # Check insights structure
        self.assertIn("consistency_score", analysis.insights)
        self.assertIn("best_night", analysis.insights)
        self.assertIn("worst_night", analysis.insights)
        
        # Consistency score should be between 0 and 100
        self.assertGreaterEqual(analysis.insights["consistency_score"], 0)
        self.assertLessEqual(analysis.insights["consistency_score"], 100)
    
    def test_format_analysis_report(self):
        """Test report formatting"""
        readings = self._generate_night_data(
            datetime.now() - timedelta(days=2),
            sleep_hours=7.0,
            restlessness=30
        )
        
        analysis = self.analyzer.analyze(readings)
        report = format_analysis_report(analysis)
        
        # Report should contain key sections
        self.assertIn("SLEEP PATTERN ANALYSIS REPORT", report)
        self.assertIn("OVERALL QUALITY", report)
        self.assertIn("RECOMMENDATIONS", report)
        self.assertIn("AVERAGE METRICS", report)
    
    def _generate_night_data(self, date: datetime, sleep_hours: float, 
                            restlessness: float) -> list:
        """Generate realistic sleep data for a single night"""
        readings = []
        
        # Sleep from 11 PM to wake time
        start_time = date.replace(hour=23, minute=0, second=0)
        wake_time = start_time + timedelta(hours=sleep_hours)
        
        current = start_time
        while current < wake_time:
            # Determine state based on time and restlessness
            hour = current.hour + current.minute / 60
            
            # Chance of movement based on restlessness (0-100)
            movement_chance = restlessness / 100
            
            if np.random.random() < movement_chance:
                state = "Tossing/Turning"
                variance = 0.08 + np.random.random() * 0.05
            else:
                state = "Asleep"
                variance = 0.02 + np.random.random() * 0.02
            
            readings.append({
                'created_at': current.isoformat(),
                'timestamp': current.isoformat(),
                'state': state,
                'variance': variance,
                'voltage': 2.5
            })
            
            current += timedelta(minutes=5)
        
        return readings


class TestNightlySummary(unittest.TestCase):
    """Test NightlySummary dataclass"""
    
    def test_nightly_summary_creation(self):
        """Test creating a NightlySummary"""
        summary = NightlySummary(
            date="2024-01-15",
            total_duration_hours=8.0,
            sleep_time_hours=7.5,
            awake_time_hours=0.5,
            movement_events=5,
            restlessness_score=25.0,
            efficiency=93.75
        )
        
        self.assertEqual(summary.date, "2024-01-15")
        self.assertEqual(summary.sleep_time_hours, 7.5)
        self.assertEqual(summary.efficiency, 93.75)


if __name__ == "__main__":
    unittest.main()
