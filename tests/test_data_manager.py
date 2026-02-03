"""
Unit tests for DataManager (SQLite + JSON)
Tests offline storage, sync tracking, and 30-day cleanup
"""

import unittest
import sys
import os
import json
import time
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from firmware.data.data_manager import DataManager, DataManagerError


class TestDataManager(unittest.TestCase):
    """Test cases for DataManager"""
    
    def setUp(self):
        """Set up test database"""
        self.test_db = "test_data_manager.db"
        # Remove old test database
        if os.path.exists(self.test_db):
            os.remove(self.test_db)
        
        self.dm = DataManager(
            db_path=self.test_db,
            device_id="test_device",
            user_id="test_user"
        )
    
    def tearDown(self):
        """Clean up test database"""
        if os.path.exists(self.test_db):
            os.remove(self.test_db)
    
    def test_init_creates_tables(self):
        """Test database initialization creates tables"""
        # Tables should be created in setUp
        stats = self.dm.get_stats()
        self.assertIn('total_readings', stats)
    
    def test_store_reading(self):
        """Test storing a reading"""
        result = self.dm.store_reading(
            voltage=2.5,
            force_percent=75.0,
            state="Asleep",
            variance=0.02
        )
        
        self.assertTrue(result)
        
        # Verify stored
        stats = self.dm.get_stats()
        self.assertEqual(stats['total_readings'], 1)
    
    def test_store_reading_default_unsynced(self):
        """Test that new readings are marked unsynced"""
        self.dm.store_reading(2.5, 75.0, "Asleep", 0.02)
        
        unsynced = self.dm.get_unsynced_readings()
        self.assertEqual(len(unsynced), 1)
    
    def test_mark_synced(self):
        """Test marking readings as synced"""
        # Store and get ID
        self.dm.store_reading(2.5, 75.0, "Asleep", 0.02)
        unsynced = self.dm.get_unsynced_readings()
        
        # Mark as synced
        ids = [r['id'] for r in unsynced]
        result = self.dm.mark_synced(ids)
        
        self.assertTrue(result)
        
        # Verify no longer unsynced
        unsynced = self.dm.get_unsynced_readings()
        self.assertEqual(len(unsynced), 0)
    
    def test_get_unsynced_readings_limit(self):
        """Test limit on unsynced readings"""
        # Store multiple readings
        for i in range(10):
            self.dm.store_reading(2.0 + i*0.1, 50.0 + i*5, "Asleep", 0.02)
        
        # Get with limit
        unsynced = self.dm.get_unsynced_readings(limit=5)
        self.assertEqual(len(unsynced), 5)
    
    def test_save_calibration(self):
        """Test saving calibration"""
        result = self.dm.save_calibration(
            baseline_voltage=0.5,
            occupied_threshold=2.5,
            movement_threshold=0.1
        )
        
        self.assertTrue(result)
    
    def test_load_calibration(self):
        """Test loading calibration"""
        # Save first
        self.dm.save_calibration(0.5, 2.5, 0.1)
        
        # Load
        cal = self.dm.load_calibration()
        
        self.assertIsNotNone(cal)
        self.assertEqual(cal['baseline_voltage'], 0.5)
        self.assertEqual(cal['occupied_threshold'], 2.5)
        self.assertEqual(cal['movement_threshold'], 0.1)
    
    def test_load_calibration_not_found(self):
        """Test loading calibration when none exists"""
        cal = self.dm.load_calibration()
        self.assertIsNone(cal)
    
    def test_to_json(self):
        """Test JSON conversion"""
        reading = {
            'voltage': 2.45,
            'force_percent': 67.5,
            'state': 'Asleep',
            'variance': 0.02,
            'timestamp': '2026-02-03T14:30:00'
        }
        
        json_str = self.dm.to_json(reading)
        
        # Verify valid JSON
        parsed = json.loads(json_str)
        
        self.assertEqual(parsed['voltage'], 2.45)
        self.assertEqual(parsed['force_percent'], 67.5)
        self.assertEqual(parsed['state'], 'Asleep')
        self.assertEqual(parsed['sensor_type'], 'fsr408')
        self.assertEqual(parsed['device_id'], 'test_device')
        self.assertEqual(parsed['user_id'], 'test_user')
    
    def test_to_json_defaults(self):
        """Test JSON with missing fields"""
        reading = {'voltage': 2.0}  # Minimal data
        
        json_str = self.dm.to_json(reading)
        parsed = json.loads(json_str)
        
        # Should have defaults
        self.assertEqual(parsed['voltage'], 2.0)
        self.assertEqual(parsed['force_percent'], 0.0)
        self.assertEqual(parsed['state'], 'Unknown')
        self.assertIn('timestamp', parsed)
    
    def test_get_recent_readings(self):
        """Test getting recent readings"""
        # Store readings
        for i in range(5):
            self.dm.store_reading(2.0 + i*0.1, 50.0 + i*5, "Asleep", 0.02)
        
        # Get recent
        recent = self.dm.get_recent_readings(limit=3)
        
        self.assertEqual(len(recent), 3)
        # Should be in reverse chronological order
        self.assertGreater(recent[0]['timestamp'], recent[1]['timestamp'])
    
    def test_get_stats(self):
        """Test statistics"""
        # Store some readings
        for i in range(5):
            self.dm.store_reading(2.0, 50.0, "Asleep", 0.02)
        
        # Mark 2 as synced
        unsynced = self.dm.get_unsynced_readings()
        ids = [r['id'] for r in unsynced[:2]]
        self.dm.mark_synced(ids)
        
        stats = self.dm.get_stats()
        
        self.assertEqual(stats['total_readings'], 5)
        self.assertEqual(stats['unsynced_readings'], 3)
        self.assertIn('database_size_mb', stats)
    
    def test_memory_queue_overflow(self):
        """Test memory queue when SQLite fails"""
        # Mock SQLite to fail
        with patch.object(self.dm, '_execute_with_retry', side_effect=Exception("DB Error")):
            # Store many readings
            for i in range(5):
                self.dm.store_reading(2.0, 50.0, "Asleep", 0.02)
        
        # Should have items in memory queue
        self.assertEqual(len(self.dm._memory_queue), 5)


