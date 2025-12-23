"""
Natural Language Understanding (NLU) Module

Handles intent recognition and entity extraction for the voice assistant.
"""

import re
from enum import Enum
from typing import Dict, List, Optional, Any
from datetime import datetime
import spacy

# Load spaCy model for NER
try:
    nlp = spacy.load("en_core_web_sm")
except:
    import subprocess
    print("[NLU] Downloading spaCy model...")
    subprocess.run(["python", "-m", "spacy", "download", "en_core_web_sm"], check=True)
    nlp = spacy.load("en_core_web_sm")


class Intent(Enum):
    # Weather intents
    WEATHER_QUERY = "weather_query"
    
    # Calendar intents
    CALENDAR_CREATE = "calendar_create"
    CALENDAR_LIST = "calendar_list"
    CALENDAR_GET = "calendar_get"
    CALENDAR_UPDATE = "calendar_update"
    CALENDAR_DELETE = "calendar_delete"
    
    # General
    GREETING = "greeting"
    HELP = "help"
    UNKNOWN = "unknown"


class NLU:
    """Natural Language Understanding for intent and entity recognition"""
    
    def __init__(self):
        self.intent_patterns = {
            Intent.GREETING: [
                r"\b(hello|hi|hey|good morning|good afternoon|good evening)\b",
            ],
            Intent.HELP: [
                r"\b(help|what can you do|capabilities)\b",
            ],
            Intent.WEATHER_QUERY: [
                r"\b(weather|temperature|forecast|rain|snow|sunny|cloudy)\b",
                r"\b(how.*weather|what.*weather|will it rain|will it snow)\b",
            ],
            Intent.CALENDAR_CREATE: [
                r"\b(create|add|schedule|book|make).*\b(appointment|meeting|event)\b",
                r"\b(schedule me|book me|set up)\b",
            ],
            Intent.CALENDAR_LIST: [
                r"\b(list|show|get|what|tell me).*\b(appointments|meetings|events|calendar|schedule)\b",
                r"\b(what do i have|what's on my|what is on my)\b",
            ],
            Intent.CALENDAR_GET: [
                r"\b(get|show|what is).*\b(appointment|meeting|event)\b.*\b(id|number)\b",
                r"\b(details of|information about|tell me about).*\b(appointment|meeting|event)\b",
            ],
            Intent.CALENDAR_UPDATE: [
                r"\b(update|change|modify|edit|reschedule).*\b(appointment|meeting|event)\b",
                r"\b(move|shift|postpone)\b",
            ],
            Intent.CALENDAR_DELETE: [
                r"\b(delete|remove|cancel).*\b(appointment|meeting|event)\b",
                r"\b(cancel my)\b",
            ],
        }
        
        self.weather_keywords = ["weather", "temperature", "forecast", "rain", "snow", "sunny", "cold", "hot"]
        self.calendar_keywords = ["appointment", "meeting", "event", "schedule", "calendar"]
    
    def parse(self, text: str, conversation_history: List[Dict] = None) -> Dict[str, Any]:
        """
        Parse user input to extract intent and entities
        
        Args:
            text: User input text
            conversation_history: Previous conversation turns for context
            
        Returns:
            Dictionary with intent and extracted entities
        """
        text_lower = text.lower()
        
        # Detect intent
        intent = self._detect_intent(text_lower)
        
        # Extract entities based on intent
        entities = {}
        if intent in [Intent.WEATHER_QUERY]:
            entities = self._extract_weather_entities(text, text_lower)
        elif intent in [Intent.CALENDAR_CREATE, Intent.CALENDAR_UPDATE]:
            entities = self._extract_calendar_entities(text, text_lower)
        elif intent in [Intent.CALENDAR_GET, Intent.CALENDAR_DELETE]:
            entities = self._extract_calendar_id_entities(text, text_lower)
        elif intent == Intent.CALENDAR_LIST:
            entities = self._extract_list_entities(text, text_lower)
        
        return {
            "intent": intent.value,
            "entities": entities,
            "original_text": text
        }
    
    def _detect_intent(self, text_lower: str) -> Intent:
        """Detect the user's intent from text"""
        # Check each intent pattern
        for intent, patterns in self.intent_patterns.items():
            for pattern in patterns:
                if re.search(pattern, text_lower):
                    return intent
        
        return Intent.UNKNOWN
    
    def _extract_weather_entities(self, text: str, text_lower: str) -> Dict[str, Any]:
        """Extract weather-related entities"""
        entities = {}
        
        # Extract location using spaCy NER
        doc = nlp(text)
        locations = [ent.text for ent in doc.ents if ent.label_ in ["GPE", "LOC"]]
        if locations:
            entities["location"] = locations[0]
        
        # Extract date/time
        dates = [ent.text for ent in doc.ents if ent.label_ == "DATE"]
        if dates:
            entities["date"] = dates[0]
        
        # Check for specific weather conditions
        conditions = ["rain", "snow", "sunny", "cloudy", "temperature", "forecast"]
        for condition in conditions:
            if condition in text_lower:
                entities["condition"] = condition
                break
        
        return entities
    
    def _extract_calendar_entities(self, text: str, text_lower: str) -> Dict[str, Any]:
        """Extract calendar-related entities (for create/update)"""
        entities = {}
        
        doc = nlp(text)
        
        # Extract dates and times
        for ent in doc.ents:
            if ent.label_ == "DATE":
                entities["date"] = ent.text
            elif ent.label_ == "TIME":
                entities["time"] = ent.text
        
        # Extract description (everything after certain keywords)
        desc_patterns = [
            r"(?:for|about|regarding|titled|called)\s+(.+)",
            r"(?:appointment|meeting|event)\s+(?:for|about|with)\s+(.+)",
        ]
        for pattern in desc_patterns:
            match = re.search(pattern, text_lower)
            if match:
                entities["description"] = match.group(1).strip()
                break
        
        # If no description found, use the whole text minus action words
        if "description" not in entities:
            # Remove common action words
            cleaned = re.sub(r'\b(create|add|schedule|book|make|appointment|meeting|event|for|me|a|an|the)\b', '', text_lower).strip()
            if cleaned:
                entities["description"] = cleaned
        
        return entities
    
    def _extract_calendar_id_entities(self, text: str, text_lower: str) -> Dict[str, Any]:
        """Extract calendar ID for get/delete operations"""
        entities = {}
        
        # Look for appointment ID (numeric)
        id_match = re.search(r'\b(?:id|number|appointment)\s*(\d+)\b', text_lower)
        if id_match:
            entities["appointment_id"] = int(id_match.group(1))
        else:
            # Look for standalone number
            num_match = re.search(r'\b(\d+)\b', text_lower)
            if num_match:
                entities["appointment_id"] = int(num_match.group(1))
        
        return entities
    
    def _extract_list_entities(self, text: str, text_lower: str) -> Dict[str, Any]:
        """Extract entities for listing appointments"""
        entities = {}
        
        doc = nlp(text)
        
        # Extract date range
        dates = [ent.text for ent in doc.ents if ent.label_ == "DATE"]
        if dates:
            entities["date"] = dates[0]
        
        # Check for "all" or "today" or "tomorrow"
        if "all" in text_lower:
            entities["scope"] = "all"
        elif "today" in text_lower:
            entities["scope"] = "today"
        elif "tomorrow" in text_lower:
            entities["scope"] = "tomorrow"
        
        return entities
