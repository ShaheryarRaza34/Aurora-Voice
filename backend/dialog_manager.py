"""
Dialog Manager

Orchestrates the conversation flow, integrating NLU, services, and conversation management.
"""

import re
from typing import Dict, Optional
from nlu import NLU, Intent
from weather_service import WeatherService
from calendar_service import CalendarService
from conversation_manager import ConversationManager


class DialogManager:
    """Manages dialog flow and integrates all components"""
    
    def __init__(self, conversation_manager: ConversationManager):
        self.nlu = NLU()
        self.weather_service = WeatherService()
        self.calendar_service = CalendarService()
        self.conversation_manager = conversation_manager
    
    def process_user_input(self, user_input: str, session_id: str) -> Dict:
        """
        Process user input and generate a response with robust context handling.
        
        Args:
            user_input: The user's spoken input
            session_id: Unique session identifier
            
        Returns:
            Dictionary with response text and metadata
        """
# Get existing context (ONLY from current session - no global fallback)
        context = self.conversation_manager.get_context(session_id)
        pending_intent = context.get("pending_intent")
        # Only get history from current session
        history = self.conversation_manager.get_history(session_id)
        
# Parse input (Pass history to NLU to help it resolve UNKNOWN intents)
        nlu_result = self.nlu.parse(user_input, history)
        intent = nlu_result["intent"]
        entities = nlu_result["entities"]
        
# SMART CONTEXT HANDLING
        # If the NLU is confused (UNKNOWN) but we are in the middle of a task, 
        # assume the user is answering a follow-up question.
        if pending_intent and intent == Intent.UNKNOWN.value:
            intent = pending_intent
            
            # Specialized recovery for entities (like "Frankfurt" or "1st January")
            # Re-extract entities with the correct intent context
            if intent == Intent.WEATHER_QUERY.value:
                # If entities were extracted but as wrong type (e.g., description instead of location), re-extract
                if not entities.get("location") or entities.get("description"):
                    weather_entities = self.nlu._extract_weather_entities(user_input, user_input.lower(), history)
                    # Merge weather entities, prioritizing location
                    if weather_entities.get("location"):
                        entities["location"] = weather_entities["location"]
                    if weather_entities.get("date"):
                        entities["date"] = weather_entities["date"]
                    if weather_entities.get("condition"):
                        entities["condition"] = weather_entities["condition"]
                    # Remove description if it was mistakenly extracted
                    if "description" in entities:
                        del entities["description"]
                # If still no location, try session-specific lookup
                if not entities.get("location"):
                    last_location = self.conversation_manager.get_last_known_location(session_id)
                    if last_location:
                        entities["location"] = last_location
            elif intent in [Intent.CALENDAR_CREATE.value, Intent.CALENDAR_UPDATE.value]:
                # Re-extract calendar entities to ensure we get description and date
                calendar_entities = self.nlu._extract_calendar_entities(user_input, user_input.lower())
                # Merge calendar entities
                if calendar_entities.get("description"):
                    entities["description"] = calendar_entities["description"]
                if calendar_entities.get("date"):
                    entities["date"] = calendar_entities["date"]
                if calendar_entities.get("time"):
                    entities["time"] = calendar_entities["time"]
                
                # Explicitly merge with pending_appointment from context
                pending_appointment = context.get("pending_appointment", {})
                if pending_appointment:
                    # Merge: new entities override pending, but keep pending if new is missing
                    # For description: be smart - don't overwrite existing good description with suspicious short descriptions
                    new_description = entities.get("description")
                    pending_description = pending_appointment.get("description")
                    if new_description and pending_description:
                        # Check if new description looks suspicious (short, numeric, might be a time)
                        new_desc_lower = new_description.lower().strip()
                        is_suspicious = (
                            len(new_desc_lower) <= 4 or  # Very short
                            new_desc_lower.isdigit() or  # All numbers
                            re.match(r'^\d+\s*[a-z]*$', new_desc_lower) or  # Numbers with letters like "5pm", "5bm"
                            re.match(r'^\d+\s*[.,!?]*$', new_desc_lower)  # Just numbers with punctuation
                        )
                        if is_suspicious:
                            # Keep the pending description instead of overwriting with suspicious one
                            entities["description"] = pending_description
                    elif not new_description and pending_description:
                        entities["description"] = pending_description
                    
                    # For date: be smart - don't overwrite good pending date with suspicious time-like values
                    new_date = entities.get("date")
                    pending_date = pending_appointment.get("date")
                    if new_date and pending_date:
                        # Check if new date looks suspicious (might be a time like "1700", "17", "12pm")
                        new_date_lower = new_date.lower().strip()
                        is_suspicious_date = (
                            len(new_date_lower) <= 4 or  # Very short (like "17", "1700")
                            new_date_lower.isdigit() or  # All numbers (like "17", "1700", "2026")
                            re.match(r'^\d{1,4}$', new_date_lower) or  # Just 1-4 digits (likely a time or year only)
                            re.match(r'^\d{1,2}(pm|am)$', new_date_lower) or  # Time format like "5pm"
                            re.match(r'^\d{4}$', new_date_lower)  # Year only like "2026" (should be full date like "March 15, 2026")
                        )
                        if is_suspicious_date:
                            # Keep the pending date instead of overwriting with suspicious one
                            entities["date"] = pending_date
                    elif not new_date and pending_date:
                        entities["date"] = pending_date
                    if not entities.get("time") and pending_appointment.get("time"):
                        entities["time"] = pending_appointment["time"]
        
# INTENT SWITCHING LOGIC
        # Only clear context if a NEW, DIFFERENT, and VALID intent is detected.
        # Do NOT clear context if intent is UNKNOWN (could be speech recognition error)
        elif pending_intent and intent != pending_intent:
            if intent != Intent.UNKNOWN.value:
                # Only clear if the new intent is a specific, known intent that's different
                # This prevents clearing context on speech recognition errors
                self.conversation_manager.clear_context(session_id)
            else:
                # If current intent is UNKNOWN, keep the pending intent active
                # This handles cases like "Frank food" (speech error) when expecting location
                intent = pending_intent
        
        
