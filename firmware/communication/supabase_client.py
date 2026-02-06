"""
Supabase REST Client for Firmware
Replaces MQTT with direct HTTP communication.

Strictly adhering to project constraints:
- Uses http.client (standard library, no 'requests' dependency)
- One-to-one mapping between method calls and HTTP requests
- Explicit control over headers and payload
"""

import http.client
import json
import logging
from typing import Any, Dict, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class SupabaseClient:
    """
    Wrapper for Supabase REST API interactions.

    Adheres to constraint: "Wrapper libraries for REST APIs are permitted.
    A wrapper has a one-to-one mapping between wrapper calls and HTTP requests"
    """

    def __init__(self, url: str, key: str):
        """
        Initialize Supabase client.

        Args:
            url: Full project URL (e.g., https://xyz.supabase.co)
            key: Anon/Public API key
        """
        self.url = url
        self.key = key

        # Parse URL for low-level connection
        parsed = urlparse(url)
        self.host = parsed.netloc
        self.base_path = parsed.path if parsed.path else ""

        # Headers required by Supabase
        self.headers = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",  # Don't send back the inserted object, saves bandwidth
        }

    def _post(self, table: str, payload: Dict[str, Any]) -> bool:
        """
        Internal method to execute raw HTTP POST.

        Args:
            table: Table name (endpoint)
            payload: Dictionary data to send

        Returns:
            True if successful (201 Created), False otherwise
        """
        conn = None
        try:
            # 1. Establish connection (TCP/TLS handshake)
            conn = http.client.HTTPSConnection(self.host, timeout=10)

            # 2. Serialize JSON
            json_data = json.dumps(payload)

            # 3. Send Request
            endpoint = f"{self.base_path}/rest/v1/{table}"
            conn.request("POST", endpoint, json_data, self.headers)

            # 4. Get Response
            response = conn.getresponse()

            # 5. Check Status (201 Created is success for insert)
            if response.status in (200, 201):
                # Consume body to clear connection
                response.read()
                return True
            else:
                logger.error(
                    f"HTTP Error {response.status}: {response.read().decode()}"
                )
                return False

        except Exception as e:
            logger.error(f"Connection failed: {e}")
            return False
        finally:
            if conn:
                conn.close()

    def insert_reading(self, reading_data: Dict[str, Any]) -> bool:
        """
        Send a single sensor reading to the 'readings' table.

        Args:
            reading_data: Dictionary matching table schema
        """
        # Ensure data matches Supabase schema expectations
        # Convert timestamp to ISO format if it's not already
        if "timestamp" in reading_data:
            # Supabase expects 'created_at', but we can map it if needed
            # For now, let's assume the table has 'timestamp' or we rename it
            # Standardizing on 'created_at' is better for Supabase
            reading_data["created_at"] = reading_data.pop("timestamp", None)

        # Clean up keys that might not exist in the simple schema
        # (The schema we designed: id, created_at, device_id, user_id, voltage, force_percent, state, variance)
        payload = {
            k: v
            for k, v in reading_data.items()
            if k
            in [
                "created_at",
                "device_id",
                "user_id",
                "voltage",
                "force_percent",
                "state",
                "variance",
            ]
        }

        return self._post("readings", payload)

    def is_configured(self) -> bool:
        """Check if URL and Key are set to something non-empty."""
        return bool(self.url and self.key and "placeholder" not in self.url)
