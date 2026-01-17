"""
Calendar Service

Interfaces with the external calendar API to manage appointments.
"""

import requests
import re
from typing import Dict, Optional, List
from datetime import datetime, timedelta
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
            
            response = self.session.post(self.BASE_URL, json=data, timeout=10)
            response.raise_for_status()
            
            result = response.json()
            
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
            
            response = self.session.get(self.BASE_URL, params=params, timeout=10)
            response.raise_for_status()
            
            result = response.json()
            
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
                          date: Optional[str] = None, time: Optional[str] = None, location: Optional[str] = None,
                          title: Optional[str] = None, start_time: Optional[str] = None, end_time: Optional[str] = None) -> Dict:
        """Update an existing appointment
        
        Args:
            appointment_id: ID of the appointment to update
            description: New description
            date: New date in YYYY-MM-DD format
            time: New time in HH:MM format (updates both start and end if only time provided)
            location: New location
            title: New title
            start_time: New start time in HH:MM format (if provided, will be combined with date)
            end_time: New end time in HH:MM format (if provided, will be combined with date)
        """
        try:
            
            # API expects ID as query parameter: ?calenderid=3875616&id=6
            update_url = f"{self.BASE_URL}&id={appointment_id}"
            
            data = {
                "action": "update"
            }
            
            if title is not None:
                data["title"] = title
            if description is not None:
                data["description"] = description
            if location is not None:
                data["location"] = location
            
            # Handle date updates: if date is provided without start_time/end_time, we need to update start_time and end_time
            # because the API stores dates as part of the ISO datetime strings
            if date is not None and start_time is None and end_time is None:
                # Date only provided - need to get existing times and combine with new date
                get_result = self.get_appointment(appointment_id)
                if get_result.get("success"):
                    current_appt = get_result.get("appointment", {})
                    current_start = current_appt.get("start_time", "")
                    current_end = current_appt.get("end_time", "")
                    
                    if current_start and "T" in current_start:
                        # Extract time portion from existing start_time (HH:MM)
                        time_part_start = current_start.split("T")[1][:5]  # Get HH:MM
                        data["start_time"] = f"{date}T{time_part_start}"
                    else:
                        # Fallback: use default time if no existing start_time
                        data["start_time"] = f"{date}T09:00"
                    
                    if current_end and "T" in current_end:
                        # Extract time portion from existing end_time (HH:MM)
                        time_part_end = current_end.split("T")[1][:5]  # Get HH:MM
                        data["end_time"] = f"{date}T{time_part_end}"
                    else:
                        # Fallback: use default time if no existing end_time
                        data["end_time"] = f"{date}T10:00"
                else:
                    # If we can't fetch current appointment, just send date and let API handle it
                    # But this likely won't work, so we'll try anyway
                    data["date"] = date
            
            # Handle time updates: prefer start_time/end_time if provided, otherwise use time
            if start_time is not None and end_time is not None:
                # Both start and end times provided - need date to combine
                if date:
                    data["start_time"] = f"{date}T{start_time}"
                    data["end_time"] = f"{date}T{end_time}"
                else:
                    # If no date provided, assume we're only updating times on same date
                    # Get current appointment to use its date
                    get_result = self.get_appointment(appointment_id)
                    if get_result.get("success"):
                        current_appt = get_result.get("appointment", {})
                        current_start = current_appt.get("start_time", "")
                        if current_start and "T" in current_start:
                            current_date = current_start.split("T")[0]
                            data["start_time"] = f"{current_date}T{start_time}"
                            data["end_time"] = f"{current_date}T{end_time}"
                        else:
                            # Fallback: use date parameter or today
                            use_date = date or datetime.now().strftime("%Y-%m-%d")
                            data["start_time"] = f"{use_date}T{start_time}"
                            data["end_time"] = f"{use_date}T{end_time}"
            elif start_time is not None:
                # Only start_time provided
                if date:
                    data["start_time"] = f"{date}T{start_time}"
                else:
                    # Get current appointment to use its date and end_time
                    get_result = self.get_appointment(appointment_id)
                    if get_result.get("success"):
                        current_appt = get_result.get("appointment", {})
                        current_start = current_appt.get("start_time", "")
                        current_end = current_appt.get("end_time", "")
                        if current_start and "T" in current_start:
                            current_date = current_start.split("T")[0]
                            data["start_time"] = f"{current_date}T{start_time}"
                            if current_end and "T" in current_end:
                                data["end_time"] = current_end  # Keep existing end_time
                        else:
                            use_date = date or datetime.now().strftime("%Y-%m-%d")
                            data["start_time"] = f"{use_date}T{start_time}"
            elif end_time is not None:
                # Only end_time provided
                if date:
                    data["end_time"] = f"{date}T{end_time}"
                else:
                    # Get current appointment to use its date and start_time
                    get_result = self.get_appointment(appointment_id)
                    if get_result.get("success"):
                        current_appt = get_result.get("appointment", {})
                        current_start = current_appt.get("start_time", "")
                        current_end = current_appt.get("end_time", "")
                        if current_start and "T" in current_start:
                            current_date = current_start.split("T")[0]
                            data["start_time"] = current_start  # Keep existing start_time
                            data["end_time"] = f"{current_date}T{end_time}"
                        else:
                            use_date = date or datetime.now().strftime("%Y-%m-%d")
                            data["end_time"] = f"{use_date}T{end_time}"
            elif time is not None:
                # Single time provided - update both start and end to same time (or API might handle it)
                # For backward compatibility, send as "time"
                data["time"] = time
            
            response = self.session.put(update_url, json=data, timeout=10)
            response.raise_for_status()
            
            result = response.json()
            
            # If API only returns {'success': True}, fetch the updated appointment
            if result.get("success") and not result.get("title") and not result.get("description"):
                get_result = self.get_appointment(appointment_id)
                if get_result["success"]:
                    appointment = get_result["appointment"]
                    return {
                        "success": True,
                        "appointment": appointment
                    }
            
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
            
            
            # API expects DELETE method
            response = self.session.delete(delete_url, timeout=10)
            
            response.raise_for_status()
            
            result = response.json()
            
            return {
                "success": True,
                "message": result.get("message", "Appointment deleted")
            }
        
        except Exception as e:
            print(f"[CalendarService] Error deleting appointment: {e}")
            print(f"[CalendarService] Exception type: {type(e).__name__}")
            import traceback
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
                # Handle special words like "tomorrow", "today", "yesterday"
                date_str_normalized = date_str.lower().strip()
                today = datetime.now().date()
                
                if date_str_normalized in ["tomorrow", "tom"]:
                    result["date"] = (today + timedelta(days=1)).strftime("%Y-%m-%d")
                    return result
                elif date_str_normalized in ["today", "tdy"]:
                    result["date"] = today.strftime("%Y-%m-%d")
                    return result
                elif date_str_normalized in ["yesterday", "yday"]:
                    result["date"] = (today - timedelta(days=1)).strftime("%Y-%m-%d")
                    return result
                
                # Convert worded ordinals to numbers (e.g., "first January" -> "1 January")
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
                        break
                
                parsed_date = date_parser.parse(date_str, fuzzy=True)
                parsed_date_str = parsed_date.strftime("%Y-%m-%d")
                
                # Check if parsed date is in the past - if so, assume next year
                today = datetime.now().date()
                parsed_date_only = parsed_date.date().replace(year=today.year)
                
                if parsed_date_only < today:
                    # Date is in the past for current year, assume next year
                    parsed_date_only = parsed_date.date().replace(year=today.year + 1)
                
                result["date"] = parsed_date_only.strftime("%Y-%m-%d")
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
                return result
            
            # Pattern for "o'clock" format: "5 o'clock", "12 o'clock" (before removing all spaces)
            # Assume PM for hours 1-11, 12 o'clock is noon (12:00), default to PM if ambiguous
            oclock_match = re.search(r"(\d{1,2})\s+o'?clock", time_with_spaces)
            if oclock_match:
                hour = int(oclock_match.group(1))
                # Common convention: "5 o'clock" in appointments usually means PM (5:00 PM)
                # If hour is 12, it's 12:00 (noon). For 1-11, assume PM. For 13-23, use as-is.
                if 1 <= hour <= 11:
                    hour += 12  # Convert to PM (13:00 = 1 PM, 23:00 = 11 PM)
                elif hour == 12:
                    hour = 12  # 12 o'clock = noon (12:00)
                result["time"] = f"{hour:02d}:00"
                return result
            
            # Pattern 2: Just a number like "15" or "12" (assume 24-hour format)
            # Check this BEFORE dateutil.parse to avoid ambiguity
            number_match = re.search(r'^(\d{1,2})$', time_normalized)
            if number_match:
                hour = int(number_match.group(1))
                if hour > 23:
                    raise ValueError(f"Invalid hour: {hour}")
                result["time"] = f"{hour:02d}:00"
                return result
            
            # Pattern 3: "HH:MM" or "H:MM" format
            colon_match = re.search(r'(\d{1,2}):(\d{2})', time_normalized)
            if colon_match:
                hour = int(colon_match.group(1))
                minute = int(colon_match.group(2))
                if 0 <= hour <= 23 and 0 <= minute <= 59:
                    result["time"] = f"{hour:02d}:{minute:02d}"
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
                    return result
            
            # Last resort: Try parsing with dateutil (but only for complex formats)
            try:
                parsed_time = date_parser.parse(time_normalized, fuzzy=True)
                result["time"] = parsed_time.strftime("%H:%M")
                return result
            except Exception as e:
                print(f"[CalendarService] dateutil parsing failed: {e}")
                # If all patterns fail
                print(f"[CalendarService] All parsing patterns failed for time_str: '{time_str}' (normalized: '{time_normalized}')")
                raise ValueError(f"Could not parse time: {time_str}")
        # Note: If time_str is None, we allow date-only parsing (used when parsing date and time separately)
        # The caller is responsible for ensuring time is provided when needed
        
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
            # Handle different date/time formats
            if start_time and start_time != "Unknown":
                dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                date_str = dt.strftime("%B %d, %Y")  # e.g., "November 3, 2025"
                time_str = dt.strftime("%I:%M %p").lstrip('0')  # e.g., "9:00 AM" (remove leading zero)
                return f"{title} on {date_str} at {time_str}"
            else:
                # If no start_time, just return title
                return f"{title}"
        except Exception as e:
            # Fallback if parsing fails
            print(f"[CalendarService] format_appointment parsing failed: {e}, start_time: {start_time}")
            if start_time and start_time != "Unknown":
                return f"{title} at {start_time}"
            else:
                return f"{title}"
    
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
