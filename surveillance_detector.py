"""
Surveillance Detection System for CYT
Detects devices that may be following or tracking the user
"""
import json
import sqlite3
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from collections import defaultdict
import pathlib

logger = logging.getLogger(__name__)

@dataclass
class DeviceAppearance:
    """Record of when/where a device was seen"""
    mac: str
    timestamp: float
    location_id: str  # GPS coordinates or location name
    ssids_probed: List[str]
    signal_strength: Optional[float] = None
    device_type: Optional[str] = None

@dataclass
class SuspiciousDevice:
    """Device flagged as potentially suspicious"""
    mac: str
    persistence_score: float
    appearances: List[DeviceAppearance]
    reasons: List[str]
    first_seen: datetime
    last_seen: datetime
    total_appearances: int
    locations_seen: List[str]

class SurveillanceDetector:
    """Detect potential surveillance devices"""
    
    def __init__(self, config: Dict):
        self.config = config
        self.appearances = []
        self.device_history = defaultdict(list)
        
        # Simple detection thresholds
        self.thresholds = {
            'min_appearances': 3,           # Need at least 3 appearances
            'min_time_span_hours': 1.0,     # Must span at least 1 hour
            'min_persistence_score': 0.5    # Minimum score to be flagged
        }
    
    def add_device_appearance(self, mac: str, timestamp: float, location_id: str, 
                            ssids_probed: List[str] = None, signal_strength: float = None,
                            device_type: str = None) -> None:
        """Record a device appearance"""
        appearance = DeviceAppearance(
            mac=mac,
            timestamp=timestamp,
            location_id=location_id,
            ssids_probed=ssids_probed or [],
            signal_strength=signal_strength,
            device_type=device_type
        )
        
        self.appearances.append(appearance)
        self.device_history[mac].append(appearance)
        
        logger.debug(f"Recorded appearance: {mac} at {location_id}")
    
    def analyze_surveillance_patterns(self) -> List[SuspiciousDevice]:
        """Analyze all devices for surveillance patterns"""
        suspicious_devices = []
        
        for mac, appearances in self.device_history.items():
            if len(appearances) < self.thresholds['min_appearances']:
                continue
                
            persistence_score, reasons = self._calculate_persistence_score(appearances)
            
            if persistence_score > self.thresholds['min_persistence_score']:  # Persistence threshold
                suspicious_device = SuspiciousDevice(
                    mac=mac,
                    persistence_score=persistence_score,
                    appearances=appearances,
                    reasons=reasons,
                    first_seen=datetime.fromtimestamp(min(a.timestamp for a in appearances)),
                    last_seen=datetime.fromtimestamp(max(a.timestamp for a in appearances)),
                    total_appearances=len(appearances),
                    locations_seen=list(set(a.location_id for a in appearances))
                )
                suspicious_devices.append(suspicious_device)
        
        # Sort by threat score
        suspicious_devices.sort(key=lambda d: d.persistence_score, reverse=True)
        return suspicious_devices
    
    def _calculate_persistence_score(self, appearances: List[DeviceAppearance]) -> Tuple[float, List[str]]:
        """Simple persistence scoring: just detect devices that appear frequently over time"""
        reasons = []
        
        # Need at least 3 appearances to be suspicious
        if len(appearances) < 3:
            return 0.0, reasons
        
        # Calculate time span device was active
        timestamps = [a.timestamp for a in appearances]
        time_span_hours = (max(timestamps) - min(timestamps)) / 3600
        
        # Skip devices that only appeared briefly
        if time_span_hours < 1.0:
            return 0.0, reasons
        
        # Simple scoring: more appearances over longer time = more suspicious
        appearance_rate = len(appearances) / time_span_hours
        
        # Calculate score based on how persistently it appeared
        if appearance_rate >= 0.5:  # Appeared at least every 2 hours
            score = min(appearance_rate / 2.0, 1.0)  # Cap at 1.0
            reasons.append(f"Appeared {len(appearances)} times over {time_span_hours:.1f} hours")
            
            # Bonus if seen across multiple locations
            unique_locations = len(set(a.location_id for a in appearances))
            if unique_locations > 1:
                reasons.append(f"Observed across {unique_locations} location labels")
                score = min(score + 0.3, 1.0)
            
            return score, reasons
        
        return 0.0, reasons
    
    
    
    
    
    def _generate_analysis_statistics(self) -> Dict:
        """Generate comprehensive statistics for the analysis"""
        if not self.appearances:
            return {
                'total_appearances': 0,
                'unique_devices': 0,
                'unique_locations': 0,
                'analysis_duration_hours': 0,
                'persistence_rate': 0,
                'multi_location_rate': 0,
                'temporal_clustering': 0,
                'off_hours_rate': 0,
                'probe_anomaly_rate': 0,
            }
        
        # Basic metrics
        total_appearances = len(self.appearances)
        unique_devices = len(self.device_history)
        unique_locations = len(set(a.location_id for a in self.appearances))
        
        # Time analysis
        timestamps = [a.timestamp for a in self.appearances]
        analysis_duration = max(timestamps) - min(timestamps)
        analysis_duration_hours = analysis_duration / 3600 if analysis_duration > 0 else 0
        
        # Device persistence analysis
        persistent_devices = [mac for mac, appearances in self.device_history.items() 
                            if len(appearances) >= self.thresholds['min_appearances']]
        persistence_rate = len(persistent_devices) / unique_devices if unique_devices > 0 else 0
        
        # Multi-location tracking analysis
        multi_location_devices = 0
        for mac, appearances in self.device_history.items():
            locations = set(a.location_id for a in appearances)
            if len(locations) >= 2:  # 2+ locations indicates following
                multi_location_devices += 1
        multi_location_rate = multi_location_devices / unique_devices if unique_devices > 0 else 0
        
        # Temporal clustering analysis
        clustered_devices = 0
        for mac, appearances in self.device_history.items():
            if len(appearances) >= 3:
                times = sorted([a.timestamp for a in appearances])
                intervals = [times[i] - times[i-1] for i in range(1, len(times))]
                if intervals:
                    avg_interval = sum(intervals) / len(intervals)
                    variance = sum((i - avg_interval) ** 2 for i in intervals) / len(intervals)
                    if variance < 3600:  # Low variance = clustered timing
                        clustered_devices += 1
        temporal_clustering = clustered_devices / unique_devices if unique_devices > 0 else 0
        
        # Off-hours activity analysis
        off_hours_appearances = 0
        for appearance in self.appearances:
            hour = datetime.fromtimestamp(appearance.timestamp).hour
            if hour >= 22 or hour <= 6:  # 10 PM to 6 AM
                off_hours_appearances += 1
        off_hours_rate = off_hours_appearances / total_appearances if total_appearances > 0 else 0
        
        # Probe pattern anomaly analysis
        anomalous_devices = 0
        suspicious_patterns = ['surveillance', 'monitor', 'track', 'spy', 'watch', 'police', 'fbi']
        for mac, appearances in self.device_history.items():
            all_ssids = []
            for appearance in appearances:
                all_ssids.extend(appearance.ssids_probed)
            
            unique_ssids = len(set(all_ssids))
            suspicious_count = sum(1 for ssid in set(all_ssids) 
                                 if any(pattern in ssid.lower() for pattern in suspicious_patterns))
            
            if unique_ssids > 20 or suspicious_count > 0:
                anomalous_devices += 1
        
        probe_anomaly_rate = anomalous_devices / unique_devices if unique_devices > 0 else 0
        
        return {
            'total_appearances': total_appearances,
            'unique_devices': unique_devices,
            'unique_locations': unique_locations,
            'analysis_duration_hours': analysis_duration_hours,
            'persistence_rate': persistence_rate,
            'multi_location_rate': multi_location_rate,
            'temporal_clustering': temporal_clustering,
            'off_hours_rate': off_hours_rate,
            'probe_anomaly_rate': probe_anomaly_rate,
        }
    
    def _format_detailed_device_analysis(self, device: SuspiciousDevice, persistence_level: str) -> str:
        """Format detailed analysis for a suspicious device with clear explanations"""
        lines = []
        
        # Device header
        threat_emoji = {"CRITICAL": "🚨", "HIGH": "⚠️", "MEDIUM": "🟡", "LOW": "🔵"}
        emoji = threat_emoji.get(persistence_level, "⚪")
        
        lines.append(f"#### {emoji} Device Analysis: `{device.mac}`")
        lines.append("")
        lines.append("*A MAC address is like a unique fingerprint for each wireless device (phone, laptop, etc.)*")
        lines.append("")
        lines.append("**📊 Heuristic Persistence Analysis:**")
        lines.append(f"- **Pattern Type:** {persistence_level} FREQUENCY")
        lines.append(f"- **Heuristic Persistence Score:** {device.persistence_score:.3f}/1.000 *(Higher = More Persistent)*")
        lines.append(f"- **Pattern Analysis:** {'📊 High-frequency appearance pattern' if persistence_level == 'CRITICAL' else '📈 Notable appearance pattern' if persistence_level == 'HIGH' else '📋 Low-frequency pattern'}")
        lines.append("")
        
        # Temporal analysis with explanations
        duration = device.last_seen - device.first_seen
        duration_hours = duration.total_seconds() / 3600
        lines.append("**⏰ Time-Based Observation Analysis:**")
        lines.append("*This shows how long the device has been observed and how often it appears*")
        lines.append("")
        lines.append(f"- **Total Observation Period:** {duration_hours:.1f} hours ({duration.days} days)")
        lines.append(f"- **First Time Spotted:** {device.first_seen.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"- **Most Recent Observation:** {device.last_seen.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"- **Total Appearances:** {device.total_appearances} times")
        lines.append(f"- **How Often It Appears:** {device.total_appearances / max(duration_hours, 1):.2f} times per hour")
        lines.append("")
        if device.total_appearances > 10:
            lines.append("  📊 **Analysis:** This device appears very frequently.")
        elif device.total_appearances > 5:
            lines.append("  📊 **Analysis:** This device appears regularly.")
        else:
            lines.append("  📊 **Analysis:** Low appearance count.")
        lines.append("")
        
        # Geographic analysis with explanations
        lines.append("**🗺️ Location Label Analysis:**")
        lines.append("*This shows which location labels were associated with the observations*")
        lines.append("")
        lines.append(f"- **Location Labels Observed:** {len(device.locations_seen)}")
        lines.append(f"- **Specific Locations:** {', '.join(device.locations_seen)}")
        if len(device.locations_seen) > 1:
            lines.append(f"- **Multi-location Observation:** Observed across {len(device.locations_seen)} location labels")
            lines.append("  ℹ️ This observation does not establish following, identity, stalking, surveillance, coordination, or intent.")
        else:
            lines.append(f"- **Multi-location Observation:** Observed in one location label")
        lines.append("")
        
        # Behavioral indicators
        lines.append("**Behavioral Review Indicators:**")
        for i, reason in enumerate(device.reasons, 1):
            lines.append(f"  {i}. {reason}")
        lines.append("")
        
        # Activity timeline (enhanced)
        lines.append("**Recent Activity Timeline:**")
        recent_appearances = sorted(device.appearances, key=lambda a: a.timestamp, reverse=True)[:10]
        for appearance in recent_appearances:
            dt = datetime.fromtimestamp(appearance.timestamp)
            ssids = ', '.join(appearance.ssids_probed[:2]) if appearance.ssids_probed else 'No probes'
            lines.append(f"- `{dt.strftime('%Y-%m-%d %H:%M:%S')}` | Location: `{appearance.location_id}` | SSIDs: {ssids}")
        
        if len(device.appearances) > 10:
            lines.append(f"- *... and {len(device.appearances) - 10} additional appearances*")
        lines.append("")
        
        # General recommendations (liability-safe)
        lines.append("**General Recommendations:**")
        lines.append("- 📊 **Data Analysis**: This device showed repeated appearances in your wireless environment")
        lines.append("- 🔍 **Consider**: This pattern might be worth noting or monitoring")
        lines.append("- 📝 **Documentation**: You could keep a log of when/where this device appears")
        lines.append("- 🤔 **Context**: Repeated identifiers can come from many sources")
        lines.append("- ⚖️ **Disclaimer**: These are heuristic observations only")
        lines.append("")
        lines.append("---")
        lines.append("")
        
        return '\n'.join(lines)
    
    def _analyze_temporal_patterns(self, suspicious_devices: List[SuspiciousDevice]) -> List[str]:
        """Analyze temporal patterns across suspicious devices"""
        patterns = []
        
        if not suspicious_devices:
            return ["No suspicious devices to analyze"]
        
        # Work hours analysis
        work_hour_devices = 0
        off_hour_devices = 0
        regular_interval_devices = 0
        
        for device in suspicious_devices:
            hours = [datetime.fromtimestamp(a.timestamp).hour for a in device.appearances]
            work_hours = [h for h in hours if 9 <= h <= 17]
            off_hours = [h for h in hours if h >= 22 or h <= 6]
            
            work_hour_ratio = len(work_hours) / len(hours) if hours else 0
            off_hour_ratio = len(off_hours) / len(hours) if hours else 0
            
            if work_hour_ratio > 0.7:
                work_hour_devices += 1
            if off_hour_ratio > 0.7:
                off_hour_devices += 1
            
            # Check for regular intervals
            if len(device.appearances) >= 3:
                timestamps = sorted([a.timestamp for a in device.appearances])
                intervals = [timestamps[i] - timestamps[i-1] for i in range(1, len(timestamps))]
                if len(intervals) > 1:
                    avg_interval = sum(intervals) / len(intervals)
                    variance = sum((i - avg_interval) ** 2 for i in intervals) / len(intervals)
                    if variance < (avg_interval * 0.1):  # Low variance = regular
                        regular_interval_devices += 1
        
        if work_hour_devices > 0:
            patterns.append(f"**{work_hour_devices} devices** show activity concentrated in daytime hours (9 AM - 5 PM)")
        
        if off_hour_devices > 0:
            patterns.append(f"**{off_hour_devices} devices** show activity concentrated outside daytime hours (10 PM - 6 AM)")
        
        if regular_interval_devices > 0:
            patterns.append(f"**{regular_interval_devices} devices** appear at highly regular intervals")
        
        # Day of week analysis
        weekday_heavy = 0
        weekend_heavy = 0
        for device in suspicious_devices:
            weekdays = []
            weekends = []
            for appearance in device.appearances:
                day_of_week = datetime.fromtimestamp(appearance.timestamp).weekday()
                if day_of_week < 5:  # Monday = 0, Friday = 4
                    weekdays.append(appearance)
                else:
                    weekends.append(appearance)
            
            if len(weekdays) > len(weekends) * 2:
                weekday_heavy += 1
            elif len(weekends) > len(weekdays):
                weekend_heavy += 1
        
        if weekday_heavy > 0:
            patterns.append(f"**{weekday_heavy} devices** appear primarily on weekdays")
        
        if weekend_heavy > 0:
            patterns.append(f"**{weekend_heavy} devices** appear primarily on weekends")

        if not patterns:
            patterns.append("No significant temporal patterns detected across reviewed devices")
        
        return patterns
    
    def _analyze_geographic_patterns(self, suspicious_devices: List[SuspiciousDevice]) -> List[str]:
        """Analyze geographic tracking patterns"""
        patterns = []
        
        if not suspicious_devices:
            return ["No suspicious devices to analyze"]
        
        # Multi-location tracking analysis
        multi_location_count = len([d for d in suspicious_devices if len(d.locations_seen) > 1])
        if multi_location_count > 0:
            patterns.append(f"**{multi_location_count} devices** observed across multiple location labels")
        
        # Location correlation analysis
        location_frequency = {}
        for device in suspicious_devices:
            for location in device.locations_seen:
                location_frequency[location] = location_frequency.get(location, 0) + 1
        
        repeated_locations = [loc for loc, count in location_frequency.items() if count > 1]
        if repeated_locations:
            patterns.append(f"**Repeated location labels observed:** {', '.join(repeated_locations)}")
        
        # Quick transition analysis
        quick_followers = 0
        for device in suspicious_devices:
            if len(device.appearances) > 1:
                sorted_appearances = sorted(device.appearances, key=lambda a: a.timestamp)
                for i in range(1, len(sorted_appearances)):
                    prev_loc = sorted_appearances[i-1].location_id
                    curr_loc = sorted_appearances[i].location_id
                    time_diff = sorted_appearances[i].timestamp - sorted_appearances[i-1].timestamp
                    
                    # If location changed within 30 minutes = quick transition
                    if prev_loc != curr_loc and time_diff < 1800:
                        quick_followers += 1
                        break

        if quick_followers > 0:
            patterns.append(f"**{quick_followers} devices** show rapid location-label transitions (< 30 minutes)")

        if not patterns:
            patterns.append("No significant geographic patterns detected across reviewed devices")
        
        return patterns
    
    def _analyze_device_correlations(self, suspicious_devices: List[SuspiciousDevice]) -> List[str]:
        """Analyze correlations between suspicious devices"""
        correlations = []
        
        if len(suspicious_devices) < 2:
            return correlations
        
        # Find devices that appear at same times/locations
        for i, device1 in enumerate(suspicious_devices):
            for j, device2 in enumerate(suspicious_devices[i+1:], i+1):
                
                # Location correlation
                common_locations = set(device1.locations_seen) & set(device2.locations_seen)
                if len(common_locations) > 1:
                    correlations.append(f"**{device1.mac}** and **{device2.mac}** both appear at: {', '.join(common_locations)}")
                
                # Temporal correlation (within 1 hour)
                temporal_matches = 0
                for app1 in device1.appearances:
                    for app2 in device2.appearances:
                        time_diff = abs(app1.timestamp - app2.timestamp)
                        if time_diff < 3600 and app1.location_id == app2.location_id:
                            temporal_matches += 1
                
                if temporal_matches > 2:
                    correlations.append(f"**{device1.mac}** and **{device2.mac}** appear together {temporal_matches} times at shared location labels")
        
        return correlations
    
    def generate_surveillance_report(self, output_file: str) -> str:
        """Generate comprehensive surveillance detection report with advanced analytics"""
        suspicious_devices = self.analyze_surveillance_patterns()
        
        # Generate comprehensive statistics
        stats = self._generate_analysis_statistics()
        
        report = []
        
        # Professional header with metadata
        report.append("# 🛡️ CYT HEURISTIC PERSISTENCE REVIEW")
        report.append("## Personal Privacy Review")
        report.append("")
        report.append("### 📖 What This Report Does")
        report.append("")
        report.append("This analysis examines wireless devices around you to describe repeated heuristic observations. Here's how it works:")
        report.append("")
        report.append("**🔍 What We Monitor:**")
        report.append("- Wireless devices (phones, laptops, other identifiers) that appear near you")
        report.append("- Whether the same identifiers show up repeatedly or across different location labels")
        report.append("- Repeated patterns that may justify a heuristic review")
        report.append("")
        report.append("**🎯 What We Look For:**")
        report.append("- **Persistence:** Devices that keep appearing over time")
        report.append("- **Multi-location observations:** Devices that appear under more than one location label")
        report.append("- **Timing patterns:** Devices active during unusual hours or at regular intervals")
        report.append("- **Correlation patterns:** Repeated co-occurrence across labels or time windows")
        report.append("")
        report.append("**Notice:** Aggregated source data may not correspond to distinct sightings.")
        report.append("**Notice:** This report does not establish identity or intent.")
        report.append("")
        report.append("---")
        report.append("")
        report.append("## 📊 ANALYSIS SUMMARY")
        report.append(f"**Report Generated:** {datetime.now().strftime('%A, %B %d, %Y at %H:%M:%S')}")
        report.append(f"**Analysis Engine:** CYT Heuristic Observation Review System v2.1")
        report.append(f"**Analysis Type:** Automated Repeated-Observation Review")
        report.append("")
        
        # Threat Level Assessment
        if not suspicious_devices:
            persistence_level = "🟢 **LOW HEURISTIC PERSISTENCE**"
            threat_color = "NEUTRAL"
        else:
            high_persistence_count = len([d for d in suspicious_devices if d.persistence_score > 0.8])
            medium_threat_count = len([d for d in suspicious_devices if 0.6 <= d.persistence_score <= 0.8])
            
            if high_persistence_count > 0:
                persistence_level = "🔴 **HIGH HEURISTIC PERSISTENCE**"
                threat_color = "HIGH"
            elif medium_threat_count > 2:
                persistence_level = "🟡 **MODERATE HEURISTIC PERSISTENCE**"
                threat_color = "ELEVATED"
            else:
                persistence_level = "🟡 **ELEVATED HEURISTIC PERSISTENCE**"
                threat_color = "ELEVATED"
        
        report.append("## 📊 ANALYSIS OVERVIEW")
        report.append("")
        report.append(f"**Heuristic Persistence Band:** {persistence_level}")
        report.append(f"**Review Band:** {threat_color}")
        report.append(f"**Monitoring Period:** {stats['analysis_duration_hours']:.1f} hours")
        report.append(f"**Total Device Appearances:** {stats['total_appearances']:,}")
        report.append(f"**Unique Devices Tracked:** {stats['unique_devices']:,}")
        report.append(f"**Identifiers Meeting Review Threshold:** {len(suspicious_devices)}")
        report.append(f"**Geographic Locations Analyzed:** {stats['unique_locations']}")
        report.append("")
        
        # Advanced Analytics Dashboard with explanations
        report.append("## 📊 HEURISTIC ACTIVITY REVIEW DASHBOARD")
        report.append("")
        report.append("*This dashboard summarizes repeated identifier and location-label observations.*")
        report.append("*It summarizes heuristic review signals and does not confirm identity or intent.*")
        report.append("")
        report.append("| Metric | Value | Risk Indicator | What This Means |")
        report.append("|--------|-------|----------------|-----------------|")
        report.append(f"| **Device Persistence Rate** | {stats['persistence_rate']:.1%} | {'🔴 Higher' if stats['persistence_rate'] > 0.3 else '🟡 Moderate' if stats['persistence_rate'] > 0.15 else '🟢 Lower'} | Percentage of devices that appear repeatedly over time. |")
        report.append(f"| **Multi-Location Observation** | {stats['multi_location_rate']:.1%} | {'🔴 Higher' if stats['multi_location_rate'] > 0.2 else '🟡 Moderate' if stats['multi_location_rate'] > 0.1 else '🟢 Lower'} | Percentage of devices observed under more than one location label. |")
        report.append(f"| **Analysis Time Period** | {stats['analysis_duration_hours']:.1f} hours | {'🟢 Longer' if stats['analysis_duration_hours'] > 12 else '🟡 Moderate' if stats['analysis_duration_hours'] > 6 else '🔴 Short'} | How long the monitoring period covered. |")
        report.append("")
        
        # Add explanatory section
        report.append("### 🤔 What Do These Numbers Mean?")
        report.append("")
        report.append("**Device Persistence Rate:** Higher values mean more repeated observations of the same identifiers.")
        report.append("- Repeated appearance can reflect many different causes")
        report.append("- The score is a heuristic review signal, not proof")
        report.append("")
        report.append("**Multi-Location Observation:** This shows whether the same identifier was observed under multiple location labels.")
        report.append("- It does not establish identity or intent")
        report.append("")
        report.append("**Analysis Time Period:** Shows how long the monitoring covered.")
        report.append("- Short periods may miss patterns")
        report.append("- Longer periods capture more observations")
        report.append("")
        report.append("**Location Labels:** The location label is an analysis label, not proof of precise device position.")
        report.append("")
        report.append("**Limitations:**")
        report.append("- Aggregated source data may combine rows that do not represent distinct sightings.")
        report.append("- MAC randomization may split one physical device across multiple identifiers.")
        report.append("- Shared devices and static devices can both create repeated observations.")
        report.append("- Location labels are analysis labels rather than proof of precise device position.")
        report.append("- The output does not establish identity or intent.")
        report.append("")
        
        if suspicious_devices:
            report.append("## 📊 HEURISTIC PERSISTENCE ANALYSIS")
            report.append("")
            report.append("*The following devices showed repeated wireless activity patterns in your environment.*")
            report.append("")
            
            # Explain threat scoring system
            report.append("### 🎯 How Heuristic Persistence Scores Work")
            report.append("")
            report.append("Each device gets a **Heuristic Persistence Score** from 0.0 to 1.0 based on repeated-observation behaviors:")
            report.append("")
            report.append("**🟢 Low (0.0-0.5):** Limited repeated observation")
            report.append("**🟡 Moderate (0.6-0.7):** Multiple observations or labels")
            report.append("**🟠 Elevated (0.8-0.9):** Strong repeated-observation pattern")
            report.append("**🔴 High (0.9-1.0):** Very persistent repeated observation across labels and time windows")
            report.append("")
            report.append("**What Raises the Heuristic Review Score:**")
            report.append("- **Appears repeatedly** at the same location over hours/days")
            report.append("- **Observed across multiple location labels**")
            report.append("- **Regular timing** - shows up at predictable times")
            report.append("- **Night activity** - appears during unusual hours")  
            report.append("- **SSID anomalies** - searches for networks with unusual names")
            report.append("")
            
            # Threat classification
            critical_persistent_devices = [d for d in suspicious_devices if d.persistence_score > 0.9]
            high_persistences = [d for d in suspicious_devices if 0.8 <= d.persistence_score <= 0.9]
            medium_persistent_devices = [d for d in suspicious_devices if 0.6 <= d.persistence_score < 0.8]
            low_persistent_devices = [d for d in suspicious_devices if d.persistence_score < 0.6]
            
            if critical_persistent_devices:
                report.append("### 📊 VERY HIGH HEURISTIC PERSISTENCE DEVICES (Score > 0.9)")
                report.append("*These devices appeared very frequently in your wireless environment*")
                report.append("")
                for device in critical_persistent_devices:
                    report.append(self._format_detailed_device_analysis(device, "CRITICAL"))
            
            if high_persistences:
                report.append("### 📈 HIGH HEURISTIC PERSISTENCE DEVICES (Score 0.8-0.9)")
                report.append("*These devices appeared frequently and might be worth noting*")
                report.append("")
                for device in high_persistences:
                    report.append(self._format_detailed_device_analysis(device, "HIGH"))
            
            if medium_persistent_devices:
                report.append("### 📋 MODERATE HEURISTIC PERSISTENCE DEVICES (Score 0.6-0.8)")
                report.append("*These devices showed some repeated wireless activity*")
                report.append("")
                for device in medium_persistent_devices:
                    report.append(self._format_detailed_device_analysis(device, "MEDIUM"))
            
            # Behavioral pattern analysis
            report.append("## 🔍 BEHAVIORAL REVIEW ANALYSIS")
            report.append("")
            
            # Temporal analysis
            report.append("### ⏰ Temporal Review Patterns")
            temporal_patterns = self._analyze_temporal_patterns(suspicious_devices)
            for pattern in temporal_patterns:
                report.append(f"- {pattern}")
            report.append("")
            
            # Geographic analysis
            report.append("### 🗺️ Location-Label Review Patterns")
            geo_patterns = self._analyze_geographic_patterns(suspicious_devices)
            for pattern in geo_patterns:
                report.append(f"- {pattern}")
            report.append("")
            
            # Device correlation analysis
            report.append("### 🔗 Device Co-Occurrence Matrix")
            correlations = self._analyze_device_correlations(suspicious_devices)
            if correlations:
                report.append("*Devices that appear together may justify review of co-occurrence patterns*")
                report.append("")
                for correlation in correlations:
                    report.append(f"- {correlation}")
            else:
                report.append("- No significant co-occurrence patterns detected")
            report.append("")
            
        else:
            report.append("## NO IDENTIFIERS MET THE HEURISTIC REVIEW THRESHOLD")
            report.append("")
            report.append("**Analysis Result:** No identifiers met the heuristic review threshold.")
            report.append("")
            report.append("**Important:** This result does not rule out repeated observations outside the review window. This result does not establish environmental safety.")
            report.append("")
            report.append("**Assessment Details:**")
            report.append(f"- **{stats['unique_devices']:,} unique devices** analyzed across **{stats['unique_locations']} location labels**")
            report.append(f"- **{stats['total_appearances']:,} device appearances** processed over **{stats['analysis_duration_hours']:.1f} hours**")
            report.append("- No identifiers exceeded the heuristic review threshold")
            report.append("- No multi-location review signals were produced")
            report.append("- Temporal review signals did not cross the threshold")
            report.append("")
        
        # Advanced countermeasures and recommendations with clear explanations
        report.append("## 🛡️ PRIVACY FOLLOW-UP GUIDE")
        report.append("")
        report.append("*Based on your analysis results, here are specific actions you can take to protect yourself.*")
        report.append("")
        
        if suspicious_devices:
            high_persistence = [d for d in suspicious_devices if d.persistence_score > 0.8]
            if high_persistence:
                report.append("### 📊 HIGH HEURISTIC-PERSISTENCE IDENTIFIERS")
                report.append("**ℹ️ Some devices showed high-frequency appearances - here are some general privacy tips:**")
                report.append("")
                report.append("#### 1. 📱 Consider Protecting Your Devices")
                report.append("**MAC Address Randomization** *(Could make your devices harder to track)*:")
                report.append("- **iPhone/iPad:** Settings → Wi-Fi → Tap info (i) next to network → Consider enabling 'Private Address'")
                report.append("- **Android:** Settings → Wi-Fi → Advanced → Consider enabling 'Use randomized MAC'")
                report.append("- **Windows:** Settings → Network & Internet → Wi-Fi → Manage known networks → Properties → Consider enabling 'Use random hardware addresses'")
                report.append("- **Mac:** System Preferences → Network → Wi-Fi → Advanced → Consider enabling 'Use private Wi-Fi address'")
                report.append("")
                report.append("**When You Might Consider Disabling Wi-Fi:**")
                report.append("- You could turn off Wi-Fi when walking around in public")
                report.append("- You might use cellular data instead when you want to reduce identifier exposure")
                report.append("- You could consider a Faraday bag (signal-blocking pouch) for your phone in sensitive situations")
                report.append("")
                
                report.append("#### 2. 🚶 Consider Changing Your Patterns")
                report.append("**You Might Consider Varying Your Routines:**")
                report.append("- You could take different routes to work/home each day")
                report.append("- You might change the times you leave and arrive")
                report.append("- You could visit different stores/restaurants than usual")
                report.append("- If possible, you might consider staying with friends/family temporarily")
                report.append("")
                report.append("**Why This Could Help:** Repeated observation often relies on predictable patterns. By changing your routine, you could reduce pattern continuity.")
                report.append("")
                
                report.append("#### 3. 📞 Consider Getting Help")
                report.append("**You Might Consider Documenting Everything:**")
                report.append("- You could save this report with timestamps")
                report.append("- You could keep a log of when/where you notice repeated observations")
                report.append("- You might ask for technical support or report interpretation if you want another review")
                report.append("")
        
        report.append("### 🔒 LONG-TERM PRIVACY PROTECTION")
        report.append("*These steps can help reduce future identifier exposure.*")
        report.append("")
        
        report.append("#### 📱 Consider Making Your Devices More Private")
        report.append("**Wi-Fi Settings You Might Consider:**")
        report.append("- You could enable MAC address randomization on your devices")
        report.append("- You might remove old Wi-Fi networks you don't use anymore")
        report.append("- You could turn off 'Auto-join' for public Wi-Fi networks")  
        report.append("- You might use a trusted VPN service when on public Wi-Fi")
        report.append("")
        
        report.append("#### 🚶 Consider Staying Unpredictable")
        report.append("**Daily Habits You Might Consider:**")
        report.append("- You could vary your daily routes when possible")
        report.append("- You might be aware of people or cars you see repeatedly")
        report.append("- You could trust your instincts if a situation feels off")
        report.append("- You might consider learning general privacy-preserving practices")
        report.append("")
        
        report.append("#### 🔍 Consider Continued Monitoring")
        report.append("**Using This Tool:**")
        report.append("- You could run CYT analysis regularly if you want to review repeated-observation patterns")
        report.append("- You might pay attention to devices that appear in multiple locations")
        report.append("- You could share reports with a technical support contact if patterns emerge")
        report.append("- You might keep logs of any suspicious activity")
        report.append("")
        
        report.append("#### ℹ️ Understanding the Technology")
        report.append("**How Identifier Reuse Works:**")
        report.append("- Devices broadcast unique identifiers (MAC addresses) when searching for Wi-Fi networks")
        report.append("- **Modern phones (iOS 14+, Android 10+) randomize these addresses** to protect privacy")
        report.append("- **Older devices or those with randomization disabled** still reveal their true MAC address")
        report.append("- Observers or logging systems could record these identifiers to track device movements")
        report.append("- This tool reviews patterns where the same identifiers appear repeatedly or across location labels")
        report.append("- **Note:** Randomized MAC addresses make tracking much harder but don't eliminate all risks")
        report.append("")
        
        # Technical appendix
        report.append("## 📋 TECHNICAL ANALYSIS APPENDIX")
        report.append("")
        report.append("### Detection Algorithm Parameters")
        report.append("```")
        report.append(f"Minimum Appearances Threshold: {self.thresholds['min_appearances']}")
        report.append(f"Minimum Time Span: {self.thresholds['min_time_span_hours']:.1f} hours")
        report.append(f"Minimum Persistence Score: {self.thresholds['min_persistence_score']}")
        report.append("```")
        report.append("")
        report.append("### Heuristic Review Notes")
        report.append(f"- Analysis based on **{len(self.appearances):,} data points**")
        report.append(f"- Heuristic review score is derived from repeated observations, time span, and location-label spread")
        report.append("")
        
        # Footer
        report.append("---")
        report.append("")
        report.append("*This report was generated by the CYT Heuristic Observation Review System.*")
        report.append("*For technical support or report interpretation, contact your security administrator.*")
        report.append("")
        report.append(f"**Report ID:** CYT-{datetime.now().strftime('%Y%m%d%H%M%S')}")
        report.append(f"**Classification:** CONFIDENTIAL - Personal Privacy Review")
        
        report_text = '\n'.join(report)
        
        # Save markdown report
        with open(output_file, 'w') as f:
            f.write(report_text)
        
        logger.info(f"Heuristic review report saved to: {output_file}")
        
        # Generate HTML version using pandoc
        html_file = output_file.replace('.md', '.html')
        try:
            import subprocess
            # Custom CSS for better styling
            css_content = """
            <style>
            body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif; 
                   max-width: 1200px; margin: 0 auto; padding: 20px; line-height: 1.6; }
            h1, h2, h3 { color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px; }
            table { border-collapse: collapse; width: 100%; margin: 20px 0; }
            th, td { border: 1px solid #ddd; padding: 12px; text-align: left; }
            th { background-color: #f8f9fa; font-weight: bold; }
            .emoji { font-size: 1.2em; }
            code { background-color: #f1f2f6; padding: 4px 8px; border-radius: 4px; }
            pre { background-color: #f8f9fa; padding: 15px; border-radius: 8px; overflow-x: auto; }
            blockquote { border-left: 4px solid #3498db; padding-left: 20px; margin-left: 0; 
                        background-color: #f8f9fa; padding: 15px 20px; border-radius: 0 8px 8px 0; }
            .threat-high { background-color: #ffe6e6; border-left: 4px solid #e74c3c; }
            .threat-medium { background-color: #fff3cd; border-left: 4px solid #f39c12; }
            .threat-low { background-color: #d4edda; border-left: 4px solid #27ae60; }
            </style>
            """
            
            # Run pandoc to convert markdown to HTML
            cmd = [
                'pandoc', 
                output_file,
                '-o', html_file,
                '--standalone',
                '--self-contained',
                '--metadata', f'title=CYT Surveillance Detection Report',
                '--css', '/dev/stdin'
            ]
            
            result = subprocess.run(cmd, input=css_content, text=True, capture_output=True)
            
            if result.returncode == 0:
                logger.info(f"HTML report generated: {html_file}")
            else:
                logger.warning(f"Failed to generate HTML report: {result.stderr}")
                
        except Exception as e:
            logger.warning(f"Could not generate HTML report: {e}")
        
        return report_text

def load_appearances_from_kismet(db_path: str, detector: SurveillanceDetector, 
                               location_id: str = "unknown") -> int:
    """Load device appearances from Kismet database"""
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
                
                detector.add_device_appearance(
                    mac=mac,
                    timestamp=timestamp,
                    location_id=location_id,
                    ssids_probed=ssids_probed,
                    device_type=device_type
                )
                count += 1
            
            logger.info(f"Loaded {count} device appearances from {db_path}")
            return count
            
    except Exception as e:
        logger.error(f"Error loading from Kismet database: {e}")
        return 0
