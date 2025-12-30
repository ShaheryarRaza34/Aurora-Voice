"""
Calendar Service

Interfaces with the external calendar API to manage appointments.
"""

import requests
import re
from typing import Dict, Optional, List
from datetime import datetime
from dateutil import parser as date_parser


class CalendarService:
    """Service for managing calendar appointments"""
    
    BASE_URL = "https://api.responsible-nlp.net/calendar.php?calenderid=3875616"
    
    def __init__(self):
        self.session = requests.Session()
    
    def create_appointment(self, description: str, date: str, start_time: str, end_time: str = None, location: str = None) -> Dict:
        """
        Create a new appointment
        
        Args:
            description: Description/title of the appointment
            date: Date in YYYY-MM-DD format
            start_time: Start time in HH:MM format
            end_time: End time in HH:MM format (required)
            location: Optional location string
            
        Returns:
            Dictionary with appointment data including ID
        """
        try:
            # Combine date and start_time into ISO format start_time: "2025-11-03T09:00"
            start_datetime_str = f"{date}T{start_time}"
            
            # Use provided end_time (required, no default)
            if not end_time:
                raise ValueError("end_time is required for appointment creation")
            
            # Combine date and end_time into ISO format
            end_datetime_str = f"{date}T{end_time}"
            
            # API expects: title, description, start_time, end_time, location
            data = {
                "title": description,  # Use description as title
                "description": description,  # Use same value for description
                "start_time": start_datetime_str,
                "end_time": end_datetime_str,
            }
            
            # Add location if provided
            if location:
                data["location"] = location
            
            print(f"[CalendarService] Creating appointment with data: {data}")
            response = self.session.post(self.BASE_URL, json=data, timeout=10)
            response.raise_for_status()
            print(f"[CalendarService] Response status: {response.status_code}")
            print(f"[CalendarService] Response headers: {response.headers}")
            
            result = response.json()
            print(f"[CalendarService] API Response: {result}")
            
            # Check if API returned an error
            if "error" in result:
                return {
                    "success": False,
                    "error": result["error"]
                }
            
            return {
                "success": True,
                "appointment": result
            }
        
        except Exception as e:
            print(f"[CalendarService] Error creating appointment: {e}")
            import traceback
            traceback.print_exc()
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
            # API expects ID as query parameter: ?calenderid=3875616&id=2
            delete_url = f"{self.BASE_URL}&id={appointment_id}"
            
            print(f"[CalendarService] Deleting appointment with ID: {appointment_id}")
            print(f"[CalendarService] DELETE API URL: {delete_url}")
            
            # API expects DELETE method
            response = self.session.delete(delete_url, timeout=10)
            print(f"[CalendarService] DELETE API response status: {response.status_code}")
            print(f"[CalendarService] DELETE API response headers: {response.headers}")
            
            response.raise_for_status()
            
            result = response.json()
            print(f"[CalendarService] DELETE API response body: {result}")
            
            return {
                "success": True,
                "message": result.get("message", "Appointment deleted")
            }
        
        except Exception as e:
            print(f"[CalendarService] Error deleting appointment: {e}")
            print(f"[CalendarService] Exception type: {type(e).__name__}")
            import traceback
            print(f"[CalendarService] Traceback: {traceback.format_exc()}")
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
                print(f"[CalendarService] Parsing date: '{date_str}'")
                # Convert worded ordinals to numbers (e.g., "first January" -> "1 January")
                date_str_normalized = date_str.lower()
                word_to_number = {
                    "first": "1", "second": "2", "third": "3", "fourth": "4", "fifth": "5",
                    "sixth": "6", "seventh": "7", "eighth": "8", "ninth": "9", "tenth": "10",
                    "eleventh": "11", "twelfth": "12", "thirteenth": "13", "fourteenth": "14",
                    "fifteenth": "15", "sixteenth": "16", "seventeenth": "17", "eighteenth": "18",
                    "nineteenth": "19", "twentieth": "20", "twenty-first": "21", "twenty-second": "22",
                    "twenty-third": "23", "twenty-fourth": "24", "twenty-fifth": "25",
                    "twenty-sixth": "26", "twenty-seventh": "27", "twenty-eighth": "28",
                    "twenty-ninth": "29", "thirtieth": "30", "thirty-first": "31"
                }
                for word, num in word_to_number.items():
                    if date_str_normalized.startswith(word + " "):
                        date_str = date_str.replace(word, num, 1).replace(word.capitalize(), num, 1)
                        print(f"[CalendarService] Converted worded ordinal '{word}' to '{num}' in date string")
                        break
                
                parsed_date = date_parser.parse(date_str, fuzzy=True)
                parsed_date_str = parsed_date.strftime("%Y-%m-%d")
                
                # Check if parsed date is in the past - if so, assume next year
                today = datetime.now().date()
                parsed_date_only = parsed_date.date().replace(year=today.year)
                
                if parsed_date_only < today:
                    # Date is in the past for current year, assume next year
                    parsed_date_only = parsed_date.date().replace(year=today.year + 1)
                    print(f"[CalendarService] Date '{date_str}' parsed to past date, using next year: {parsed_date_only}")
                
                result["date"] = parsed_date_only.strftime("%Y-%m-%d")
                print(f"[CalendarService] Parsed date to: {result['date']}")
            except Exception as e:
                print(f"[CalendarService] Date parsing failed: {e}, defaulting to today")
                # Default to today
                result["date"] = datetime.now().strftime("%Y-%m-%d")
        else:
            result["date"] = datetime.now().strftime("%Y-%m-%d")
        
        # Parse time - REQUIRED, no defaults
        if time_str:
            # Normalize the time string first
            time_normalized = time_str.strip().lower()
            
            # Handle formats like "12, 0, 0" or "15, 0, 0" -> "12:00:00" or "15:00:00"
            comma_match = re.search(r'(\d{1,2})\s*[.,]\s*(\d+)\s*[.,]\s*(\d+)', time_normalized)
            if comma_match:
                hour = int(comma_match.group(1))
                minute = int(comma_match.group(2))
                second = int(comma_match.group(3))
                if 0 <= hour <= 23 and 0 <= minute <= 59 and 0 <= second <= 59:
                    result["time"] = f"{hour:02d}:{minute:02d}"
                    print(f"[CalendarService] Parsed time from comma format '{time_str}' to: {result['time']}")
                    return result
            
            # Remove dots and normalize spaces - handle "p.m." or "p. m." -> "pm"
            time_normalized = time_normalized.replace('.', '').replace(' ', '')
            
            # Pattern 1: "12pm", "12pm", "3pm", "3pm" (after cleaning dots/spaces)
            pm_am_match = re.search(r'(\d{1,2})(pm|am)', time_normalized)
            if pm_am_match:
                hour = int(pm_am_match.group(1))
                period = pm_am_match.group(2)
                if period == "pm" and hour != 12:
                    hour += 12
                elif period == "am" and hour == 12:
                    hour = 0
                result["time"] = f"{hour:02d}:00"
                print(f"[CalendarService] Extracted time from AM/PM format '{time_str}' -> '{time_normalized}' -> {result['time']}")
                return result
            
            # Also try with spaces: "12 pm", "3 am" (before removing all spaces)
            time_with_spaces = time_str.strip().lower().replace('.', '')
            pm_am_match_spaced = re.search(r'(\d{1,2})\s+(pm|am)', time_with_spaces)
            if pm_am_match_spaced:
                hour = int(pm_am_match_spaced.group(1))
                period = pm_am_match_spaced.group(2)
                if period == "pm" and hour != 12:
                    hour += 12
                elif period == "am" and hour == 12:
                    hour = 0
                result["time"] = f"{hour:02d}:00"
                print(f"[CalendarService] Extracted time from AM/PM format (with spaces) '{time_str}' -> {result['time']}")
                return result
            
            # Pattern 2: Just a number like "15" or "12" (assume 24-hour format)
            # Check this BEFORE dateutil.parse to avoid ambiguity
            number_match = re.search(r'^(\d{1,2})$', time_normalized)
            if number_match:
                hour = int(number_match.group(1))
                if hour > 23:
                    raise ValueError(f"Invalid hour: {hour}")
                result["time"] = f"{hour:02d}:00"
                print(f"[CalendarService] Extracted time from number format '{time_str}' to: {result['time']}")
                return result
            
            # Pattern 3: "HH:MM" or "H:MM" format
            colon_match = re.search(r'(\d{1,2}):(\d{2})', time_normalized)
            if colon_match:
                hour = int(colon_match.group(1))
                minute = int(colon_match.group(2))
                if 0 <= hour <= 23 and 0 <= minute <= 59:
                    result["time"] = f"{hour:02d}:{minute:02d}"
                    print(f"[CalendarService] Extracted time from colon format '{time_str}' to: {result['time']}")
                    return result
            
            # Pattern 4: "HHMM" format (e.g., "1200", "1500")
            digits_match = re.search(r'^(\d{3,4})$', time_normalized)
            if digits_match:
                time_digits = digits_match.group(1)
                if len(time_digits) == 3:
                    hour = int(time_digits[0])
                    minute = int(time_digits[1:3])
                else:  # 4 digits
                    hour = int(time_digits[0:2])
                    minute = int(time_digits[2:4])
                if 0 <= hour <= 23 and 0 <= minute <= 59:
                    result["time"] = f"{hour:02d}:{minute:02d}"
                    print(f"[CalendarService] Extracted time from digits format '{time_str}' to: {result['time']}")
                    return result
            
            # Last resort: Try parsing with dateutil (but only for complex formats)
            try:
                parsed_time = date_parser.parse(time_normalized, fuzzy=True)
                result["time"] = parsed_time.strftime("%H:%M")
                print(f"[CalendarService] Parsed time via dateutil: '{time_str}' -> {result['time']}")
                return result
            except Exception as e:
                print(f"[CalendarService] dateutil parsing failed: {e}")
                # If all patterns fail
                print(f"[CalendarService] All parsing patterns failed for time_str: '{time_str}' (normalized: '{time_normalized}')")
                raise ValueError(f"Could not parse time: {time_str}")
        else:
            # Time is required - raise error instead of defaulting
            print(f"[CalendarService] ERROR: time_str is None or empty. time_str='{time_str}'")
            raise ValueError("Time is required for appointment creation")
        
        return result
    
    def format_appointment(self, appointment: Dict) -> str:
        """Format a single appointment for display"""
        apt_id = appointment.get("id", "?")
        
        # API returns 'title' and 'description', prefer title if available
        title = appointment.get("title", appointment.get("description", "Untitled appointment"))
        
        # API returns 'start_time' in ISO format (YYYY-MM-DDTHH:MM)
        start_time = appointment.get("start_time", appointment.get("date", "Unknown"))
        
        # Parse the datetime if it's in ISO format
        try:
            dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
            date_str = dt.strftime("%B %d, %Y")  # e.g., "November 3, 2025"
            time_str = dt.strftime("%I:%M %p").lstrip('0')  # e.g., "9:00 AM" (remove leading zero)
            return f"{title} on {date_str} at {time_str}"
        except:
            # Fallback if parsing fails
            return f"{title} at {start_time}"
    
    def get_next_appointment(self, appointments: List[Dict]) -> Optional[Dict]:
        """Get the next upcoming appointment"""
        if not appointments:
            return None
        
        # Sort appointments by start_time
        now = datetime.now()
        upcoming = []
        
        for apt in appointments:
            start_time = apt.get("start_time", apt.get("date", ""))
            if start_time:
                try:
                    dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                    # Only include future appointments
                    if dt > now:
                        upcoming.append((dt, apt))
                except:
                    # If parsing fails, include it anyway
                    upcoming.append((now, apt))
        
        if not upcoming:
            return None
        
        # Sort by datetime and return the earliest
        upcoming.sort(key=lambda x: x[0])
        return upcoming[0][1]
    
    def format_appointments_list(self, appointments: List[Dict]) -> str:
        """Format a list of appointments for display"""
        if not appointments:
            return "You have no appointments scheduled."
        
        count = len(appointments)
        if count == 1:
            return f"You have one appointment: {self.format_appointment(appointments[0])}."
        
        parts = [f"You have {count} appointments:"]
        for i, apt in enumerate(appointments, 1):
            parts.append(f"{i}. {self.format_appointment(apt)}")
        
        return ". ".join(parts) + "."
