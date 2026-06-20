#!/usr/bin/env python3
"""
Integrated Surveillance Analysis Tool for CYT
Combines GPS tracking, device detection, and KML export for stalking/surveillance detection
"""
import argparse
import glob
import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path

from surveillance_detector import SurveillanceDetector, load_appearances_from_kismet
from gps_tracker import GPSTracker, KMLExporter, simulate_gps_data
from secure_credentials import secure_config_loader

logger = logging.getLogger(__name__)


def _configure_cli_logging() -> None:
    """Configure CLI logging only when the tool is executed directly."""
    log_path = os.path.abspath('surveillance_analysis.log')
    root_logger = logging.getLogger()

    for handler in root_logger.handlers:
        if isinstance(handler, logging.FileHandler) and os.path.abspath(handler.baseFilename) == log_path:
            return

    root_logger.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

    file_handler = logging.FileHandler('surveillance_analysis.log')
    file_handler.setFormatter(formatter)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    root_logger.addHandler(file_handler)
    root_logger.addHandler(stream_handler)

class SurveillanceAnalyzer:
    """Main surveillance analysis orchestrator"""
    
    def __init__(self, config_path: str = 'config.json'):
        # Load secure configuration
        os.environ['CYT_TEST_MODE'] = 'true'  # For non-interactive mode
        self.config, self.credential_manager = secure_config_loader(config_path)
        
        # Initialize components
        self.detector = SurveillanceDetector(self.config)
        self.gps_tracker = GPSTracker(self.config)
        self.kml_exporter = KMLExporter()
        
        # Analysis settings
        self.analysis_window_hours = 24  # Analyze last 24 hours by default
        
    def analyze_kismet_data(self, kismet_db_path: str = None, 
                          gps_data: list = None) -> dict:
        """Perform complete surveillance analysis on Kismet data"""
        
        print("🔍 Starting Surveillance Analysis...")
        print("=" * 50)
        
        # Find all Kismet databases from past 24 hours
        if not kismet_db_path:
            db_pattern = self.config['paths']['kismet_logs']
            all_db_files = glob.glob(db_pattern)
            if not all_db_files:
                raise FileNotFoundError(f"No Kismet database found at: {db_pattern}")
            
            # Filter to databases modified in the past 24 hours
            import sqlite3
            current_time = time.time()
            hours_24_ago = current_time - (self.analysis_window_hours * 3600)
            
            recent_db_files = [db for db in all_db_files if os.path.getmtime(db) >= hours_24_ago]
            recent_db_files = sorted(recent_db_files, key=os.path.getmtime, reverse=True)
            
            if not recent_db_files:
                print(f"⚠️ No databases found from past {self.analysis_window_hours} hours, using most recent")
                kismet_db_path = max(all_db_files, key=os.path.getmtime)
            else:
                print(f"📊 Found {len(recent_db_files)} databases from past {self.analysis_window_hours} hours:")
                total_gps_coords = 0
                for db_file in recent_db_files:
                    try:
                        conn = sqlite3.connect(db_file)
                        cursor = conn.cursor()
                        cursor.execute("SELECT COUNT(*) FROM devices WHERE avg_lat != 0 AND avg_lon != 0")
                        gps_count = cursor.fetchone()[0]
                        conn.close()
                        print(f"   📁 {os.path.basename(db_file)}: {gps_count} GPS locations")
                        total_gps_coords += gps_count
                    except:
                        print(f"   ❌ {os.path.basename(db_file)}: Error reading")
                
                print(f"🛰️ Total GPS coordinates across all databases: {total_gps_coords}")
                # We'll process all recent databases, not just one
                kismet_db_path = recent_db_files  # Pass list instead of single file
        
        # Handle multiple database files
        db_files_to_process = kismet_db_path if isinstance(kismet_db_path, list) else [kismet_db_path]
        print(f"📊 Processing {len(db_files_to_process)} Kismet database(s)")
        
        # Load GPS data (real, simulated, or extract from Kismet)
        if gps_data:
            print(f"🛰️ Loading {len(gps_data)} GPS coordinates...")
            for lat, lon, name in gps_data:
                location_id = self.gps_tracker.add_gps_reading(lat, lon, location_name=name)
                print(f"   📍 {name}: {lat:.4f}, {lon:.4f} -> {location_id}")
        else:
            # Extract GPS coordinates from all Kismet databases
            print("🛰️ Extracting GPS coordinates from Kismet databases...")
            try:
                import sqlite3
                all_gps_coords = []
                
                for db_file in db_files_to_process:
                    try:
                        conn = sqlite3.connect(db_file)
                        cursor = conn.cursor()
                        
                        # Get GPS locations with timestamps from this database
                        cursor.execute("""
                            SELECT DISTINCT avg_lat, avg_lon, first_time
                            FROM devices 
                            WHERE avg_lat != 0 AND avg_lon != 0 
                            ORDER BY first_time
                        """)
                        
                        db_coords = cursor.fetchall()
                        conn.close()
                        
                        if db_coords:
                            print(f"   📁 {os.path.basename(db_file)}: {len(db_coords)} GPS locations")
                            all_gps_coords.extend(db_coords)
                        
                    except Exception as e:
                        print(f"   ❌ Error reading {os.path.basename(db_file)}: {e}")
                        continue
                
                if all_gps_coords:
                    # Sort all coordinates by timestamp and deduplicate nearby points
                    all_gps_coords.sort(key=lambda x: x[2])  # Sort by timestamp
                    
                    gps_data = []
                    prev_lat, prev_lon = None, None
                    location_counter = 1
                    
                    for lat, lon, timestamp in all_gps_coords:
                        # Skip if too close to previous point (within ~50m)
                        if prev_lat and prev_lon:
                            import math
                            distance = math.sqrt((lat - prev_lat)**2 + (lon - prev_lon)**2) * 111000  # rough meters
                            if distance < 50:
                                continue
                        
                        location_name = f"Location_{location_counter}"
                        location_id = self.gps_tracker.add_gps_reading(lat, lon, location_name=location_name)
                        print(f"   📍 {location_name}: {lat:.6f}, {lon:.6f}")
                        gps_data.append((lat, lon, location_name))
                        
                        prev_lat, prev_lon = lat, lon
                        location_counter += 1
                    
                    print(f"🛰️ Total unique GPS locations: {len(gps_data)}")
                else:
                    print("⚠️ No GPS coordinates found in any Kismet database - using single location mode")
                    location_id = "unknown_location"
                    
            except Exception as e:
                print(f"❌ Error extracting GPS from Kismet: {e}")
                print("⚠️ Using single location mode")
                location_id = "unknown_location"
        
        # Load device appearances from Kismet databases
        print("📡 Loading device appearances from Kismet databases...")
        total_count = 0
        
        if gps_data:
            # Load devices from all databases, associating them with GPS locations
            primary_location = "Location_1"  # Use the first/primary location
            for db_file in db_files_to_process:
                db_count = self._load_appearances_with_gps(db_file, primary_location)
                print(f"   📁 {os.path.basename(db_file)}: {db_count} device appearances")
                total_count += db_count
        else:
            # Load from all databases without GPS correlation
            for db_file in db_files_to_process:
                db_count = load_appearances_from_kismet(db_file, self.detector, "unknown_location")
                print(f"   📁 {os.path.basename(db_file)}: {db_count} device appearances")
                total_count += db_count
        
        print(f"✅ Total device appearances loaded: {total_count:,}")
        
        # Perform surveillance detection
        print("\\n🔍 Analyzing repeated-observation patterns...")
        suspicious_devices = self.detector.analyze_surveillance_patterns()
        
        if suspicious_devices:
            print(f"⚠️ {len(suspicious_devices)} identifiers met the heuristic review threshold.")
            print("\\nTop review candidates:")
            for i, device in enumerate(suspicious_devices[:5], 1):
                print(f"  {i}. {device.mac} (Score: {device.persistence_score:.2f})")
                print(f"     Appearances: {device.total_appearances}, Locations: {len(device.locations_seen)}")
                for reason in device.reasons[:2]:  # Show top 2 reasons
                    print(f"     • {reason}")
                print()
        else:
            print("✅ No identifiers met the heuristic review threshold")
        
        # Generate reports
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Generate surveillance report
        report_file = f"surveillance_reports/surveillance_report_{timestamp}.md"
        html_file = f"surveillance_reports/surveillance_report_{timestamp}.html"
        print(f"\\n📝 Generating heuristic review reports:")
        print(f"   📄 Markdown: {report_file}")
        print(f"   🌐 HTML: {html_file}")
        surveillance_report = self.detector.generate_surveillance_report(report_file)
        
        # Generate KML file if GPS data available
        kml_file = None
        if gps_data:
            kml_file = f"kml_files/surveillance_analysis_{timestamp}.kml"
            print(f"🗺️ Generating KML visualization: {kml_file}")
            self.kml_exporter.generate_kml(self.gps_tracker, suspicious_devices, kml_file)
            print(f"   Open in Google Earth to visualize device tracking patterns")
        
        # Analysis summary
        multi_location_devices = self.gps_tracker.get_devices_across_locations()
        location_sessions = self.gps_tracker.get_location_history()
        
        results = {
            'total_devices': total_count,
            'suspicious_devices': len(suspicious_devices),
            'high_persistence_devices': len([d for d in suspicious_devices if d.persistence_score > 0.8]),
            'multi_location_devices': len(multi_location_devices),
            'location_sessions': len(location_sessions),
            'report_file': report_file,
            'kml_file': kml_file,
            'suspicious_device_list': suspicious_devices
        }
        
        return results
    
    def generate_demo_analysis(self) -> dict:
        """Generate analysis using simulated GPS data for demo purposes"""
        print("🎯 Generating heuristic review demo analysis...")
        print("Using simulated GPS route with real Kismet data")
        
        # Use simulated GPS route
        gps_route = simulate_gps_data()
        
        # Perform analysis
        results = self.analyze_kismet_data(gps_data=gps_route)
        
        print("\\n🎪 Demo Analysis Complete!")
        print("=" * 50)
        print(f"📊 Analysis Results:")
        print(f"   Total Devices: {results['total_devices']:,}")
        print(f"   Identifiers Meeting Review Threshold: {results['suspicious_devices']}")
        print(f"   High Review: {results['high_threat_devices']}")
        print(f"   Multi-Location Devices: {results['multi_location_devices']}")
        print(f"   Location Sessions: {results['location_sessions']}")
        print(f"\\n📁 Generated Files:")
        print(f"   📝 Report: {results['report_file']}")
        if results['kml_file']:
            print(f"   🗺️ KML: {results['kml_file']}")
        
        return results
    
    def analyze_multi_location_activity(self, min_review_score: float = 0.7) -> list:
        """Analyze for repeated multi-location activity using the existing candidate algorithm"""
        suspicious_devices = self.detector.analyze_surveillance_patterns()

        # Filter for repeated multi-location review indicators
        review_candidates = []
        for device in suspicious_devices:
            if device.persistence_score >= min_review_score:
                # Additional repeated-observation checks
                locations = len(device.locations_seen)
                appearances = device.total_appearances

                # Review indicators:
                # - Appears at 3+ different location labels
                # - High frequency of appearances
                # - Spans multiple days
                time_span = device.last_seen - device.first_seen
                time_span_hours = time_span.total_seconds() / 3600

                review_score = 0
                review_reasons = []

                if locations >= 3:
                    review_score += 0.4
                    review_reasons.append(f"Observed across {locations} location labels")

                if appearances >= 10:
                    review_score += 0.3
                    review_reasons.append(f"High frequency ({appearances} appearances)")

                if time_span_hours >= 24:
                    review_score += 0.3
                    review_reasons.append(f"Persistent over {time_span_hours/24:.1f} days")

                device.heuristic_review_score = review_score
                device.activity_reasons = review_reasons
                device.stalking_score = review_score
                device.stalking_reasons = review_reasons

                if review_score >= 0.6:
                    review_candidates.append(device)

        return review_candidates

    def analyze_for_stalking(self, min_persistence_score: float = 0.7) -> list:
        """Backward-compatible wrapper for multi-location activity review"""
        return self.analyze_multi_location_activity(min_review_score=min_persistence_score)
    
    def export_results_json(self, results: dict, output_file: str) -> None:
        """Export analysis results to JSON for further processing"""
        
        # Convert device objects to serializable format
        serializable_results = results.copy()
        if 'suspicious_device_list' in results:
            device_list = []
            for device in results['suspicious_device_list']:
                device_dict = {
                    'mac': device.mac,
                    'persistence_score': device.persistence_score,
                    'total_appearances': device.total_appearances,
                    'locations_seen': device.locations_seen,
                    'reasons': device.reasons,
                    'first_seen': device.first_seen.isoformat(),
                    'last_seen': device.last_seen.isoformat()
                }
                device_list.append(device_dict)
            serializable_results['suspicious_device_list'] = device_list
        
        with open(output_file, 'w') as f:
            json.dump(serializable_results, f, indent=2)
        
        print(f"📊 Results exported to JSON: {output_file}")
    
    def _load_appearances_with_gps(self, db_path: str, location_id: str) -> int:
        """Load device appearances and register them with GPS tracker"""
        import sqlite3
        import json
        
        try:
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                
                # Get all devices with timestamps
                cursor.execute("""
                    SELECT devmac, last_time, type, device 
                    FROM devices 
                    WHERE last_time > 0
                    ORDER BY last_time DESC
                """)
                
                rows = cursor.fetchall()
                count = 0
                
                # Set current location in GPS tracker for device correlation
                if hasattr(self.gps_tracker, 'location_sessions') and self.gps_tracker.location_sessions:
                    # Find the location session that matches our location_id
                    for session in self.gps_tracker.location_sessions:
                        if session.session_id == location_id:
                            self.gps_tracker.current_location = session
                            break
                
                for row in rows:
                    mac, timestamp, device_type, device_json = row
                    
                    # Extract SSIDs from device JSON
                    ssids_probed = []
                    try:
                        device_data = json.loads(device_json)
                        dot11_device = device_data.get('dot11.device', {})
                        if dot11_device:
                            probe_record = dot11_device.get('dot11.device.last_probed_ssid_record', {})
                            ssid = probe_record.get('dot11.probedssid.ssid')
                            if ssid:
                                ssids_probed = [ssid]
                    except (json.JSONDecodeError, KeyError):
                        pass
                    
                    # Add to surveillance detector
                    self.detector.add_device_appearance(
                        mac=mac,
                        timestamp=timestamp,
                        location_id=location_id,
                        ssids_probed=ssids_probed,
                        device_type=device_type
                    )
                    
                    # Also add to GPS tracker if current location is set
                    if self.gps_tracker.current_location:
                        self.gps_tracker.add_device_at_current_location(mac)
                    
                    count += 1
                
                logger.info(f"Loaded {count} device appearances from {db_path}")
                return count
                
        except Exception as e:
            logger.error(f"Error loading from Kismet database: {e}")
            return 0