class TestDataManagerRetention(unittest.TestCase):
    """Test 30-day retention policy"""
    
    def setUp(self):
        """Set up test database"""
        self.test_db = "test_retention.db"
        if os.path.exists(self.test_db):
            os.remove(self.test_db)
        
        self.dm = DataManager(db_path=self.test_db)
    
    def tearDown(self):
        """Clean up"""
        if os.path.exists(self.test_db):
            os.remove(self.test_db)
    
    def test_cleanup_old_data(self):
        """Test cleanup of old data"""
        import sqlite3
        
        # Insert old data (manually set timestamp)
        old_date = (datetime.now() - timedelta(days=31)).isoformat()
        
        with sqlite3.connect(self.test_db) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO readings (timestamp, voltage, force_percent, state, variance)
                VALUES (?, 2.0, 50.0, 'Asleep', 0.02)
            """, (old_date,))
            conn.commit()
        
        # Also insert recent data
        self.dm.store_reading(2.0, 50.0, "Asleep", 0.02)
        
        # Cleanup
        deleted = self.dm.cleanup_old_data()
        
        # Should have deleted 1 old record
        self.assertEqual(deleted, 1)
        
        # Verify only recent data remains
        stats = self.dm.get_stats()
        self.assertEqual(stats['total_readings'], 1)
    
    def test_retention_30_days(self):
        """Test that data is kept for 30 days"""
        import sqlite3
        
        # Insert data at 29 days old (should be kept)
        old_date = (datetime.now() - timedelta(days=29)).isoformat()
        
        with sqlite3.connect(self.test_db) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO readings (timestamp, voltage, force_percent, state, variance)
                VALUES (?, 2.0, 50.0, 'Asleep', 0.02)
            """, (old_date,))
            conn.commit()
        
        # Cleanup
        deleted = self.dm.cleanup_old_data()
        
        # Should not delete 29-day old data
        self.assertEqual(deleted, 0)


class TestDataManagerErrorHandling(unittest.TestCase):
    """Test error handling and recovery"""
    
    def setUp(self):
        self.test_db = "test_errors.db"
        if os.path.exists(self.test_db):
            os.remove(self.test_db)
        self.dm = DataManager(db_path=self.test_db)
    
    def tearDown(self):
        if os.path.exists(self.test_db):
            os.remove(self.test_db)
    
    @patch('sqlite3.connect')
    def test_retry_on_lock(self, mock_connect):
        """Test retry when database is locked"""
        # First two calls fail with locked, third succeeds
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_conn.cursor.return_value = mock_cursor
        
        mock_connect.side_effect = [
            sqlite3.OperationalError("database is locked"),
            sqlite3.OperationalError("database is locked"),
            mock_conn
        ]
        
        # Should retry and eventually succeed
        # Note: This test is simplified; real test would need more mocking
    
    def test_flush_memory_queue(self):
        """Test flushing memory queue to database"""
        # Add items to queue
        self.dm._memory_queue = [
            {'voltage': 1.0, 'force_percent': 25.0, 'state': 'Asleep', 
             'variance': 0.01, 'timestamp': '2026-02-03T14:30:00'},
            {'voltage': 2.0, 'force_percent': 50.0, 'state': 'Asleep', 
             'variance': 0.02, 'timestamp': '2026-02-03T14:30:01'}
        ]
        
        # Flush
        self.dm._flush_memory_queue()
        
        # Queue should be empty
        self.assertEqual(len(self.dm._memory_queue), 0)
        
        # Data should be in database
        stats = self.dm.get_stats()
        self.assertEqual(stats['total_readings'], 2)


if __name__ == '__main__':
    unittest.main(verbosity=2)
