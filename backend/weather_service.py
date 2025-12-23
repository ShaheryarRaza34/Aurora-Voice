"""
Weather Service

Interfaces with the external weather API to fetch forecast data.
"""

import requests
from typing import Dict, Optional, List


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
            
            print(f"[WeatherService] Calling API (POST): {self.BASE_URL} with data={data}")
            response = self.session.post(self.BASE_URL, data=data, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            print(f"[WeatherService] API Response: {data}")
            
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
    
    def format_forecast(self, forecast_data: Dict) -> str:
        """Format forecast data into a natural language response"""
        if not forecast_data.get("success"):
            return f"Sorry, I couldn't fetch the weather forecast. Error: {forecast_data.get('error', 'Unknown error')}"
        
        location = forecast_data.get("location", "the requested location")
        forecast = forecast_data.get("forecast", [])
        
        if not forecast:
            return f"No forecast data available for {location}."
        
        # Build response
        parts = [f"Here's the weather forecast for {location.title()}:"]
        
        for day_data in forecast[:5]:  # Limit to 5 days
            day = day_data.get("day", "Unknown").title()
            weather = day_data.get("weather", "unknown")
            temp = day_data.get("temperature", {})
            
            if isinstance(temp, dict):
                temp_min = temp.get("min", "?")
                temp_max = temp.get("max", "?")
                temp_str = f"{temp_min} to {temp_max} degrees"
            else:
                temp_str = str(temp)
            
            parts.append(f"{day}: {weather.title()}, {temp_str}.")
        
        return " ".join(parts)
