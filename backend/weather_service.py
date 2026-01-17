"""
Weather Service

Interfaces with the external weather API to fetch forecast data.
"""

import requests
from typing import Dict, Optional, List
from datetime import datetime
from dateutil import parser as date_parser


class WeatherService:
    """Service for fetching weather information"""
    
    BASE_URL = "https://api.responsible-nlp.net/weather.php"
    
    def __init__(self):
        self.session = requests.Session()
    
    def get_forecast(self, location: str = "zurich", days: int = 5) -> Dict:
        """
        Get weather forecast for a location
        
        Args:
            location: City name (default: zurich)
            days: Number of days to forecast (1-5, default: 5)
            
        Returns:
            Dictionary with forecast data
        """
        try:
            data = {
                "place": location.lower(),  # API expects 'place' parameter
                "days": min(max(1, days), 5)  # Clamp between 1 and 5
            }
            
            response = self.session.post(self.BASE_URL, data=data, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            # Check for API error
            if "error" in data:
                return {
                    "success": False,
                    "error": data["error"]
                }
            
            return {
                "success": True,
                "location": data.get("place", location),
                "forecast": data.get("forecast", []),
                "raw_data": data
            }
        
        except Exception as e:
            print(f"[WeatherService] Error fetching forecast: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def format_forecast(self, forecast_data: Dict, query_context: Optional[Dict] = None) -> str:
        """
        Format forecast data into a natural language response
        
        Args:
            forecast_data: The forecast data from API
            query_context: Optional dict with 'date', 'condition', 'location' for specific queries
        """
        if not forecast_data.get("success"):
            return f"Sorry, I couldn't fetch the weather forecast. {forecast_data.get('error', 'Unknown error')}"
        
        location = forecast_data.get("location", "the requested location")
        forecast = forecast_data.get("forecast", [])
        
        if not forecast:
            return f"No forecast data available for {location.title()}."
        
        # Handle specific queries (e.g., "is it going to rain on Friday?")
        if query_context:
            date_query = query_context.get("date")
            condition = query_context.get("condition")
            # Safely handle None condition
            condition_query = condition.lower() if condition and isinstance(condition, str) else ""
            
            # If asking about a specific date and condition
            if date_query and condition_query:
                answer = self._answer_specific_query(forecast, date_query, condition_query, location)
                if answer:
                    return answer
            # If asking about a specific date only
            elif date_query:
                answer = self._answer_date_query(forecast, date_query, location)
                if answer:
                    return answer
            # If asking about a specific condition
            elif condition_query:
                answer = self._answer_condition_query(forecast, condition_query, location)
                if answer:
                    return answer
        
        # Default: return full forecast summary
        parts = [f"Weather forecast for {location.title()}:"]
        
        for day_data in forecast[:5]:  # Limit to 5 days
            day = day_data.get("day", "Unknown").title()
            weather = day_data.get("weather", "unknown").title()
            temp = day_data.get("temperature", {})
            
            if isinstance(temp, dict):
                temp_min = temp.get("min", "?")
                temp_max = temp.get("max", "?")
                if temp_min != "?" and temp_max != "?":
                    temp_str = f"{temp_min}° to {temp_max}°C"
                else:
                    temp_str = "temperature unavailable"
            else:
                temp_str = f"{temp}°C" if temp else "temperature unavailable"
            
            parts.append(f"{day}: {weather}, {temp_str}")
        
        return ". ".join(parts) + "."
    
    def _find_day_in_forecast(self, forecast: List[Dict], date_query: str) -> Optional[Dict]:
        """Find a specific day in the forecast based on date query"""
        if not date_query or not isinstance(date_query, str):
            return None
        
        if not forecast:
            return None
        
        query_lower = date_query.lower()
        
        # Check for "today" first - first day in forecast is usually today
        if "today" in query_lower:
            return forecast[0] if forecast else None
        
        # Check for "tomorrow" - second day in forecast is usually tomorrow
        if "tomorrow" in query_lower:
            return forecast[1] if len(forecast) > 1 else None
        
        try:
            # Try to parse the date query to get day name
            query_date = date_parser.parse(date_query, fuzzy=True)
            query_day_name = query_date.strftime("%A").lower()  # e.g., "friday"
            
            # Also try day names directly
            day_names = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
            
            for day_data in forecast:
                day = day_data.get("day", "").lower()
                # Match by day name
                if query_day_name in day or any(dn in query_lower and dn in day for dn in day_names):
                    return day_data
        except:
            # If parsing fails, try direct day name matching
            day_names = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
            for day_data in forecast:
                day = day_data.get("day", "").lower()
                if any(dn in query_lower and dn in day for dn in day_names):
                    return day_data
        
        return None
    
    def _answer_specific_query(self, forecast: List[Dict], date_query: str, condition_query: str, location: str) -> str:
        """Answer a specific query like 'will it rain on Friday?'"""
        day_data = self._find_day_in_forecast(forecast, date_query)
        
        if not day_data:
            return None  # Return None to fall back to full forecast
        
        day = day_data.get("day", "that day").title()
        weather = day_data.get("weather", "").lower()
        
        # Check if condition matches
        condition_keywords = {
            "rain": ["rain", "rainy", "drizzle", "shower", "storm", "precipitation"],
            "snow": ["snow", "snowy", "sleet", "blizzard"],
            "sunny": ["sunny", "clear", "sun"],
            "cloudy": ["cloudy", "cloud", "overcast", "partly cloudy"]
        }
        
        for condition, keywords in condition_keywords.items():
            if condition in condition_query:
                matches = any(kw in weather for kw in keywords)
                if matches:
                    return f"Yes, it's going to {condition} on {day} in {location.title()}."
                else:
                    return f"No, it's not going to {condition} on {day}. The forecast shows {weather.title()} weather."
        
        return None
    
    def _answer_date_query(self, forecast: List[Dict], date_query: str, location: str) -> str:
        """Answer a query about a specific date"""
        day_data = self._find_day_in_forecast(forecast, date_query)
        
        if not day_data:
            return None
        
        day = day_data.get("day", "that day").title()
        weather = day_data.get("weather", "unknown").title()
        temp = day_data.get("temperature", {})
        
        if isinstance(temp, dict):
            temp_min = temp.get("min", "?")
            temp_max = temp.get("max", "?")
            if temp_min != "?" and temp_max != "?":
                temp_str = f"{temp_min}° to {temp_max}°C"
            else:
                temp_str = "temperature unavailable"
        else:
            temp_str = f"{temp}°C" if temp else "temperature unavailable"
        
        return f"On {day} in {location.title()}, expect {weather} weather with temperatures around {temp_str}."
    
    def _answer_condition_query(self, forecast: List[Dict], condition_query: str, location: str) -> str:
        """Answer a query about a specific weather condition"""
        if not condition_query or not isinstance(condition_query, str):
            return None
        
        condition_keywords = {
            "rain": ["rain", "rainy", "drizzle", "shower", "storm"],
            "snow": ["snow", "snowy", "sleet"],
            "sunny": ["sunny", "clear", "sun"],
            "cloudy": ["cloudy", "cloud", "overcast"]
        }
        
        # Find which condition is being asked about
        condition_name = None
        condition_lower = condition_query.lower()
        for condition, keywords in condition_keywords.items():
            if condition in condition_lower:
                condition_name = condition
                break
        
        if not condition_name:
            return None
        
        matching_days = []
        keywords = condition_keywords.get(condition_name, [])
        for day_data in forecast[:5]:
            day = day_data.get("day", "Unknown").title()
            weather = day_data.get("weather", "").lower()
            
            if keywords and any(kw in weather for kw in keywords):
                matching_days.append(day)
        
        if matching_days:
            if len(matching_days) == 1:
                return f"Yes, it's going to {condition_name} on {matching_days[0]} in {location.title()}."
            else:
                return f"Yes, it's going to {condition_name} on {', '.join(matching_days)} in {location.title()}."
        else:
            return f"No, I don't see {condition_name} in the forecast for {location.title()} in the next few days."
