"""
Secure database operations - prevents SQL injection
"""
import glob
import logging
import pathlib
import sqlite3
import json
from typing import List, Tuple, Optional, Dict, Any
from datetime import datetime, timedelta
import time

logger = logging.getLogger(__name__)


def find_newest_matching_kismet_db(pattern: str) -> Optional[pathlib.Path]:
    """Return the newest matching Kismet database path for a glob pattern."""
    newest_path: Optional[pathlib.Path] = None
    newest_key: Optional[tuple[int, str]] = None

    for match in glob.glob(pattern):
        path = pathlib.Path(match)
        try:
            if not path.is_file():
                continue
            stat_result = path.stat()
        except OSError:
            continue

        candidate_key = (stat_result.st_mtime_ns, str(path))
        if newest_key is None or candidate_key > newest_key:
            newest_key = candidate_key
            newest_path = path

    return newest_path


def select_runtime_kismet_db(current_path: str, pattern: str) -> Tuple[pathlib.Path, bool]:
    """
    Resolve the active Kismet database path for runtime monitoring.

    Returns the current path unchanged when discovery yields no usable
    replacement or when the candidate cannot be opened/validated.
    """
    current_db_path = pathlib.Path(current_path)
    candidate_path = find_newest_matching_kismet_db(pattern)

    if candidate_path is None:
        logger.warning(
            "No Kismet database candidates matched pattern: %s; retaining %s",
            pattern,
            current_db_path,
        )
        return current_db_path, False

    if candidate_path == current_db_path:
        return current_db_path, False

    try:
        with SecureKismetDB(str(candidate_path)) as candidate_db:
            if not candidate_db.validate_connection():
                logger.warning(
                    "Retaining current Kismet database %s after candidate %s failed validation",
                    current_db_path,
                    candidate_path,
                )
                return current_db_path, False
    except Exception as exc:
        logger.warning(
            "Retaining current Kismet database %s after candidate %s could not be opened or validated: %s",
            current_db_path,
            candidate_path,
            exc,
        )
        return current_db_path, False

    logger.info("Using Kismet database: %s", candidate_path)
    return candidate_path, True

