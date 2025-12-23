"""
Calendar Service

Interfaces with the external calendar API to manage appointments.
"""

import requests
from typing import Dict, Optional, List
from datetime import datetime
from dateutil import parser as date_parser


class CalendarService:
    """Service for managing calendar appointments"""
    
    BASE_URL = "https://api.responsible-nlp.net/calendar.php?calenderid=3875616"
    
    def __init__(self):
        self.session = requests.Session()
    
    def create_appointment(self, description: str, date: str, time: str) -> Dict:
        """
        Create a new appointment
        
        Args:
            description: Description of the appointment
            date: Date in YYYY-MM-DD format
            time: Time in HH:MM format
            
        Returns:
            Dictionary with appointment data including ID
        """
        try:
            data = {
                "action": "create",
                "description": description,
                "date": date,
                "time": time
            }
            
            response = self.session.post(self.BASE_URL, json=data, timeout=10)
            response.raise_for_status()
            
            result = response.json()
            return {
                "success": True,
                "appointment": result
            }
        
        except Exception as e:
            print(f"[CalendarService] Error creating appointment: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def list_appointments(self) -> Dict:
        """List all appointments"""
        try:
            params = {"action": "list"}
            
            print(f"[CalendarService] Calling API (GET): {self.BASE_URL} with params={params}")
            response = self.session.get(self.BASE_URL, params=params, timeout=10)
            response.raise_for_status()
            
            result = response.json()
            print(f"[CalendarService] API Response: {result}")
            
            # API returns array directly, not {"appointments": [...]}
            appointments = result if isinstance(result, list) else result.get("appointments", [])
            
            return {
                "success": True,
                "appointments": appointments
            }
        
        except Exception as e:
            print(f"[CalendarService] Error listing appointments: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def get_appointment(self, appointment_id: int) -> Dict:
        """Get a specific appointment by ID"""
        try:
            params = {
                "action": "get",
                "id": appointment_id
            }
            
            response = self.session.get(self.BASE_URL, params=params, timeout=10)
            response.raise_for_status()
            
            result = response.json()
            return {
                "success": True,
                "appointment": result
            }
        
        except Exception as e:
            print(f"[CalendarService] Error getting appointment: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def update_appointment(self, appointment_id: int, description: Optional[str] = None,
                          date: Optional[str] = None, time: Optional[str] = None) -> Dict:
        """Update an existing appointment"""
        try:
            data = {
                "action": "update",
                "id": appointment_id
            }
            
            if description is not None:
                data["description"] = description
            if date is not None:
                data["date"] = date
            if time is not None:
                data["time"] = time
            
            response = self.session.post(self.BASE_URL, json=data, timeout=10)
            response.raise_for_status()
            
            result = response.json()
            return {
                "success": True,
                "appointment": result
            }
        
        except Exception as e:
            print(f"[CalendarService] Error updating appointment: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def delete_appointment(self, appointment_id: int) -> Dict:
        """Delete an appointment"""
        try:
            data = {
                "action": "delete",
                "id": appointment_id
            }
            
            response = self.session.post(self.BASE_URL, json=data, timeout=10)
            response.raise_for_status()
            
            result = response.json()
            return {
                "success": True,
                "message": result.get("message", "Appointment deleted")
            }
        
        except Exception as e:
            print(f"[CalendarService] Error deleting appointment: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def parse_date_time(self, date_str: Optional[str] = None, time_str: Optional[str] = None) -> Dict:
        """
        Parse natural language date/time strings
        
        Returns:
            Dictionary with 'date' (YYYY-MM-DD) and 'time' (HH:MM)
        """
        result = {}
        
        # Parse date
        if date_str:
            try:
                parsed_date = date_parser.parse(date_str, fuzzy=True)
                result["date"] = parsed_date.strftime("%Y-%m-%d")
            except:
                # Default to today
                result["date"] = datetime.now().strftime("%Y-%m-%d")
        else:
            result["date"] = datetime.now().strftime("%Y-%m-%d")
        
        # Parse time
        if time_str:
            try:
                parsed_time = date_parser.parse(time_str, fuzzy=True)
                result["time"] = parsed_time.strftime("%H:%M")
            except:
                # Default to noon
                result["time"] = "12:00"
        else:
            result["time"] = "12:00"
        
        return result
    
    def format_appointment(self, appointment: Dict) -> str:
        """Format a single appointment for display"""
        apt_id = appointment.get("id", "?")
        
        # API returns 'title' and 'description', prefer title if available
        title = appointment.get("title", appointment.get("description", "No title"))
        
        # API returns 'start_time' in ISO format (YYYY-MM-DDTHH:MM)
        start_time = appointment.get("start_time", appointment.get("date", "Unknown"))
        
        # Parse the datetime if it's in ISO format
        try:
            dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
            date_str = dt.strftime("%B %d, %Y")  # e.g., "November 03, 2025"
            time_str = dt.strftime("%I:%M %p")   # e.g., "09:00 AM"
            return f"Appointment {apt_id}: {title} on {date_str} at {time_str}"
        except:
            # Fallback if parsing fails
            return f"Appointment {apt_id}: {title} at {start_time}"
    
    def format_appointments_list(self, appointments: List[Dict]) -> str:
        """Format a list of appointments for display"""
        if not appointments:
            return "You have no appointments scheduled."
        
        parts = [f"You have {len(appointments)} appointment(s):"]
        for apt in appointments:
            parts.append(self.format_appointment(apt))
        
        return " ".join(parts)
