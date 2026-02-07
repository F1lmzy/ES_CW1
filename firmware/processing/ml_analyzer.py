"""
ML-Based Sleep Pattern Analyzer

Analyzes historical sleep data using machine learning techniques:
- K-Means clustering to categorize nights into quality buckets
- Linear regression for trend analysis
- Rule-based suggestion engine

Dependencies: pandas, scikit-learn, numpy
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import StandardScaler

logger = logging.getLogger(__name__)


class SleepQuality(Enum):
    """Sleep quality categories from clustering"""
    EXCELLENT = "excellent"
    GOOD = "good"
    POOR = "poor"
    RESTLESS = "restless"


@dataclass
class NightlySummary:
    """Aggregated sleep metrics for a single night"""
    date: str
    total_duration_hours: float
    sleep_time_hours: float  # Time spent in ASLEEP state
    awake_time_hours: float  # Time spent in AWAKE state
    movement_events: int
    restlessness_score: float  # Normalized 0-100
    sleep_quality: Optional[SleepQuality] = None
    efficiency: float = 0.0  # Sleep time / total duration


@dataclass
class SleepAnalysis:
    """Complete sleep analysis results"""
    nights: List[NightlySummary]
    overall_quality: SleepQuality
    trend_direction: str  # "improving", "declining", "stable"
    trend_slope: float
    average_sleep_duration: float
    average_restlessness: float
    recommendations: List[str] = field(default_factory=list)
    insights: Dict[str, Any] = field(default_factory=dict)


class SleepMLAnalyzer:
    """
    Machine Learning Sleep Pattern Analyzer
    
    Designed to run on Raspberry Pi 2 - uses lightweight models:
    - K-Means: O(n*k*i) complexity, very fast
    - Linear Regression: O(n), linear time
    """
    
    def __init__(self):
        self.scaler = StandardScaler()
        self.clusterer = None
        self.trend_model = None
        
    def analyze(self, readings: List[Dict], n_clusters: int = 3) -> SleepAnalysis:
        """
        Main analysis pipeline.
        
        Args:
            readings: List of reading dictionaries from Supabase
            n_clusters: Number of quality buckets (default 3)
            
        Returns:
            SleepAnalysis with ML insights and recommendations
        """
        if not readings:
            logger.warning("No readings provided for analysis")
            return self._empty_analysis()
        
        # Step 1: Aggregate readings into nightly summaries
        nightly_data = self._aggregate_nights(readings)
        if not nightly_data:
            return self._empty_analysis()
        
        # Step 2: Feature extraction and clustering
        self._cluster_nights(nightly_data, n_clusters)
        
        # Step 3: Trend analysis
        trend = self._analyze_trends(nightly_data)
        
        # Step 4: Generate insights
        insights = self._generate_insights(nightly_data, trend)
        
        # Step 5: Build recommendations
        recommendations = self._generate_recommendations(nightly_data, trend, insights)
        
        return SleepAnalysis(
            nights=nightly_data,
            overall_quality=self._get_overall_quality(nightly_data),
            trend_direction=trend["direction"],
            trend_slope=trend["slope"],
            average_sleep_duration=np.mean([n.sleep_time_hours for n in nightly_data]),
            average_restlessness=np.mean([n.restlessness_score for n in nightly_data]),
            recommendations=recommendations,
            insights=insights
        )
    
    def _aggregate_nights(self, readings: List[Dict]) -> List[NightlySummary]:
        """
        Aggregate raw readings into nightly sleep summaries.
        
        Groups readings by date and calculates:
        - Total time in bed
        - Time spent in each sleep state
        - Movement frequency
        - Sleep efficiency
        """
        df = pd.DataFrame(readings)
        
        if df.empty:
            return []
        
        # Convert timestamp to datetime
        df['timestamp'] = pd.to_datetime(df.get('created_at', df.get('timestamp')))
        
        # Group by "sleep night" - from 6 PM to 6 PM next day
        # This handles overnight sleep sessions that span midnight
        df['sleep_night'] = df['timestamp'].apply(
            lambda x: (x - pd.Timedelta(hours=18)).date()
        )
        
        nights = []
        for date, group in df.groupby('sleep_night'):
            # Sort by timestamp
            group = group.sort_values('timestamp')
            
            # Calculate duration
            if len(group) > 1:
                total_duration = (group['timestamp'].max() - group['timestamp'].min()).total_seconds() / 3600
            else:
                total_duration = 0
            
            # Count states
            state_counts = group['state'].value_counts()
            
            # Time estimates based on reading frequency
            # Assume readings are roughly evenly spaced during the night
            avg_interval_minutes = total_duration * 60 / len(group) if len(group) > 1 else 5
            
            # Calculate time in each state (approximate)
            sleep_time = state_counts.get('Asleep', 0) * avg_interval_minutes / 60
            awake_time = state_counts.get('Present (Awake)', 0) * avg_interval_minutes / 60
            moving_time = state_counts.get('Tossing/Turning', 0) * avg_interval_minutes / 60
            
            # Movement events (significant variance changes)
            movement_events = len(group[group['variance'] > group['variance'].quantile(0.8)])
            
            # Restlessness score (0-100, higher = more restless)
            total_time = sleep_time + awake_time + moving_time
            if total_time > 0:
                restlessness = (moving_time / total_time) * 100 + (movement_events / len(group)) * 20
                restlessness = min(restlessness, 100)  # Cap at 100
            else:
                restlessness = 0
            
            # Efficiency: sleep time / total time in bed
            efficiency = (sleep_time / total_time * 100) if total_time > 0 else 0
            
            nights.append(NightlySummary(
                date=str(date),
                total_duration_hours=total_time,
                sleep_time_hours=sleep_time,
                awake_time_hours=awake_time + moving_time,
                movement_events=movement_events,
                restlessness_score=round(restlessness, 1),
                efficiency=round(efficiency, 1)
            ))
        
        return sorted(nights, key=lambda x: x.date)
    
    def _cluster_nights(self, nights: List[NightlySummary], n_clusters: int = 3):
        """
        Apply K-Means clustering to categorize nights by quality.
        
        Features:
        - sleep_time_hours (normalized)
        - restlessness_score (normalized)
        - efficiency (normalized)
        """
        if len(nights) < n_clusters:
            # Not enough data, assign all as "good"
            for night in nights:
                night.sleep_quality = SleepQuality.GOOD
            return
        
        # Extract features
        features = np.array([
            [n.sleep_time_hours, n.restlessness_score, n.efficiency]
            for n in nights
        ])
        
        # Scale features
        scaled_features = self.scaler.fit_transform(features)
        
        # Cluster
        self.clusterer = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
        labels = self.clusterer.fit_predict(scaled_features)
        
        # Map clusters to quality levels based on feature centroids
        centroids = self.clusterer.cluster_centers_
        
        # Calculate quality score for each centroid (higher sleep, lower restlessness = better)
        # Unscale to original feature space for interpretation
        centroids_unscaled = self.scaler.inverse_transform(centroids)
        quality_scores = []
        
        for centroid in centroids_unscaled:
            sleep_time, restlessness, efficiency = centroid
            # Simple scoring: weight sleep duration and efficiency positively, restlessness negatively
            score = (sleep_time * 0.4) + (efficiency * 0.4) - (restlessness * 0.02)
            quality_scores.append(score)
        
        # Sort clusters by quality score
        sorted_indices = np.argsort(quality_scores)
        
        # Map to quality enum
        cluster_to_quality = {}
        n_clusters_actual = len(sorted_indices)
        
        if n_clusters_actual >= 3:
            cluster_to_quality[sorted_indices[0]] = SleepQuality.POOR
            cluster_to_quality[sorted_indices[-1]] = SleepQuality.EXCELLENT
            for i in sorted_indices[1:-1]:
                cluster_to_quality[i] = SleepQuality.GOOD
        elif n_clusters_actual == 2:
            cluster_to_quality[sorted_indices[0]] = SleepQuality.POOR
            cluster_to_quality[sorted_indices[1]] = SleepQuality.GOOD
        else:
            cluster_to_quality[sorted_indices[0]] = SleepQuality.GOOD
        
        # Assign qualities to nights
        for night, label in zip(nights, labels):
            night.sleep_quality = cluster_to_quality.get(label, SleepQuality.GOOD)
    
    def _analyze_trends(self, nights: List[NightlySummary]) -> Dict:
        """
        Analyze sleep quality trends over time using linear regression.
        
        Returns:
            Dictionary with trend direction and slope
        """
        if len(nights) < 3:
            return {"direction": "stable", "slope": 0.0}
        
        # Create quality score for each night (1-4 scale)
        quality_scores = []
        for night in nights:
            if night.sleep_quality == SleepQuality.EXCELLENT:
                quality_scores.append(4)
            elif night.sleep_quality == SleepQuality.GOOD:
                quality_scores.append(3)
            elif night.sleep_quality == SleepQuality.RESTLESS:
                quality_scores.append(2)
            else:
                quality_scores.append(1)
        
        # Linear regression on day index vs quality score
        X = np.arange(len(nights)).reshape(-1, 1)
        y = np.array(quality_scores)
        
        self.trend_model = LinearRegression()
        self.trend_model.fit(X, y)
        
        slope = self.trend_model.coef_[0]
        
        # Interpret trend
        if slope > 0.1:
            direction = "improving"
        elif slope < -0.1:
            direction = "declining"
        else:
            direction = "stable"
        
        return {
            "direction": direction,
            "slope": float(slope),
            "r_squared": self.trend_model.score(X, y)
        }
    
    def _generate_insights(self, nights: List[NightlySummary], trend: Dict) -> Dict:
        """Generate data-driven insights"""
        insights = {}
        
        if not nights:
            return insights
        
        # Best and worst nights
        sorted_by_quality = sorted(nights, key=lambda x: 
            (x.sleep_time_hours, -x.restlessness_score), reverse=True)
        
        insights["best_night"] = sorted_by_quality[0].date if sorted_by_quality else None
        insights["worst_night"] = sorted_by_quality[-1].date if len(sorted_by_quality) > 1 else None
        
        # Consistency metrics
        sleep_durations = [n.sleep_time_hours for n in nights]
        insights["consistency_score"] = 100 - np.std(sleep_durations) * 10  # Higher = more consistent
        insights["consistency_score"] = max(0, min(100, insights["consistency_score"]))
        
        # Weekday vs weekend patterns
        df = pd.DataFrame([{"date": n.date, "sleep_time": n.sleep_time_hours, 
                           "quality": n.sleep_quality.value} for n in nights])
        df['date'] = pd.to_datetime(df['date'])
        df['is_weekend'] = df['date'].dt.dayofweek >= 5
        
        weekend_avg = df[df['is_weekend']]['sleep_time'].mean() if df['is_weekend'].any() else 0
        weekday_avg = df[~df['is_weekend']]['sleep_time'].mean() if (~df['is_weekend']).any() else 0
        
        insights["weekend_weekday_diff"] = weekend_avg - weekday_avg
        insights["sleeps_more_on_weekends"] = weekend_avg > weekday_avg + 0.5
        
        # Restlessness patterns
        restlessness_by_day = [(n.date, n.restlessness_score) for n in nights]
        high_restless_days = [d for d, r in restlessness_by_day if r > 50]
        insights["high_restlessness_days"] = high_restless_days
        insights["average_restlessness"] = np.mean([n.restlessness_score for n in nights])
        
        return insights
    
    def _generate_recommendations(self, nights: List[NightlySummary], 
                                 trend: Dict, insights: Dict) -> List[str]:
        """Generate actionable sleep recommendations"""
        recommendations = []
        
        if not nights:
            return ["Insufficient data for recommendations. Collect at least 3-4 nights of data."]
        
        # Trend-based recommendations
        if trend["direction"] == "declining":
            recommendations.append(
                "Your sleep quality is trending down over the week. Consider maintaining a more consistent sleep schedule."
            )
        elif trend["direction"] == "improving":
            recommendations.append(
                "Great progress! Your sleep quality is improving. Keep up your current habits."
            )
        
        # Consistency recommendations
        if insights.get("consistency_score", 100) < 50:
            recommendations.append(
                "Your sleep duration varies significantly from night to night. Try to go to bed and wake up at the same time daily."
            )
        
        # Weekend pattern
        if insights.get("sleeps_more_on_weekends"):
            recommendations.append(
                "You sleep significantly more on weekends (social jetlag). Consider adjusting your weekday bedtime to get more consistent rest."
            )
        
        # Restlessness recommendations
        high_restless = insights.get("high_restlessness_days", [])
        if len(high_restless) >= 2:
            recommendations.append(
                f"High restlessness detected on {len(high_restless)} nights ({', '.join(high_restless)}). "
                "Check for environmental factors like room temperature, noise, or late caffeine intake."
            )
        
        # Duration recommendations
        avg_sleep = np.mean([n.sleep_time_hours for n in nights])
        if avg_sleep < 6:
            recommendations.append(
                f"Your average sleep time ({avg_sleep:.1f} hours) is below the recommended 7-9 hours. "
                "Aim to extend your sleep duration for better health."
            )
        elif avg_sleep > 10:
            recommendations.append(
                f"Your average sleep time ({avg_sleep:.1f} hours) is quite long. If you still feel tired, "
                "consider consulting a healthcare provider about sleep quality."
            )
        
        # Efficiency recommendations
        avg_efficiency = np.mean([n.efficiency for n in nights])
        if avg_efficiency < 80:
            recommendations.append(
                f"Your sleep efficiency is {avg_efficiency:.0f}% (time asleep vs time in bed). "
                "Try to reduce time awake in bed by avoiding screens before sleep."
            )
        
        # Default if no specific issues
        if not recommendations:
            recommendations.append(
                "Your sleep patterns look healthy! Keep maintaining good sleep hygiene practices."
            )
        
        return recommendations
    
    def _get_overall_quality(self, nights: List[NightlySummary]) -> SleepQuality:
        """Calculate overall quality based on majority cluster"""
        if not nights:
            return SleepQuality.GOOD
        
        qualities = [n.sleep_quality for n in nights]
        quality_counts = {}
        for q in qualities:
            quality_counts[q] = quality_counts.get(q, 0) + 1
        
        return max(quality_counts, key=quality_counts.get)
    
    def _empty_analysis(self) -> SleepAnalysis:
        """Return empty analysis for no data"""
        return SleepAnalysis(
            nights=[],
            overall_quality=SleepQuality.GOOD,
            trend_direction="stable",
            trend_slope=0.0,
            average_sleep_duration=0.0,
            average_restlessness=0.0,
            recommendations=["No sleep data available. Please ensure the device is collecting data."],
            insights={}
        )


def format_analysis_report(analysis: SleepAnalysis) -> str:
    """Format analysis results into a human-readable report"""
    lines = [
        "=" * 60,
        "SLEEP PATTERN ANALYSIS REPORT",
        "=" * 60,
        "",
        f"Analysis Period: {len(analysis.nights)} nights",
        f"Overall Quality: {analysis.overall_quality.value.upper()}",
        f"Trend: {analysis.trend_direction.upper()} (slope: {analysis.trend_slope:.2f})",
        "",
        "-" * 60,
        "AVERAGE METRICS",
        "-" * 60,
        f"  Average Sleep Duration: {analysis.average_sleep_duration:.1f} hours",
        f"  Average Restlessness: {analysis.average_restlessness:.1f}/100",
        "",
    ]
    
    if analysis.nights:
        lines.extend([
            "-" * 60,
            "NIGHTLY BREAKDOWN",
            "-" * 60,
        ])
        for night in analysis.nights:
            lines.append(
                f"  {night.date}: {night.sleep_time_hours:.1f}h sleep, "
                f"{night.restlessness_score:.0f}% restless [{night.sleep_quality.value}]"
            )
        lines.append("")
    
    lines.extend([
        "-" * 60,
        "INSIGHTS",
        "-" * 60,
    ])
    
    if analysis.insights:
        if "best_night" in analysis.insights:
            lines.append(f"  Best Night: {analysis.insights['best_night']}")
        if "worst_night" in analysis.insights:
            lines.append(f"  Worst Night: {analysis.insights['worst_night']}")
        if "consistency_score" in analysis.insights:
            lines.append(f"  Consistency Score: {analysis.insights['consistency_score']:.0f}/100")
        if analysis.insights.get("sleeps_more_on_weekends"):
            diff = analysis.insights.get("weekend_weekday_diff", 0)
            lines.append(f"  Weekend Effect: You sleep {diff:.1f}h more on weekends")
    else:
        lines.append("  No insights available")
    
    lines.extend([
        "",
        "-" * 60,
        "RECOMMENDATIONS",
        "-" * 60,
    ])
    
    for i, rec in enumerate(analysis.recommendations, 1):
        lines.append(f"  {i}. {rec}")
    
    lines.extend([
        "",
        "=" * 60,
    ])
    
    return "\n".join(lines)


# Convenience function for testing
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    print("Generating synthetic sleep data for testing...")
    
    # Generate test data
    test_readings = []
    base_date = datetime.now() - timedelta(days=7)
    
    for day in range(7):
        # Simulate a sleep session from 11 PM to 7 AM (8 hours)
        # For testing, we'll keep it on one "logical night" by using the start date
        night_date = base_date + timedelta(days=day)
        start_time = night_date.replace(hour=23, minute=0, second=0)
        end_time = start_time + timedelta(hours=8)
        
        # Vary the sleep quality per night to create interesting clusters
        sleep_quality_factor = 0.3 + (day * 0.1)  # Improving over the week
        restlessness_base = 0.15 - (day * 0.02)   # Decreasing over the week
        
        print(f"Generating night {day+1}/7: {night_date.date()} (quality factor: {sleep_quality_factor:.2f})")
        
        # Generate readings every 5 minutes
        reading_count = 0
        current = start_time
        while current < end_time:
            # Calculate minutes into sleep session (0-480 minutes)
            minutes_into_sleep = (current - start_time).total_seconds() / 60
            sleep_progress = minutes_into_sleep / 480  # 0.0 to 1.0
            
            # Simulate realistic sleep stages
            if sleep_progress < 0.1:  # First 10% - falling asleep
                state = "Present (Awake)"
                variance = 0.05
            elif sleep_progress > 0.9:  # Last 10% - waking up
                state = "Present (Awake)"
                variance = 0.04
            elif 0.3 < sleep_progress < 0.7:  # Middle - deep sleep
                state = "Asleep"
                variance = 0.015
            else:  # Light sleep
                state = "Asleep"
                variance = 0.025
            
            # Add random movements based on restlessness
            if np.random.random() < restlessness_base:
                state = "Tossing/Turning"
                variance = 0.08 + np.random.random() * 0.04
            
            # Occasionally wake up briefly
            if np.random.random() < 0.02:
                state = "Present (Awake)"
                variance = 0.06
            
            test_readings.append({
                'created_at': current.isoformat(),
                'timestamp': current.isoformat(),
                'state': state,
                'variance': variance,
                'voltage': 2.5 if state != "Empty Bed" else 0.3
            })
            reading_count += 1
            current += timedelta(minutes=5)
        
        print(f"  Generated {reading_count} readings")
    
    print(f"\nTotal readings: {len(test_readings)}")
    
    # Run analysis
    print("\nRunning ML analysis...")
    analyzer = SleepMLAnalyzer()
    analysis = analyzer.analyze(test_readings)
    
    # Print report
    print("\n" + format_analysis_report(analysis))
