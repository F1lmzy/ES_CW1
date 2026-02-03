"""
Data Management Module
SQLite offline storage with automatic cleanup and JSON serialization for MQTT.
Meets specification #23: System remains functional when data connectivity is lost.
"""

import sqlite3
import json
import time
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)


class DataManagerError(Exception):
    """Custom exception for DataManager errors"""
    pass


class DataManager:
    """
    Manages sensor data storage and retrieval.
    
    Features:
    - SQLite local storage for offline functionality (spec #23)
    - 30-day data retention with automatic cleanup
    - JSON serialization for MQTT transmission
    - Calibration data persistence
    - Error handling with retry logic
    - In-memory queue for SQLite failures
    
    Schema:
    - readings: sensor data with sync status
    - calibration: single-row calibration parameters
    """
    
    # Retention period: 30 days
    RETENTION_DAYS = 30
    
    # Cleanup interval: every 100 inserts
    CLEANUP_INTERVAL = 100
    
    # In-memory queue size (for SQLite failures)
    MAX_QUEUE_SIZE = 1000
    
    def __init__(self, db_path: str = "sleepsense.db", device_id: str = "rpi_node_1", 
                 user_id: str = "user_001"):
        """
        Initialize DataManager.
        
        Args:
            db_path: Path to SQLite database file
            device_id: Unique device identifier for JSON payload
            user_id: User identifier for JSON payload
        """
        self.db_path = db_path
        self.device_id = device_id
        self.user_id = user_id
        
        # Insert counter for cleanup scheduling
        self._insert_count = 0
        
        # In-memory queue for offline buffering when SQLite fails
        self._memory_queue: List[Dict] = []
        
        # Initialize database
        self._init_db()
        
        logger.info(f"DataManager initialized: {db_path}")
    
    def _init_db(self):
        """Initialize SQLite database with schema"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Sensor readings table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS readings (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                        voltage REAL,
                        force_percent REAL,
                        state TEXT,
                        variance REAL,
                        synced BOOLEAN DEFAULT 0,
                        device_id TEXT DEFAULT 'rpi_node_1',
                        user_id TEXT DEFAULT 'user_001'
                    )
                """)
                
                # Calibration table (single row)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS calibration (
                        id INTEGER PRIMARY KEY CHECK (id = 1),
                        baseline_voltage REAL,
                        occupied_threshold REAL,
                        movement_threshold REAL,
                        calibrated_at DATETIME
                    )
                """)
                
                # Indexes for performance
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_timestamp ON readings(timestamp)
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_synced ON readings(synced) 
                    WHERE synced = 0
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_user_device 
                    ON readings(user_id, device_id)
                """)
                
                conn.commit()
                logger.info("Database schema initialized")
                
        except sqlite3.Error as e:
            logger.error(f"Database initialization failed: {e}")
            raise DataManagerError(f"Failed to initialize database: {e}")
    
    def _execute_with_retry(self, operation, max_retries: int = 3) -> Any:
        """
        Execute database operation with retry logic.
        
        Args:
            operation: Function that performs database operation
            max_retries: Maximum number of retry attempts
            
        Returns:
            Result of operation
        """
        for attempt in range(max_retries):
            try:
                return operation()
            except sqlite3.OperationalError as e:
                if "database is locked" in str(e) and attempt < max_retries - 1:
                    wait_time = 0.1 * (attempt + 1)
                    logger.warning(f"Database locked, retrying in {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    raise
        
        raise DataManagerError("Max retries exceeded")
    
    def store_reading(self, voltage: float, force_percent: float, state: str, 
                      variance: float) -> bool:
        """
        Store sensor reading to SQLite.
        
        If SQLite fails, stores in memory queue for later flush.
        
        Args:
            voltage: Voltage reading
            force_percent: Force percentage (0-100)
            state: Sleep state string
            variance: Movement variance
            
        Returns:
            True if stored successfully, False otherwise
        """
        def _insert():
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO readings 
                    (voltage, force_percent, state, variance, device_id, user_id, synced)
                    VALUES (?, ?, ?, ?, ?, ?, 0)
                """, (voltage, force_percent, state, variance, self.device_id, self.user_id))
                conn.commit()
                return True
        
        try:
            result = self._execute_with_retry(_insert)
            self._insert_count += 1
            
            # Periodic cleanup
            if self._insert_count >= self.CLEANUP_INTERVAL:
                self.cleanup_old_data()
                self._insert_count = 0
            
            # Flush memory queue if any
            if self._memory_queue:
                self._flush_memory_queue()
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to store reading to SQLite: {e}")
            # Store in memory queue for later
            if len(self._memory_queue) < self.MAX_QUEUE_SIZE:
                self._memory_queue.append({
                    'voltage': voltage,
                    'force_percent': force_percent,
                    'state': state,
                    'variance': variance,
                    'timestamp': datetime.now().isoformat()
                })
                logger.warning(f"Stored in memory queue (size: {len(self._memory_queue)})")
            return False
    
    def _flush_memory_queue(self):
        """Flush in-memory queue to SQLite"""
        if not self._memory_queue:
            return
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                for item in self._memory_queue:
                    cursor.execute("""
                        INSERT INTO readings 
                        (voltage, force_percent, state, variance, timestamp, device_id, user_id, synced)
                        VALUES (?, ?, ?, ?, ?, ?, ?, 0)
                    """, (item['voltage'], item['force_percent'], item['state'], 
                          item['variance'], item['timestamp'], self.device_id, self.user_id))
                conn.commit()
                
            logger.info(f"Flushed {len(self._memory_queue)} items from memory queue")
            self._memory_queue.clear()
            
        except Exception as e:
            logger.error(f"Failed to flush memory queue: {e}")
    
    def get_unsynced_readings(self, limit: int = 100) -> List[Dict]:
        """
        Get readings that haven't been synced to remote server.
        
        Spec #23: Enables offline functionality with sync when reconnected.
        
        Args:
            limit: Maximum number of readings to return
            
        Returns:
            List of unsynced readings as dictionaries
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT id, timestamp, voltage, force_percent, state, variance,
                           device_id, user_id
                    FROM readings 
                    WHERE synced = 0
                    ORDER BY timestamp ASC
                    LIMIT ?
                """, (limit,))
                
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
                
        except Exception as e:
            logger.error(f"Failed to get unsynced readings: {e}")
            return []
    
    def mark_synced(self, ids: List[int]) -> bool:
        """
        Mark readings as synced after successful MQTT transmission.
        
        Args:
            ids: List of reading IDs to mark as synced
            
        Returns:
            True if successful
        """
        if not ids:
            return True
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                placeholders = ','.join('?' * len(ids))
                cursor.execute(f"""
                    UPDATE readings SET synced = 1
                    WHERE id IN ({placeholders})
                """, ids)
                conn.commit()
                
            logger.debug(f"Marked {len(ids)} readings as synced")
            return True
            
        except Exception as e:
            logger.error(f"Failed to mark readings as synced: {e}")
            return False
    
    def get_recent_readings(self, limit: int = 100, hours: Optional[int] = None) -> List[Dict]:
        """
        Get recent readings from database.
        
        Args:
            limit: Maximum number of readings
            hours: If specified, only get readings from last N hours
            
        Returns:
            List of readings as dictionaries
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                if hours:
                    since = datetime.now() - timedelta(hours=hours)
                    cursor.execute("""
                        SELECT * FROM readings 
                        WHERE timestamp > ?
                        ORDER BY timestamp DESC
                        LIMIT ?
                    """, (since.isoformat(), limit))
                else:
                    cursor.execute("""
                        SELECT * FROM readings 
                        ORDER BY timestamp DESC
                        LIMIT ?
                    """, (limit,))
                
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
                
        except Exception as e:
            logger.error(f"Failed to get recent readings: {e}")
            return []
    
    def save_calibration(self, baseline_voltage: float, occupied_threshold: float,
                        movement_threshold: float) -> bool:
        """
        Save calibration values to SQLite.
        
        Args:
            baseline_voltage: Empty bed voltage
            occupied_threshold: Occupied bed voltage
            movement_threshold: Movement detection threshold
            
        Returns:
            True if successful
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Use REPLACE to handle single-row constraint
                cursor.execute("""
                    REPLACE INTO calibration 
                    (id, baseline_voltage, occupied_threshold, movement_threshold, calibrated_at)
                    VALUES (1, ?, ?, ?, datetime('now'))
                """, (baseline_voltage, occupied_threshold, movement_threshold))
                
                conn.commit()
                logger.info("Calibration saved to database")
                return True
                
        except Exception as e:
            logger.error(f"Failed to save calibration: {e}")
            return False
    
    def load_calibration(self) -> Optional[Dict]:
        """
        Load calibration values from SQLite.
        
        Returns:
            Dictionary with calibration data or None if not found
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                cursor.execute("SELECT * FROM calibration WHERE id = 1")
                row = cursor.fetchone()
                
                if row:
                    return dict(row)
                return None
                
        except Exception as e:
            logger.error(f"Failed to load calibration: {e}")
            return None
    
    def cleanup_old_data(self) -> int:
        """
        Remove data older than retention period (30 days).
        
        Returns:
            Number of records deleted
        """
        cutoff = datetime.now() - timedelta(days=self.RETENTION_DAYS)
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    DELETE FROM readings 
                    WHERE timestamp < ?
                """, (cutoff.isoformat(),))
                
                deleted = cursor.rowcount
                conn.commit()
                
                if deleted > 0:
                    logger.info(f"Cleaned up {deleted} old records (older than {self.RETENTION_DAYS} days)")
                
                # Vacuum to reclaim space
                cursor.execute("VACUUM")
                
                return deleted
                
        except Exception as e:
            logger.error(f"Failed to cleanup old data: {e}")
            return 0
    
    def to_json(self, reading: Dict) -> str:
        """
        Convert reading to JSON format for MQTT transmission.
        
        JSON Schema:
        {
            "timestamp": "2026-02-03T14:30:00",
            "sensor_type": "fsr408",
            "channel": 0,
            "voltage": 2.45,
            "force_percent": 67.5,
            "state": "Asleep",
            "variance": 0.02,
            "device_id": "rpi_node_1",
            "user_id": "user_001"
        }
        
        Args:
            reading: Dictionary with sensor reading data
            
        Returns:
            JSON string
        """
        payload = {
            'timestamp': reading.get('timestamp', datetime.now().isoformat()),
            'sensor_type': 'fsr408',
            'channel': 0,
            'voltage': reading.get('voltage', 0.0),
            'force_percent': reading.get('force_percent', 0.0),
            'state': reading.get('state', 'Unknown'),
            'variance': reading.get('variance', 0.0),
            'device_id': self.device_id,
            'user_id': self.user_id
        }
        
        return json.dumps(payload, indent=2)
    
    def get_stats(self) -> Dict:
        """
        Get database statistics.
        
        Returns:
            Dictionary with database stats
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Total readings
                cursor.execute("SELECT COUNT(*) FROM readings")
                total = cursor.fetchone()[0]
                
                # Unsynced readings
                cursor.execute("SELECT COUNT(*) FROM readings WHERE synced = 0")
                unsynced = cursor.fetchone()[0]
                
                # Database size
                db_size = Path(self.db_path).stat().st_size
                
                # Oldest and newest readings
                cursor.execute("SELECT MIN(timestamp), MAX(timestamp) FROM readings")
                min_ts, max_ts = cursor.fetchone()
                
                return {
                    'total_readings': total,
                    'unsynced_readings': unsynced,
                    'database_size_mb': round(db_size / (1024 * 1024), 2),
                    'oldest_reading': min_ts,
                    'newest_reading': max_ts,
                    'memory_queue_size': len(self._memory_queue)
                }
                
        except Exception as e:
            logger.error(f"Failed to get stats: {e}")
            return {}


# Convenience function for testing
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    print("\nDataManager Test")
    
    # Create manager
    dm = DataManager(db_path="test.db", device_id="test_node", user_id="test_user")
    
    # Store some readings
    print("\nStoring readings...")
    for i in range(5):
        dm.store_reading(
            voltage=2.0 + (i * 0.1),
            force_percent=50.0 + (i * 5),
            state="Asleep",
            variance=0.02
        )
    
    # Save calibration
    dm.save_calibration(baseline_voltage=0.5, occupied_threshold=2.5, movement_threshold=0.1)
    
    # Get unsynced readings
    unsynced = dm.get_unsynced_readings()
    print(f"\nUnsynced readings: {len(unsynced)}")
    
    # Convert to JSON
    if unsynced:
        json_data = dm.to_json(unsynced[0])
        print(f"\nSample JSON:\n{json_data}")
    
    # Get stats
    stats = dm.get_stats()
    print(f"\nDatabase stats: {stats}")
    
    # Mark synced
    ids = [r['id'] for r in unsynced[:3]]
    dm.mark_synced(ids)
    
    # Cleanup
    dm.cleanup_old_data()
    
    print("\nTest complete!")