def main():
    """Main CLI interface"""
    _configure_cli_logging()
    parser = argparse.ArgumentParser(description='CYT Surveillance Analysis Tool')
    parser.add_argument('--demo', action='store_true', 
                       help='Run demo analysis with simulated GPS data')
    parser.add_argument('--kismet-db', type=str,
                       help='Path to specific Kismet database file')
    parser.add_argument('--gps-file', type=str,
                       help='JSON file with GPS coordinates')
    parser.add_argument('--multi-location-only', action='store_true',
                       help='Focus analysis on repeated multi-location activity')
    parser.add_argument('--stalking-only', action='store_true',
                       help='Deprecated alias for --multi-location-only')
    parser.add_argument('--output-json', type=str,
                       help='Export results to JSON file')
    parser.add_argument('--min-threat', type=float, default=0.5,
                       help='Minimum heuristic review score for reporting (default: 0.5)')
    
    args = parser.parse_args()
    
    try:
        analyzer = SurveillanceAnalyzer()
        
        if args.demo:
            results = analyzer.generate_demo_analysis()
        else:
            # Load GPS data if provided
            gps_data = None
            if args.gps_file:
                with open(args.gps_file, 'r') as f:
                    gps_data = json.load(f)
            
            results = analyzer.analyze_kismet_data(
                kismet_db_path=args.kismet_db,
                gps_data=gps_data
            )
        
        # Multi-location activity review
        if args.multi_location_only or args.stalking_only:
            review_devices = analyzer.analyze_multi_location_activity(args.min_threat)
            print("\\nMulti-location activity review")
            if review_devices:
                for device in review_devices:
                    score = getattr(device, "heuristic_review_score", getattr(device, "stalking_score", 0.0))
                    reasons = getattr(device, "activity_reasons", getattr(device, "stalking_reasons", []))
                    print(f"   {device.mac} (Heuristic review score: {score:.2f})")
                    for reason in reasons:
                        print(f"      • {reason}")
            else:
                print("   No devices met the heuristic review threshold")
        
        # Export JSON if requested
        if args.output_json:
            analyzer.export_results_json(results, args.output_json)
        
        print("\\n🔒 Analysis complete.")
        
    except Exception as e:
        logger.error(f"Analysis failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == '__main__':
    exit(main())
