"""
Dialog Manager

Orchestrates the conversation flow, integrating NLU, services, and conversation management.
"""

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
        Process user input and generate a response
        
        Args:
            user_input: The user's spoken input
            session_id: Unique session identifier
            
        Returns:
            Dictionary with response text and metadata
        """
        # Get conversation history for context
        history = self.conversation_manager.get_history(session_id)
        
        # Parse user input
        nlu_result = self.nlu.parse(user_input, history)
        intent = nlu_result["intent"]
        entities = nlu_result["entities"]
        
        print(f"[DialogManager] Intent: {intent}, Entities: {entities}")
        
        # Save user turn
        self.conversation_manager.add_turn(session_id, "user", user_input, intent)
        
        # Handle intent
        response_text = self._handle_intent(intent, entities, session_id)
        
        # Save assistant turn
        self.conversation_manager.add_turn(session_id, "assistant", response_text, intent)
        
        return {
            "response": response_text,
            "intent": intent,
            "entities": entities
        }
    
    def _handle_intent(self, intent: str, entities: Dict, session_id: str) -> str:
        """Route to appropriate intent handler"""
        
        if intent == Intent.GREETING.value:
            return self._handle_greeting()
        
        elif intent == Intent.HELP.value:
            return self._handle_help()
        
        elif intent == Intent.WEATHER_QUERY.value:
            return self._handle_weather_query(entities)
        
        elif intent == Intent.CALENDAR_CREATE.value:
            return self._handle_calendar_create(entities)
        
        elif intent == Intent.CALENDAR_LIST.value:
            return self._handle_calendar_list(entities)
        
        elif intent == Intent.CALENDAR_GET.value:
            return self._handle_calendar_get(entities)
        
        elif intent == Intent.CALENDAR_UPDATE.value:
            return self._handle_calendar_update(entities)
        
        elif intent == Intent.CALENDAR_DELETE.value:
            return self._handle_calendar_delete(entities)
        
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
    
    def _handle_weather_query(self, entities: Dict) -> str:
        """Handle weather query"""
        location = entities.get("location", "zurich")
        
        # Fetch forecast
        forecast_data = self.weather_service.get_forecast(location=location)
        
        # Format and return
        return self.weather_service.format_forecast(forecast_data)
    
    def _handle_calendar_create(self, entities: Dict) -> str:
        """Handle calendar creation"""
        description = entities.get("description")
        date_str = entities.get("date")
        time_str = entities.get("time")
        
        if not description:
            return "I need a description for the appointment. What is it for?"
        
        # Parse date and time
        parsed = self.calendar_service.parse_date_time(date_str, time_str)
        date = parsed["date"]
        time = parsed["time"]
        
        # Create appointment
        result = self.calendar_service.create_appointment(description, date, time)
        
        if result["success"]:
            appointment = result["appointment"]
            return f"I've created your appointment: {self.calendar_service.format_appointment(appointment)}"
        else:
            return f"Sorry, I couldn't create the appointment. Error: {result.get('error')}"
    
    def _handle_calendar_list(self, entities: Dict) -> str:
        """Handle calendar listing"""
        result = self.calendar_service.list_appointments()
        
        if result["success"]:
            appointments = result["appointments"]
            return self.calendar_service.format_appointments_list(appointments)
        else:
            return f"Sorry, I couldn't fetch your appointments. Error: {result.get('error')}"
    
    def _handle_calendar_get(self, entities: Dict) -> str:
        """Handle getting a specific appointment"""
        appointment_id = entities.get("appointment_id")
        
        if not appointment_id:
            return "Please specify the appointment ID you want to see."
        
        result = self.calendar_service.get_appointment(appointment_id)
        
        if result["success"]:
            appointment = result["appointment"]
            return f"Here's the appointment: {self.calendar_service.format_appointment(appointment)}"
        else:
            return f"Sorry, I couldn't find that appointment. Error: {result.get('error')}"
    
    def _handle_calendar_update(self, entities: Dict) -> str:
        """Handle updating an appointment"""
        appointment_id = entities.get("appointment_id")
        description = entities.get("description")
        date_str = entities.get("date")
        time_str = entities.get("time")
        
        if not appointment_id:
            return "Please specify which appointment ID you want to update."
        
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
            return f"I've updated your appointment: {self.calendar_service.format_appointment(appointment)}"
        else:
            return f"Sorry, I couldn't update the appointment. Error: {result.get('error')}"
    
    def _handle_calendar_delete(self, entities: Dict) -> str:
        """Handle deleting an appointment"""
        appointment_id = entities.get("appointment_id")
        
        if not appointment_id:
            return "Please specify which appointment ID you want to delete."
        
        result = self.calendar_service.delete_appointment(appointment_id)
        
        if result["success"]:
            return f"I've deleted appointment {appointment_id}."
        else:
            return f"Sorry, I couldn't delete the appointment. Error: {result.get('error')}"
    
    def _handle_unknown(self) -> str:
        """Handle unknown intent"""
        return ("I'm not sure I understood that. I can help you with weather forecasts "
                "and calendar management. What would you like to do?")
