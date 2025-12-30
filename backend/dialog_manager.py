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
        # 1. Get existing context (ONLY from current session - no global fallback)
        context = self.conversation_manager.get_context(session_id)
        pending_intent = context.get("pending_intent")
        # Only get history from current session
        history = self.conversation_manager.get_history(session_id)
        
        # 2. Parse input (Pass history to NLU to help it resolve UNKNOWN intents)
        nlu_result = self.nlu.parse(user_input, history)
        intent = nlu_result["intent"]
        entities = nlu_result["entities"]
        
        # 3. SMART CONTEXT HANDLING
        # If the NLU is confused (UNKNOWN) but we are in the middle of a task, 
        # assume the user is answering a follow-up question.
        if pending_intent and intent == Intent.UNKNOWN.value:
            intent = pending_intent
            print(f"[DialogManager] Recovered intent '{intent}' from context for input: '{user_input}'")
            
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
                        print(f"[DialogManager] Using last known location from current session: {entities['location']}")
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
                    print(f"[DialogManager] Merging entities with pending_appointment: {pending_appointment}")
                    # Merge: new entities override pending, but keep pending if new is missing
                    if not entities.get("description") and pending_appointment.get("description"):
                        entities["description"] = pending_appointment["description"]
                    if not entities.get("date") and pending_appointment.get("date"):
                        entities["date"] = pending_appointment["date"]
                    if not entities.get("time") and pending_appointment.get("time"):
                        entities["time"] = pending_appointment["time"]
                    print(f"[DialogManager] Merged entities: {entities}")
        
        # 4. INTENT SWITCHING LOGIC
        # Only clear context if a NEW, DIFFERENT, and VALID intent is detected.
        # Do NOT clear context if intent is UNKNOWN (could be speech recognition error)
        elif pending_intent and intent != pending_intent:
            if intent != Intent.UNKNOWN.value:
                # Only clear if the new intent is a specific, known intent that's different
                # This prevents clearing context on speech recognition errors
                print(f"[DialogManager] Intent switch: {pending_intent} -> {intent}. Clearing old context.")
                self.conversation_manager.clear_context(session_id)
            else:
                # If current intent is UNKNOWN, keep the pending intent active
                # This handles cases like "Frank food" (speech error) when expecting location
                intent = pending_intent
                print(f"[DialogManager] Intent is UNKNOWN, keeping pending intent '{intent}' (possible speech recognition error)")
        
        print(f"[DialogManager] Final Intent: {intent}, Entities: {entities}")
        
        # 5. Save user turn (with entities so location can be retrieved later)
        self.conversation_manager.add_turn(session_id, "user", user_input, intent, entities)
        
        # 6. Handle the intent and generate response (pass user_input for fallback logic)
        response_text = self._handle_intent(intent, entities, session_id, user_input)
        
        # 7. Save assistant turn
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
            return self._handle_calendar_list(entities, session_id)
        
        elif intent == Intent.CALENDAR_GET.value:
            return self._handle_calendar_get(entities, session_id)
        
        elif intent == Intent.CALENDAR_UPDATE.value:
            return self._handle_calendar_update(entities, session_id)
        
        elif intent == Intent.CALENDAR_DELETE.value:
            return self._handle_calendar_delete(entities, session_id)
        
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
                print(f"[DialogManager] Resolved 'there' to location from global lookup: {location}")
            # Remove the marker
            if "_needs_location_resolution" in entities:
                del entities["_needs_location_resolution"]
        
        # If location is still missing, try to get it from database history
        if not location:
            # First try: Get last known location from database
            last_location = self.conversation_manager.get_last_known_location(session_id)
            if last_location:
                location = last_location
                print(f"[DialogManager] Using last known location from database: {location}")
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
                            print(f"[DialogManager] Resolved location from conversation history: {location}")
                            break
                    elif turn.get("role") == "user":
                        # Extract location from user's previous query
                        user_text = turn.get("text", "")
                        location_match = re.search(r'\b(?:in|for|at)\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)?)\b', user_text)
                        if location_match:
                            location = location_match.group(1)
                            print(f"[DialogManager] Resolved location from user's previous query: {location}")
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
                print(f"[DialogManager] Using default location: {location}")
        
        # Store location in context and database for future reference
        if location and location.lower() != "zurich":
            pending_weather["location"] = location
            self.conversation_manager.set_context(session_id, "pending_weather", pending_weather)
            # Store as last known location (for cross-session lookup)
            self.conversation_manager.set_context(session_id, "last_location", location)
            print(f"[DialogManager] Stored location '{location}' in context_store for session {session_id}")
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
                    print(f"[DialogManager] Detected follow-up conversation - using pending_appointment values (pending fields: {pending_fields_count}, current entities: {current_entities_count})")
                else:
                    print(f"[DialogManager] All fields complete in pending_appointment - treating as fresh creation")
                    pending_appointment = {}
            else:
                print(f"[DialogManager] No pending fields - fresh creation")
                pending_appointment = {}
        else:
            print(f"[DialogManager] No pending intent or appointment - fresh creation")
            pending_appointment = {}
        
        # Merge entities with pending appointment data (only if follow-up)
        if is_follow_up:
            description = entities.get("description") or pending_appointment.get("description")
            date_str = entities.get("date") or pending_appointment.get("date")
            start_time = entities.get("start_time") or pending_appointment.get("start_time")
            end_time = entities.get("end_time") or pending_appointment.get("end_time")
            # Fallback to old "time" field if start_time not provided
            if not start_time:
                time_str = entities.get("time") or pending_appointment.get("time")
                if time_str:
                    start_time = time_str
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
        
        print(f"[DialogManager] Calendar create entities: description='{description}', date='{date_str}', start_time='{start_time}', end_time='{end_time}'")
        print(f"[DialogManager] Full entities dictionary from NLU: {entities}")
        print(f"[DialogManager] Pending appointment context: {pending_appointment}")
        print(f"[DialogManager] Is follow-up: {is_follow_up}")
        
        # Check: If user says "12 p.m.", ensure it's treated as time, not date
        # If entities has a "date" that looks like a time (e.g., "12" with pm/am), move it to start_time
        if entities.get("date") and not start_time:
            date_value = entities.get("date", "").lower().strip()
            # Check if date looks like a time (contains pm/am or is just a number)
            if "pm" in date_value or "am" in date_value or (date_value.isdigit() and len(date_value) <= 2):
                print(f"[DialogManager] WARNING: Date '{date_value}' looks like a time, checking if it should be start_time")
                # If it's a number or has pm/am, it's likely a time, not a date
                if "pm" in date_value or "am" in date_value or (date_value.isdigit() and int(date_value) <= 23):
                    start_time = date_value.replace('.', '').replace(' ', '')
                    entities["start_time"] = start_time
                    entities["date"] = None  # Clear the incorrect date
                    print(f"[DialogManager] Moved '{date_value}' from date to start_time: '{start_time}'")
        
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
                    print(f"[DialogManager] FALLBACK: Using short input '{user_input}' as description: '{description}'")
        
        # FALLBACK: If start_time is missing and user_input is short, treat it as start_time
        if not start_time and pending_appointment and len(user_input.split()) < 5:
            # Check if we're waiting for start_time (pending_appointment has description and date but no start_time)
            if pending_appointment.get("description") and pending_appointment.get("date") and not pending_appointment.get("start_time"):
                # Clean up the input
                clean_input = user_input.strip().rstrip('.,!?;:')
                # Check if it looks like a time (contains numbers and possibly AM/PM)
                if re.search(r'\d', clean_input):
                    start_time = clean_input
                    print(f"[DialogManager] FALLBACK: Using short input '{user_input}' as start_time: '{start_time}'")
        
        # Check for missing fields - ALL fields are required (description, date, start_time, AND end_time)
        # Also check for empty strings (not just None)
        missing_fields = []
        if not description or not description.strip():
            missing_fields.append("description")
        if not date_str or not date_str.strip():
            missing_fields.append("date")
        if not start_time or not start_time.strip():
            missing_fields.append("start_time")
        if not end_time or not end_time.strip():
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
                fields_str = " and ".join(missing_fields)
                return f"I need {fields_str} for the appointment. Please provide them."
            else:
                return "I need a description, date, start time, and end time for the appointment. Please provide all of them."
        
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
                fields_str = " and ".join(missing_fields)
                return f"I need {fields_str} for the appointment. Please provide them."
            else:
                return "I need a description, date, start time, and end time for the appointment. Please provide all of them."
        
        print(f"[DialogManager] All fields present. Creating appointment: description='{description}', date='{date_str}', start_time='{start_time}', end_time='{end_time}'")
        
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
            
            print(f"[DialogManager] About to parse times: start_time='{start_time}' (type: {type(start_time)}), end_time='{end_time}' (type: {type(end_time)})")
            
            parsed_start = self.calendar_service.parse_date_time(None, start_time)
            print(f"[DialogManager] Parsed start_time result: {parsed_start}")
            start_time_parsed = parsed_start["time"]
            
            parsed_end = self.calendar_service.parse_date_time(None, end_time)
            print(f"[DialogManager] Parsed end_time result: {parsed_end}")
            end_time_parsed = parsed_end["time"]
            
            print(f"[DialogManager] Parsed date/time: date='{date}', start_time='{start_time_parsed}', end_time='{end_time_parsed}'")
        except Exception as e:
            print(f"[DialogManager] Date/time parsing error: {e}")
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
            print(f"[DialogManager] Appointment creation error: {e}")
            return f"Sorry, I encountered an error creating the appointment: {e}"
    
    def _handle_calendar_list(self, entities: Dict, session_id: str) -> str:
        """Handle calendar listing"""
        result = self.calendar_service.list_appointments()
        
        if result["success"]:
            appointments = result["appointments"]
            
            # Check if user asked for "next" or "upcoming" appointment
            scope = entities.get("scope", "all")
            if scope == "next":
                next_appointment = self.calendar_service.get_next_appointment(appointments)
                if next_appointment:
                    return f"Your next appointment is: {self.calendar_service.format_appointment(next_appointment)}."
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
    
    def _handle_calendar_update(self, entities: Dict, session_id: str) -> str:
        """Handle updating an appointment"""
        context = self.conversation_manager.get_context(session_id)
        pending_update = context.get("pending_update", {})
        
        appointment_id = entities.get("appointment_id") or pending_update.get("appointment_id")
        description = entities.get("description") or pending_update.get("description")
        date_str = entities.get("date") or pending_update.get("date")
        time_str = entities.get("time") or pending_update.get("time")
        
        if not appointment_id:
            # Store what we have and ask for ID
            if description or date_str or time_str:
                pending_update["description"] = description
                pending_update["date"] = date_str
                pending_update["time"] = time_str
                self.conversation_manager.set_context(session_id, "pending_update", pending_update)
                self.conversation_manager.set_context(session_id, "pending_intent", "calendar_update")
            return "Which appointment would you like to update? Please provide the appointment ID."
        
        # Clear context
        self.conversation_manager.set_context(session_id, "pending_update", {})
        self.conversation_manager.set_context(session_id, "pending_intent", None)
        
        # Parse date and time if provided
        date = None
        time = None
        if date_str or time_str:
            parsed = self.calendar_service.parse_date_time(date_str, time_str)
            date = parsed["date"] if date_str else None
            time = parsed["time"] if time_str else None
        
        result = self.calendar_service.update_appointment(
            appointment_id, description=description, date=date, time=time
        )
        
        if result["success"]:
            appointment = result["appointment"]
            return f"Updated: {self.calendar_service.format_appointment(appointment)}"
        else:
            return f"Sorry, I couldn't update the appointment. {result.get('error')}"
    
    def _handle_calendar_delete(self, entities: Dict, session_id: str) -> str:
        """Handle deleting an appointment"""
        context = self.conversation_manager.get_context(session_id)
        pending_delete = context.get("pending_delete", {})
        
        appointment_id = entities.get("appointment_id") or pending_delete.get("appointment_id")
        
        print(f"[DialogManager] Delete handler - entities: {entities}")
        print(f"[DialogManager] Delete handler - pending_delete: {pending_delete}")
        print(f"[DialogManager] Delete handler - appointment_id: {appointment_id} (type: {type(appointment_id)})")
        
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
        
        print(f"[DialogManager] Calling delete_appointment API with ID: {appointment_id}")
        result = self.calendar_service.delete_appointment(appointment_id)
        print(f"[DialogManager] Delete API result: {result}")
        
        if result["success"]:
            return f"Deleted appointment {appointment_id}."
        else:
            return f"Sorry, I couldn't delete the appointment. {result.get('error')}"
    
    def _handle_unknown(self) -> str:
        """Handle unknown intent"""
        return ("I'm not sure I understood that. I can help you with weather forecasts "
                "and calendar management. What would you like to do?")