class SecureKismetDB:
    """Secure wrapper for Kismet database operations"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._connection = None
    
    def __enter__(self):
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
    
    def connect(self) -> None:
        """Establish secure database connection"""
        try:
            self._connection = sqlite3.connect(self.db_path, timeout=30.0)
            self._connection.row_factory = sqlite3.Row  # Enable column access by name
            logger.info(f"Connected to database: {self.db_path}")
        except sqlite3.Error as e:
            logger.error(f"Failed to connect to database {self.db_path}: {e}")
            raise
    
    def close(self) -> None:
        """Close database connection"""
        if self._connection:
            self._connection.close()
            self._connection = None
    
    def execute_safe_query(self, query: str, params: Tuple = ()) -> List[sqlite3.Row]:
        """Execute parameterized query safely"""
        if not self._connection:
            raise RuntimeError("Database not connected")
        
        try:
            cursor = self._connection.cursor()
            cursor.execute(query, params)
            return cursor.fetchall()
        except sqlite3.Error as e:
            logger.error(f"Database query failed: {query}, params: {params}, error: {e}")
            raise
    
    def get_devices_by_time_range(self, start_time: float, end_time: Optional[float] = None) -> List[Dict[str, Any]]:
        """
        Get devices within time range with proper parameterization
        
        Args:
            start_time: Unix timestamp for start time
            end_time: Optional unix timestamp for end time
            
        Returns:
            List of device dictionaries
        """
        if end_time is not None:
            query = "SELECT devmac, type, device, last_time FROM devices WHERE last_time >= ? AND last_time <= ?"
            params = (start_time, end_time)
        else:
            query = "SELECT devmac, type, device, last_time FROM devices WHERE last_time >= ?"
            params = (start_time,)
        
        rows = self.execute_safe_query(query, params)
        
        devices = []
        for row in rows:
            try:
                # Parse device JSON safely
                device_data = None
                if row['device']:
                    try:
                        device_data = json.loads(row['device'])
                    except (json.JSONDecodeError, TypeError) as e:
                        logger.warning(f"Failed to parse device JSON for {row['devmac']}: {e}")
                
                devices.append({
                    'mac': row['devmac'],
                    'type': row['type'],
                    'device_data': device_data,
                    'last_time': row['last_time']
                })
            except Exception as e:
                logger.warning(f"Error processing device row: {e}")
                continue
        
        return devices
    
    def get_mac_addresses_by_time_range(self, start_time: float, end_time: Optional[float] = None) -> List[str]:
        """Get just MAC addresses for a time range"""
        devices = self.get_devices_by_time_range(start_time, end_time)
        return [device['mac'] for device in devices if device['mac']]
    
    def get_probe_requests_by_time_range(self, start_time: float, end_time: Optional[float] = None) -> List[Dict[str, str]]:
        """
        Get probe requests with SSIDs for time range
        
        Returns:
            List of dicts with 'mac', 'ssid', 'timestamp'
        """
        devices = self.get_devices_by_time_range(start_time, end_time)
        
        probes = []
        for device in devices:
            mac = device['mac']
            device_data = device['device_data']
            
            if not device_data:
                continue
            
            # Extract probe request SSID safely
            try:
                dot11_device = device_data.get('dot11.device', {})
                if not isinstance(dot11_device, dict):
                    continue
                    
                probe_record = dot11_device.get('dot11.device.last_probed_ssid_record', {})
                if not isinstance(probe_record, dict):
                    continue
                
                ssid = probe_record.get('dot11.probedssid.ssid', '')
                if ssid and isinstance(ssid, str):
                    probes.append({
                        'mac': mac,
                        'ssid': ssid,
                        'timestamp': device['last_time']
                    })
            except (KeyError, TypeError, AttributeError) as e:
                logger.debug(f"No probe data for device {mac}: {e}")
                continue
        
        return probes
    
    def validate_connection(self) -> bool:
        """Validate database connection and basic structure"""
        try:
            # Test basic query
            result = self.execute_safe_query("SELECT COUNT(*) as count FROM devices LIMIT 1")
            count = result[0]['count'] if result else 0
            logger.info(f"Database contains {count} devices")
            return True
        except sqlite3.Error as e:
            logger.error(f"Database validation failed: {e}")
            return False


class SecureTimeWindows:
    """Secure time window management for device tracking"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.time_windows = config.get('timing', {}).get('time_windows', {
            'recent': 5,
            'medium': 10, 
            'old': 15,
            'oldest': 20
        })
    
    def get_time_boundaries(self) -> Dict[str, float]:
        """Calculate secure time boundaries"""
        now = datetime.now()
        
        boundaries = {}
        for window_name, minutes in self.time_windows.items():
            boundary_time = now - timedelta(minutes=minutes)
            boundaries[f'{window_name}_time'] = time.mktime(boundary_time.timetuple())
        
        # Add current time boundary (2 minutes ago for active scanning)
        current_boundary = now - timedelta(minutes=2)
        boundaries['current_time'] = time.mktime(current_boundary.timetuple())
        
        return boundaries
    
    def filter_devices_by_ignore_list(self, devices: List[str], ignore_list: List[str]) -> List[str]:
        """Safely filter devices against ignore list"""
        if not ignore_list:
            return devices
        
        # Convert ignore list to set for O(1) lookup
        ignore_set = set(mac.upper() for mac in ignore_list)
        
        filtered = []
        for device in devices:
            if isinstance(device, str) and device.upper() not in ignore_set:
                filtered.append(device)
        
        return filtered
    
    def filter_ssids_by_ignore_list(self, ssids: List[str], ignore_list: List[str]) -> List[str]:
        """Safely filter SSIDs against ignore list"""
        if not ignore_list:
            return ssids
        
        ignore_set = set(ignore_list)
        
        filtered = []
        for ssid in ssids:
            if isinstance(ssid, str) and ssid not in ignore_set:
                filtered.append(ssid)
        
        return filtered


def create_secure_db_connection(db_path: str) -> SecureKismetDB:
    """Factory function to create secure database connection"""
    return SecureKismetDB(db_path)