# Save user turn (with entities so location can be retrieved later)
        self.conversation_manager.add_turn(session_id, "user", user_input, intent, entities)
        
# Handle the intent and generate response (pass user_input for fallback logic)
        response_text = self._handle_intent(intent, entities, session_id, user_input)
        
# Save assistant turn
        self.conversation_manager.add_turn(session_id, "assistant", response_text, intent)
        
        return {
            "response": response_text,
            "intent": intent,
            "entities": entities
        }
    
    def _handle_intent(self, intent: str, entities: Dict, session_id: str, user_input: str = "") -> str:
        """Route to appropriate intent handler"""
        
        if intent == Intent.GREETING.value:
            return self._handle_greeting()
        
        elif intent == Intent.HELP.value:
            return self._handle_help()
        
        elif intent == Intent.WEATHER_QUERY.value:
            return self._handle_weather_query(entities, session_id)
        
        elif intent == Intent.CALENDAR_CREATE.value:
            return self._handle_calendar_create(entities, session_id, user_input)
        
        elif intent == Intent.CALENDAR_LIST.value:
            return self._handle_calendar_list(entities, session_id, user_input)
        
        elif intent == Intent.CALENDAR_GET.value:
            return self._handle_calendar_get(entities, session_id)
        
        elif intent == Intent.CALENDAR_UPDATE.value:
            return self._handle_calendar_update(entities, session_id, user_input)
        
        elif intent == Intent.CALENDAR_DELETE.value:
            return self._handle_calendar_delete(entities, session_id, user_input)
        
        else:
            return self._handle_unknown()
    
    def _handle_greeting(self) -> str:
        """Handle greeting intent"""
        return "Hello! I'm your voice assistant. I can help you check the weather and manage your calendar. How can I assist you today?"
    
    def _handle_help(self) -> str:
        """Handle help intent"""
        return ("I can help you with weather forecasts and calendar management. "
                "You can ask about the weather, create appointments, list your schedule, "
                "update or delete appointments. Just let me know what you need!")
    
    def _handle_weather_query(self, entities: Dict, session_id: str) -> str:
        """Handle weather query with conversation context and database history"""
        context = self.conversation_manager.get_context(session_id)
        pending_weather = context.get("pending_weather", {})
        
        # Merge entities with pending weather query data
        location = entities.get("location") or pending_weather.get("location")
        date = entities.get("date") or pending_weather.get("date")
        condition = entities.get("condition") or pending_weather.get("condition")
        
        # Check if we need to resolve "there" or similar location references
        if entities.get("_needs_location_resolution") and not location:
            # Try global location lookup first
            last_location = self.conversation_manager.get_last_known_location(session_id)
            if last_location:
                location = last_location
            # Remove the marker
            if "_needs_location_resolution" in entities:
                del entities["_needs_location_resolution"]
        
        # If location is still missing, try to get it from database history
        if not location:
            # First try: Get last known location from database
            last_location = self.conversation_manager.get_last_known_location(session_id)
            if last_location:
                location = last_location
            else:
                # Second try: Look in recent conversation history
                history = self.conversation_manager.get_history(session_id, limit=5)
                for turn in reversed(history):
                    if turn.get("role") == "assistant":
                        # Extract location from assistant's previous response
                        assistant_text = turn.get("text", "")
                        # Better pattern: matches "in Frankfurt", "for Frankfurt", "at Frankfurt"
                        location_match = re.search(r'\b(?:in|for|at)\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)?)\b', assistant_text)
                        if location_match:
                            location = location_match.group(1)
                            break
                    elif turn.get("role") == "user":
                        # Extract location from user's previous query
                        user_text = turn.get("text", "")
                        location_match = re.search(r'\b(?:in|for|at)\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)?)\b', user_text)
                        if location_match:
                            location = location_match.group(1)
                            break
        
        # If location is still missing, location will remain None (no global fallback)
        
        # If location is still missing, ask for it
        if not location:
            # Store context and ask for location
            if entities.get("date") or entities.get("condition"):
                pending_weather["date"] = entities.get("date")
                pending_weather["condition"] = entities.get("condition")
                self.conversation_manager.set_context(session_id, "pending_weather", pending_weather)
                self.conversation_manager.set_context(session_id, "pending_intent", "weather_query")
                return "Which location would you like the weather for?"
            else:
                # Try to get default location from context (user preference)
                default_location = context.get("default_location", "zurich")
                location = default_location
        
        # Store location in context and database for future reference
        if location and location.lower() != "zurich":
            pending_weather["location"] = location
            self.conversation_manager.set_context(session_id, "pending_weather", pending_weather)
            # Store as last known location (for cross-session lookup)
            self.conversation_manager.set_context(session_id, "last_location", location)
            # Clear pending intent
            self.conversation_manager.set_context(session_id, "pending_intent", None)
        
        # Fetch forecast
        forecast_data = self.weather_service.get_forecast(location=location)
        
        # Pass query context for targeted responses
        query_context = {
            "date": date,
            "condition": condition,
            "location": location
        }
        
        # Format and return with context
        return self.weather_service.format_forecast(forecast_data, query_context=query_context)
    
    def _handle_calendar_create(self, entities: Dict, session_id: str, user_input: str = "") -> str:
        """Handle calendar creation with conversation context"""
        context = self.conversation_manager.get_context(session_id)
        pending_appointment = context.get("pending_appointment", {})
        pending_intent = context.get("pending_intent")
        
        # Only use pending_appointment if we're in a follow-up conversation (intent was recovered)
        # If this is a fresh appointment creation, ignore old pending values
        # Check if this is a follow-up by seeing if entities are minimal (only date, or only description, etc.)
        # and pending_appointment has values - this suggests we're continuing a previous conversation
        is_follow_up = False
        if pending_intent == "calendar_create" and pending_appointment:
            # Count how many entities were extracted in current turn
            current_entities_count = sum(1 for k in ["description", "date", "start_time", "end_time", "time"] if entities.get(k))
            # Count how many fields are already in pending_appointment
            pending_fields_count = len([k for k in ["description", "date", "start_time", "end_time", "time"] if pending_appointment.get(k)])
            
            # If there's a pending appointment and user is providing missing fields, it's a follow-up
            # This includes cases where user provides both start_time and end_time in one response
            if pending_fields_count > 0:
                # Check if user is providing missing fields (not all fields are present yet)
                has_description = pending_appointment.get("description") or entities.get("description")
                has_date = pending_appointment.get("date") or entities.get("date")
                has_start_time = pending_appointment.get("start_time") or entities.get("start_time")
                has_end_time = pending_appointment.get("end_time") or entities.get("end_time")
                
                # If not all fields are complete, this is a follow-up
                if not (has_description and has_date and has_start_time and has_end_time):
                    is_follow_up = True
                else:
                    pending_appointment = {}
            else:
                pending_appointment = {}
        else:
            pending_appointment = {}
        
        # Merge entities with pending appointment data (only if follow-up)
        if is_follow_up:
            description = entities.get("description") or pending_appointment.get("description")
            date_str = entities.get("date") or pending_appointment.get("date")
            # Get start_time from pending first, then entities (entities override only if start_time wasn't in pending)
            pending_start_time = pending_appointment.get("start_time")
            entities_start_time = entities.get("start_time")
            # If we already have start_time in pending and entities also has start_time,
            # and end_time is missing, treat new start_time as end_time instead
            if pending_start_time and entities_start_time and not entities.get("end_time") and not pending_appointment.get("end_time"):
                # We're likely waiting for end_time, so map the new start_time to end_time
                start_time = pending_start_time
                end_time = entities_start_time
            else:
                start_time = entities_start_time or pending_start_time
                end_time = entities.get("end_time") or pending_appointment.get("end_time")
            # Fallback to old "time" field if start_time not provided
            if not start_time:
                time_str = entities.get("time") or pending_appointment.get("time")
                if time_str:
                    start_time = time_str
            # Map "time" to "end_time" if end_time is missing but start_time already exists
            elif not end_time:
                time_str = entities.get("time") or pending_appointment.get("time")
                if time_str:
                    end_time = time_str
        else:
            # Fresh creation - only use current entities
            description = entities.get("description")
            date_str = entities.get("date")
            start_time = entities.get("start_time")
            end_time = entities.get("end_time")
            # Fallback to old "time" field if start_time not provided
            if not start_time:
                time_str = entities.get("time")
                if time_str:
                    start_time = time_str
            # Map "time" to "end_time" if end_time is missing but start_time already exists
            elif not end_time:
                time_str = entities.get("time")
                if time_str:
                    end_time = time_str
        
        
        # Check: If user says "12 p.m.", ensure it's treated as time, not date
        # If entities has a "date" that looks like a time (e.g., "12" with pm/am), move it to start_time
        if entities.get("date") and not start_time:
            date_value = entities.get("date", "").lower().strip()
            # Check if date looks like a time (contains pm/am or is just a number)
            if "pm" in date_value or "am" in date_value or (date_value.isdigit() and len(date_value) <= 2):
                # If it's a number or has pm/am, it's likely a time, not a date
                if "pm" in date_value or "am" in date_value or (date_value.isdigit() and int(date_value) <= 23):
                    start_time = date_value.replace('.', '').replace(' ', '')
                    entities["start_time"] = start_time
                    entities["date"] = None  # Clear the incorrect date
        
        # FALLBACK: If description is missing and user_input is short (likely a follow-up answer)
        # and we're waiting for description, treat entire user_input as description
        if not description and pending_appointment and len(user_input.split()) < 5:
            # Check if we're waiting for description (pending_appointment has date but no description)
            if pending_appointment.get("date") and not pending_appointment.get("description"):
                # Clean up the input (remove punctuation, common words)
                clean_input = user_input.strip().rstrip('.,!?;:')
                # Remove common filler words
                filler_words = ["is", "would", "be", "the", "a", "an"]
                words = [w for w in clean_input.split() if w.lower() not in filler_words]
                if words:
                    description = " ".join(words)
        
        # FALLBACK: If start_time is missing and user_input is short, treat it as start_time
        if not start_time and pending_appointment and len(user_input.split()) < 5:
            # Check if we're waiting for start_time (pending_appointment has description and date but no start_time)
            if pending_appointment.get("description") and pending_appointment.get("date") and not pending_appointment.get("start_time"):
                # Clean up the input
                clean_input = user_input.strip().rstrip('.,!?;:')
                # Check if it looks like a time (contains numbers and possibly AM/PM)
                if re.search(r'\d', clean_input):
                    start_time = clean_input
        
        # FALLBACK: If end_time is missing but start_time exists, and user provides a time, map it to end_time
        # This handles cases where NLU extracts time as "start_time" when we're actually waiting for end_time
        if not end_time and start_time and pending_appointment:
            # Check if we're waiting for end_time (have description, date, and start_time already)
            if pending_appointment.get("description") and pending_appointment.get("date") and pending_appointment.get("start_time"):
                # If entities has "time" or "start_time" that wasn't used, map it to end_time
                time_str = entities.get("time") or entities.get("start_time")
                if time_str:
                    end_time = time_str
                # Otherwise, if user_input is short and looks like a time, use it
                elif len(user_input.split()) < 5:
                    clean_input = user_input.strip().rstrip('.,!?;:')
                    if re.search(r'\d', clean_input):
                        end_time = clean_input
        
        # Check for missing fields - ALL fields are required (description, date, start_time, AND end_time)
        # Also check for empty strings (not just None)
        missing_fields = []
        # Debug: Check actual values before missing fields check
        
        if not description or (isinstance(description, str) and not description.strip()):
            missing_fields.append("description")
        if not date_str or (isinstance(date_str, str) and not date_str.strip()):
            missing_fields.append("date")
        if not start_time or (isinstance(start_time, str) and not start_time.strip()):
            missing_fields.append("start_time")
        if not end_time or (isinstance(end_time, str) and not end_time.strip()):
            missing_fields.append("end_time")
        
        
        # If ANY fields are missing, store context and ask for them (DO NOT hit API)
        if missing_fields:
            # Store partial appointment data in context
            if description:
                pending_appointment["description"] = description
            if date_str:
                pending_appointment["date"] = date_str
            if start_time:
                pending_appointment["start_time"] = start_time
            if end_time:
                pending_appointment["end_time"] = end_time
            
            self.conversation_manager.set_context(session_id, "pending_appointment", pending_appointment)
            self.conversation_manager.set_context(session_id, "pending_intent", "calendar_create")
            
            # Ask for missing fields
            if len(missing_fields) == 1:
                field = missing_fields[0]
                if field == "description":
                    return "What should I call this appointment?"
                elif field == "date":
                    return "When should I schedule this appointment?"
                elif field == "start_time":
                    return "What time should this appointment start?"
                elif field == "end_time":
                    return "What time should this appointment end?"
            elif len(missing_fields) == 2:
                # Map field names to user-friendly names
                field_map = {"description": "description", "date": "date", "start_time": "start time", "end_time": "end time"}
                friendly_names = [field_map.get(f, f) for f in missing_fields]
                fields_str = " and ".join(friendly_names)
                return f"I need {fields_str} for the appointment. Please provide them."
            else:
                # Map field names to user-friendly names and list only missing fields
                field_map = {"description": "description", "date": "date", "start_time": "start time", "end_time": "end time"}
                friendly_names = [field_map.get(f, f) for f in missing_fields]
                # Create a readable list: "description, start time, and end time"
                if len(friendly_names) > 1:
                    last_field = friendly_names[-1]
                    other_fields = ", ".join(friendly_names[:-1])
                    fields_str = f"{other_fields}, and {last_field}"
                else:
                    fields_str = friendly_names[0]
                return f"I need {fields_str} for the appointment. Please provide all of them."
        
        # ALL required fields present - NOW we can create the appointment
        # Double-check that all fields are actually present (defensive check)
        if not description or not date_str or not start_time or not end_time:
            # This should not happen, but if it does, ask for missing fields
            missing_fields = []
            if not description:
                missing_fields.append("description")
            if not date_str:
                missing_fields.append("date")
            if not start_time:
                missing_fields.append("start_time")
            if not end_time:
                missing_fields.append("end_time")
            
            # Store partial appointment data in context
            if description:
                pending_appointment["description"] = description
            if date_str:
                pending_appointment["date"] = date_str
            if start_time:
                pending_appointment["start_time"] = start_time
            if end_time:
                pending_appointment["end_time"] = end_time
            
            self.conversation_manager.set_context(session_id, "pending_appointment", pending_appointment)
            self.conversation_manager.set_context(session_id, "pending_intent", "calendar_create")
            
            if len(missing_fields) == 1:
                field = missing_fields[0]
                if field == "description":
                    return "What should I call this appointment?"
                elif field == "date":
                    return "When should I schedule this appointment?"
                elif field == "start_time":
                    return "What time should this appointment start?"
                elif field == "end_time":
                    return "What time should this appointment end?"
            elif len(missing_fields) == 2:
                # Map field names to user-friendly names
                field_map = {"description": "description", "date": "date", "start_time": "start time", "end_time": "end time"}
                friendly_names = [field_map.get(f, f) for f in missing_fields]
                fields_str = " and ".join(friendly_names)
                return f"I need {fields_str} for the appointment. Please provide them."
            else:
                # Map field names to user-friendly names and list only missing fields
                field_map = {"description": "description", "date": "date", "start_time": "start time", "end_time": "end time"}
                friendly_names = [field_map.get(f, f) for f in missing_fields]
                # Create a readable list: "description, start time, and end time"
                if len(friendly_names) > 1:
                    last_field = friendly_names[-1]
                    other_fields = ", ".join(friendly_names[:-1])
                    fields_str = f"{other_fields}, and {last_field}"
                else:
                    fields_str = friendly_names[0]
                return f"I need {fields_str} for the appointment. Please provide all of them."
        
        
        # Clear pending context before creating
        self.conversation_manager.set_context(session_id, "pending_appointment", {})
        self.conversation_manager.set_context(session_id, "pending_intent", None)
        
        # Parse date and times (start_time and end_time are required, no defaults)
        try:
            parsed_date = self.calendar_service.parse_date_time(date_str, None)
            date = parsed_date["date"]
            
            # Only parse times if they are actually provided (not None or empty)
            if not start_time or not start_time.strip():
                raise ValueError("start_time is required")
            if not end_time or not end_time.strip():
                raise ValueError("end_time is required")
            
            
            parsed_start = self.calendar_service.parse_date_time(None, start_time)
            start_time_parsed = parsed_start["time"]
            
            parsed_end = self.calendar_service.parse_date_time(None, end_time)
            end_time_parsed = parsed_end["time"]
            
        except Exception as e:
            print(f"[DialogManager] ERROR DETAILS - Entities extracted: {entities}")
            print(f"[DialogManager] ERROR DETAILS - start_time='{start_time}', end_time='{end_time}', date_str='{date_str}'")
            print(f"[DialogManager] ERROR DETAILS - Exception type: {type(e).__name__}, message: {str(e)}")
            # Store context and ask user to provide valid times
            pending_appointment["description"] = description
            pending_appointment["date"] = date_str
            if start_time:
                pending_appointment["start_time"] = start_time
            if end_time:
                pending_appointment["end_time"] = end_time
            self.conversation_manager.set_context(session_id, "pending_appointment", pending_appointment)
            self.conversation_manager.set_context(session_id, "pending_intent", "calendar_create")
            if "time" in str(e).lower() or "Time is required" in str(e) or "start_time" in str(e).lower() or "end_time" in str(e).lower():
                return f"I couldn't understand the time format. Please provide times in format like '12 PM' or '15:00'."
            else:
                return f"I couldn't understand the date/time format. Please provide a valid date and times."
        
        # Create appointment (only when ALL fields are valid)
        try:
            result = self.calendar_service.create_appointment(description, date, start_time_parsed, end_time_parsed)
            
            if result["success"]:
                appointment = result["appointment"]
                return f"Created: {self.calendar_service.format_appointment(appointment)}"
            else:
                return f"Sorry, I couldn't create the appointment. {result.get('error')}"
        except Exception as e:
            return f"Sorry, I encountered an error creating the appointment: {e}"
    
    def _handle_calendar_list(self, entities: Dict, session_id: str, user_input: str = "") -> str:
        """Handle calendar listing"""
        result = self.calendar_service.list_appointments()
        
        if result["success"]:
            appointments = result["appointments"]
            
            # Check if user asked for "next" or "upcoming" appointment
            scope = entities.get("scope", "all")
            user_input_lower = user_input.lower() if user_input else ""
            is_where_query = "where" in user_input_lower or "where is" in user_input_lower
            
            # Check if user asked about appointment on a specific date (e.g., "my appointment on 12th January")
            date_str = entities.get("date")
            if date_str and scope != "next":
                # User asked about appointment on a specific date
                parsed_date = self.calendar_service.parse_date_time(date_str, None)
                target_date = parsed_date["date"]  # Format: YYYY-MM-DD
                
                # Filter appointments matching the date
                matching_appointments = []
                for apt in appointments:
                    apt_start_time = apt.get("start_time", "")
                    if apt_start_time:
                        apt_date = apt_start_time.split("T")[0]  # Get YYYY-MM-DD part
                        if apt_date == target_date:
                            matching_appointments.append(apt)
                
                if len(matching_appointments) == 0:
                    return f"I couldn't find any appointments on {date_str}."
                elif len(matching_appointments) == 1:
                    # Only one appointment on that date
                    appointment = matching_appointments[0]
                    appointment_details = self.calendar_service.format_appointment(appointment)
                    location = appointment.get("location", "").strip()
                    
                    if is_where_query:
                        # User asked "Where is my appointment on 12th January?"
                        if location:
                            return f"Your appointment on {date_str} is: {appointment_details}. It's located at {location}."
                        else:
                            # Location missing - show details and ask for location
                            appointment_id = appointment.get("id")
                            self.conversation_manager.set_context(session_id, "pending_update", {
                                "appointment_id": appointment_id,
                                "_update_field": "location"
                            })
                            self.conversation_manager.set_context(session_id, "pending_intent", "calendar_update")
                            return f"Your appointment on {date_str} is: {appointment_details}. The location is not set. What should be the location?"
                    else:
                        # Regular query - show details with location if available
                        if location:
                            return f"Your appointment on {date_str} is: {appointment_details}. Location: {location}."
                        else:
                            return f"Your appointment on {date_str} is: {appointment_details}."
                else:
                    # Multiple appointments on that date
                    if is_where_query:
                        # List all with locations
                        parts = [f"You have {len(matching_appointments)} appointments on {date_str}:"]
                        for apt in matching_appointments:
                            apt_details = self.calendar_service.format_appointment(apt)
                            apt_location = apt.get("location", "").strip()
                            if apt_location:
                                parts.append(f"{apt_details} at {apt_location}")
                            else:
                                parts.append(f"{apt_details} (location not set)")
                        return ". ".join(parts) + "."
                    else:
                        # Just list them
                        return self.calendar_service.format_appointments_list(matching_appointments)
            
            if scope == "next":
                next_appointment = self.calendar_service.get_next_appointment(appointments)
                if next_appointment:
                    # Format appointment details
                    appointment_details = self.calendar_service.format_appointment(next_appointment)
                    
                    # Check if location exists
                    location = next_appointment.get("location", "").strip()
                    
                    if is_where_query:
                        # User asked "Where is my next appointment?"
                        if location:
                            # Location exists - include it in the response
                            return f"Your next appointment is: {appointment_details}. It's located at {location}."
                        else:
                            # Location missing - show details and ask for location
                            # Store context to update location for this appointment
                            appointment_id = next_appointment.get("id")
                            self.conversation_manager.set_context(session_id, "pending_update", {
                                "appointment_id": appointment_id,
                                "_update_field": "location"
                            })
                            self.conversation_manager.set_context(session_id, "pending_intent", "calendar_update")
                            return f"Your next appointment is: {appointment_details}. The location is not set. What should be the location?"
                    else:
                        # Regular "next appointment" query - just show details
                        if location:
                            return f"Your next appointment is: {appointment_details}. Location: {location}."
                        else:
                            return f"Your next appointment is: {appointment_details}."
                else:
                    return "You have no upcoming appointments."
            
            return self.calendar_service.format_appointments_list(appointments)
        else:
            return f"Sorry, I couldn't fetch your appointments. {result.get('error')}"
    
    def _handle_calendar_get(self, entities: Dict, session_id: str) -> str:
        """Handle getting a specific appointment"""
        context = self.conversation_manager.get_context(session_id)
        pending_get = context.get("pending_get", {})
        
        appointment_id = entities.get("appointment_id") or pending_get.get("appointment_id")
        
        if not appointment_id:
            # Store context and ask for ID
            self.conversation_manager.set_context(session_id, "pending_get", {})
            self.conversation_manager.set_context(session_id, "pending_intent", "calendar_get")
            return "Which appointment would you like to see? Please provide the appointment ID."
        
        # Clear context
        self.conversation_manager.set_context(session_id, "pending_get", {})
        self.conversation_manager.set_context(session_id, "pending_intent", None)
        
        result = self.calendar_service.get_appointment(appointment_id)
        
        if result["success"]:
            appointment = result["appointment"]
            return f"{self.calendar_service.format_appointment(appointment)}"
        else:
            return f"Sorry, I couldn't find that appointment. {result.get('error')}"
    
    def _handle_calendar_update(self, entities: Dict, session_id: str, user_input: str = "") -> str:
        """Handle updating an appointment"""
        context = self.conversation_manager.get_context(session_id)
        pending_update = context.get("pending_update", {})
        
        appointment_id = entities.get("appointment_id") or pending_update.get("appointment_id")
        description = entities.get("description") or pending_update.get("description")
        title = entities.get("title") or pending_update.get("title")
        date_str = entities.get("date") or pending_update.get("date")
        time_str = entities.get("time") or pending_update.get("time")
        start_time_str = entities.get("start_time") or pending_update.get("start_time")
        end_time_str = entities.get("end_time") or pending_update.get("end_time")
        location = entities.get("location") or pending_update.get("location")
        
        # Detect which field the user wants to update based on keywords in user_input
        # This helps us ask for missing new values
        update_field_intent = pending_update.get("_update_field")  # Track which field needs updating
        
        user_input_lower = user_input.lower() if user_input else ""
        if not update_field_intent:
            # Detect update field intent from user input
            # Handle variations like "change the place of", "change place of", "change the place", etc.
            if any(phrase in user_input_lower for phrase in ["change location", "update location", "change the place", "update the place", "change place", "update place", "move to"]):
                update_field_intent = "location"
            elif any(phrase in user_input_lower for phrase in ["change title", "update title", "change the title", "update the title"]):
                update_field_intent = "title"
            elif any(phrase in user_input_lower for phrase in ["change description", "update description", "change the description", "update the description"]):
                update_field_intent = "description"
            elif any(phrase in user_input_lower for phrase in ["change time", "update time", "change the time", "update the time", "reschedule", "change when"]):
                update_field_intent = "time"
            elif any(phrase in user_input_lower for phrase in ["change date", "update date", "change the date", "update the date", "move to date"]):
                update_field_intent = "date"
        
        # If update_field_intent is "title" and we have description but no title, use description as title
        if update_field_intent == "title" and description and not title:
            title = description
            description = None  # Clear description since we're updating title
        
        
        if not appointment_id:
            # Try to find appointment by scope (next, last, etc.) if mentioned
            user_input_lower = user_input.lower() if user_input else ""
            if any(phrase in user_input_lower for phrase in ["next appointment", "next meeting", "next event", "upcoming appointment"]):
                # Find the next appointment
                list_result = self.calendar_service.list_appointments()
                if list_result.get("success"):
                    appointments = list_result.get("appointments", [])
                    next_appointment = self.calendar_service.get_next_appointment(appointments)
                    if next_appointment:
                        appointment_id = next_appointment.get("id")
                    else:
                        return "I couldn't find your next appointment."
                else:
                    return f"Sorry, I couldn't retrieve your appointments. {list_result.get('error')}"
            
            # Try to find appointment(s) by date if date is provided and no appointment_id found yet
            if not appointment_id and date_str:
                # Parse the date to find matching appointments
                parsed_date = self.calendar_service.parse_date_time(date_str, None)
                target_date = parsed_date["date"]  # Format: YYYY-MM-DD
                
                
                # List all appointments to find matches for the date
                list_result = self.calendar_service.list_appointments()
                if list_result.get("success"):
                    appointments = list_result.get("appointments", [])
                    # Filter appointments matching the date
                    matching_appointments = []
                    for apt in appointments:
                        apt_start_time = apt.get("start_time", "")
                        # Extract date from ISO format (YYYY-MM-DDTHH:MM)
                        if apt_start_time:
                            apt_date = apt_start_time.split("T")[0]  # Get YYYY-MM-DD part
                            if apt_date == target_date:
                                matching_appointments.append(apt)
                    
                    
                    if len(matching_appointments) == 0:
                        # No appointments found for that date
                        return f"I couldn't find any appointments on {date_str}. Please check the date or provide the appointment ID."
                    elif len(matching_appointments) == 1:
                        # Only one appointment - check if we have the new value
                        if update_field_intent:
                            if update_field_intent == "location" and not location:
                                # Store context and ask for location
                                pending_update["_update_field"] = update_field_intent
                                pending_update["description"] = description
                                pending_update["date"] = date_str
                                pending_update["time"] = time_str
                                pending_update["appointment_id"] = matching_appointments[0]["id"]
                                self.conversation_manager.set_context(session_id, "pending_update", pending_update)
                                self.conversation_manager.set_context(session_id, "pending_intent", "calendar_update")
                                apt_title = matching_appointments[0].get("title", matching_appointments[0].get("description", "Untitled"))
                                return f"I found one appointment on {date_str}: {apt_title}. What should be the new location?"
                            elif update_field_intent == "title" and not title:
                                # Store context and ask for title
                                pending_update["_update_field"] = update_field_intent
                                pending_update["description"] = description
                                pending_update["date"] = date_str
                                pending_update["time"] = time_str
                                pending_update["location"] = location
                                pending_update["appointment_id"] = matching_appointments[0]["id"]
                                self.conversation_manager.set_context(session_id, "pending_update", pending_update)
                                self.conversation_manager.set_context(session_id, "pending_intent", "calendar_update")
                                apt_title = matching_appointments[0].get("title", matching_appointments[0].get("description", "Untitled"))
                                return f"I found one appointment on {date_str}: {apt_title}. What should be the new title?"
                            elif update_field_intent == "description" and not description:
                                # Store context and ask for description
                                pending_update["_update_field"] = update_field_intent
                                pending_update["date"] = date_str
                                pending_update["time"] = time_str
                                pending_update["location"] = location
                                pending_update["appointment_id"] = matching_appointments[0]["id"]
                                self.conversation_manager.set_context(session_id, "pending_update", pending_update)
                                self.conversation_manager.set_context(session_id, "pending_intent", "calendar_update")
                                apt_title = matching_appointments[0].get("title", matching_appointments[0].get("description", "Untitled"))
                                return f"I found one appointment on {date_str}: {apt_title}. What should be the new description?"
                            elif update_field_intent == "time" and not time_str:
                                # Store context and ask for time
                                pending_update["_update_field"] = update_field_intent
                                pending_update["description"] = description
                                pending_update["date"] = date_str
                                pending_update["location"] = location
                                pending_update["appointment_id"] = matching_appointments[0]["id"]
                                self.conversation_manager.set_context(session_id, "pending_update", pending_update)
                                self.conversation_manager.set_context(session_id, "pending_intent", "calendar_update")
                                apt_title = matching_appointments[0].get("title", matching_appointments[0].get("description", "Untitled"))
                                return f"I found one appointment on {date_str}: {apt_title}. What should be the new time?"
                        
                        # Only one appointment - use it directly!
                        appointment_id = matching_appointments[0]["id"]
                        # Continue with update (will fall through to update code below)
                    else:
                        # Multiple appointments - check if we have the new value, if not ask for it first
                        if update_field_intent:
                            new_value = None
                            if update_field_intent == "location" and not location:
                                pending_update["_update_field"] = update_field_intent
                                pending_update["description"] = description
                                pending_update["date"] = date_str
                                pending_update["time"] = time_str
                                self.conversation_manager.set_context(session_id, "pending_update", pending_update)
                                self.conversation_manager.set_context(session_id, "pending_intent", "calendar_update")
                                return f"I found {len(matching_appointments)} appointments on {date_str}. What should be the new location?"
                            elif update_field_intent == "title" and not title:
                                pending_update["_update_field"] = update_field_intent
                                pending_update["description"] = description
                                pending_update["date"] = date_str
                                pending_update["time"] = time_str
                                pending_update["location"] = location
                                self.conversation_manager.set_context(session_id, "pending_update", pending_update)
                                self.conversation_manager.set_context(session_id, "pending_intent", "calendar_update")
                                return f"I found {len(matching_appointments)} appointments on {date_str}. What should be the new title?"
                            elif update_field_intent == "description" and not description:
                                pending_update["_update_field"] = update_field_intent
                                pending_update["date"] = date_str
                                pending_update["time"] = time_str
                                pending_update["location"] = location
                                self.conversation_manager.set_context(session_id, "pending_update", pending_update)
                                self.conversation_manager.set_context(session_id, "pending_intent", "calendar_update")
                                return f"I found {len(matching_appointments)} appointments on {date_str}. What should be the new description?"
                            elif update_field_intent == "time" and not time_str:
                                pending_update["_update_field"] = update_field_intent
                                pending_update["description"] = description
                                pending_update["date"] = date_str
                                pending_update["location"] = location
                                self.conversation_manager.set_context(session_id, "pending_update", pending_update)
                                self.conversation_manager.set_context(session_id, "pending_intent", "calendar_update")
                                return f"I found {len(matching_appointments)} appointments on {date_str}. What should be the new time?"
                        
                        # If we have the new value (or no specific field intent), list appointments and ask which one
                        pending_update["title"] = title
                        pending_update["description"] = description
                        pending_update["date"] = date_str
                        pending_update["time"] = time_str
                        pending_update["location"] = location
                        if update_field_intent:
                            pending_update["_update_field"] = update_field_intent
                        self.conversation_manager.set_context(session_id, "pending_update", pending_update)
                        self.conversation_manager.set_context(session_id, "pending_intent", "calendar_update")
                        
                        # Build list of appointments with descriptions
                        apt_list = []
                        for i, apt in enumerate(matching_appointments, 1):
                            apt_title = apt.get("title", apt.get("description", "Untitled"))
                            apt_time = apt.get("start_time", "")
                            # Extract time from ISO format
                            if apt_time and "T" in apt_time:
                                time_part = apt_time.split("T")[1][:5]  # Get HH:MM
                                apt_list.append(f"{i}. {apt_title} at {time_part}")
                            else:
                                apt_list.append(f"{i}. {apt_title}")
                        
                        return f"I found {len(matching_appointments)} appointments on {date_str}: {', '.join(apt_list)}. Which one would you like to update? Please say the number or appointment ID."
            
            # Check if we're waiting for a new value for a specific field
            if update_field_intent:
                if update_field_intent == "location" and not location:
                    # Store context and ask for location
                    pending_update["_update_field"] = update_field_intent
                    pending_update["title"] = title
                    pending_update["description"] = description
                    pending_update["date"] = date_str
                    pending_update["time"] = time_str
                    self.conversation_manager.set_context(session_id, "pending_update", pending_update)
                    self.conversation_manager.set_context(session_id, "pending_intent", "calendar_update")
                    return "What should be the new location?"
                elif update_field_intent == "title" and not title:
                    # Store context and ask for title
                    pending_update["_update_field"] = update_field_intent
                    pending_update["description"] = description
                    pending_update["date"] = date_str
                    pending_update["time"] = time_str
                    pending_update["location"] = location
                    self.conversation_manager.set_context(session_id, "pending_update", pending_update)
                    self.conversation_manager.set_context(session_id, "pending_intent", "calendar_update")
                    return "What should be the new title?"
                elif update_field_intent == "description" and not description:
                    # Store context and ask for description
                    pending_update["_update_field"] = update_field_intent
                    pending_update["date"] = date_str
                    pending_update["time"] = time_str
                    pending_update["location"] = location
                    self.conversation_manager.set_context(session_id, "pending_update", pending_update)
                    self.conversation_manager.set_context(session_id, "pending_intent", "calendar_update")
                    return "What should be the new description?"
                elif update_field_intent == "time" and not time_str:
                    # Store context and ask for time
                    pending_update["_update_field"] = update_field_intent
                    pending_update["description"] = description
                    pending_update["date"] = date_str
                    pending_update["location"] = location
                    self.conversation_manager.set_context(session_id, "pending_update", pending_update)
                    self.conversation_manager.set_context(session_id, "pending_intent", "calendar_update")
                    return "What should be the new time?"
            
            # If no date provided or still no appointment_id, ask for ID
            if title or description or date_str or time_str or location:
                pending_update["title"] = title
                pending_update["description"] = description
                pending_update["date"] = date_str
                pending_update["time"] = time_str
                pending_update["location"] = location
                if update_field_intent:
                    pending_update["_update_field"] = update_field_intent
                self.conversation_manager.set_context(session_id, "pending_update", pending_update)
                self.conversation_manager.set_context(session_id, "pending_intent", "calendar_update")
            
            if not appointment_id:
                return "Which appointment would you like to update? Please provide the appointment ID or date."
        
        # Clear context after extracting values (but before update)
        self.conversation_manager.set_context(session_id, "pending_update", {})
        self.conversation_manager.set_context(session_id, "pending_intent", None)
        
        # Parse date and time if provided
        date = None
        time = None
        start_time = None
        end_time = None
        
        # Parse date
        if date_str:
            parsed_date = self.calendar_service.parse_date_time(date_str, None)
            date = parsed_date["date"]
        
        # Parse time (single time - for backward compatibility)
        if time_str:
            parsed_time = self.calendar_service.parse_date_time(None, time_str)
            time = parsed_time["time"]
        
        # Parse start_time and end_time separately
        if start_time_str:
            parsed_start = self.calendar_service.parse_date_time(None, start_time_str)
            start_time = parsed_start["time"]
        if end_time_str:
            parsed_end = self.calendar_service.parse_date_time(None, end_time_str)
            end_time = parsed_end["time"]
        
        # Only send fields that are actually being updated (not fields used to identify the appointment)
        # If update_field_intent is set, only send that field (plus date if updating date/time)
        # If update_field_intent is not set, send all provided fields
        final_title = None
        final_description = None
        final_date = None
        final_time = None
        final_start_time = None
        final_end_time = None
        final_location = None
        
        if update_field_intent:
            # Only update the specific field the user requested
            if update_field_intent == "title":
                final_title = title
            elif update_field_intent == "description":
                final_description = description
            elif update_field_intent == "location":
                final_location = location
            elif update_field_intent == "date":
                final_date = date
                # When updating date, we also need to update start_time and end_time (handled in calendar_service)
            elif update_field_intent == "time":
                final_time = time
                final_start_time = start_time
                final_end_time = end_time
        else:
            # No specific field intent - send all provided fields (user might be updating multiple fields)
            final_title = title
            final_description = description
            final_date = date
            final_time = time
            final_start_time = start_time
            final_end_time = end_time
            final_location = location
        
        result = self.calendar_service.update_appointment(
            appointment_id, title=final_title, description=final_description, date=final_date, time=final_time, 
            location=final_location, start_time=final_start_time, end_time=final_end_time
        )
        
        if result["success"]:
            appointment = result["appointment"]
            return f"Updated: {self.calendar_service.format_appointment(appointment)}"
        else:
            return f"Sorry, I couldn't update the appointment. {result.get('error')}"
    
    def _handle_calendar_delete(self, entities: Dict, session_id: str, user_input: str = "") -> str:
        """Handle deleting an appointment"""
        context = self.conversation_manager.get_context(session_id)
        pending_delete = context.get("pending_delete", {})
        
        appointment_id = entities.get("appointment_id") or pending_delete.get("appointment_id")
        
        
        # Initialize appointment_title variable
        appointment_title = None
        
        # Check if user is referring to "previously created", "last", "most recent", etc.
        user_input_lower = user_input.lower() if user_input else ""
        if not appointment_id and any(phrase in user_input_lower for phrase in ["previously created", "last created", "most recent", "last appointment", "previous appointment", "recently created"]):
            # Find the most recently created appointment (highest ID)
            list_result = self.calendar_service.list_appointments()
            if list_result.get("success"):
                appointments = list_result.get("appointments", [])
                if appointments:
                    # Sort by ID (highest first) - assuming IDs are sequential and higher = more recent
                    appointments_sorted = sorted(appointments, key=lambda apt: apt.get("id", 0), reverse=True)
                    most_recent = appointments_sorted[0]
                    appointment_id = most_recent.get("id")
                    appointment_title = most_recent.get('title', most_recent.get('description', 'Untitled'))
                else:
                    return "I couldn't find any appointments to delete."
            else:
                return f"Sorry, I couldn't retrieve your appointments. {list_result.get('error')}"
        
        if not appointment_id:
            # Store context and ask for ID
            self.conversation_manager.set_context(session_id, "pending_delete", {})
            self.conversation_manager.set_context(session_id, "pending_intent", "calendar_delete")
            return "Which appointment would you like to delete? Please provide the appointment ID."
        
        # Ensure appointment_id is an integer
        try:
            appointment_id = int(appointment_id)
        except (ValueError, TypeError) as e:
            print(f"[DialogManager] Error converting appointment_id to int: {e}")
            return f"Invalid appointment ID: {appointment_id}. Please provide a valid number."
        
        # Clear context
        self.conversation_manager.set_context(session_id, "pending_delete", {})
        self.conversation_manager.set_context(session_id, "pending_intent", None)
        
        # If appointment_title not set yet, try to get it from the appointment before deletion
        if not appointment_title:
            get_result = self.calendar_service.get_appointment(appointment_id)
            if get_result.get("success"):
                appointment = get_result.get("appointment", {})
                appointment_title = appointment.get("title", appointment.get("description", f"ID {appointment_id}"))
            else:
                appointment_title = f"ID {appointment_id}"
        
        result = self.calendar_service.delete_appointment(appointment_id)
        
        if result["success"]:
            return f"Deleted appointment {appointment_title}."
        else:
            return f"Sorry, I couldn't delete the appointment. {result.get('error')}"
    
    def _handle_unknown(self) -> str:
        """Handle unknown intent"""
        return ("I'm not sure I understood that. I can help you with weather forecasts "
                "and calendar management. What would you like to do?")
