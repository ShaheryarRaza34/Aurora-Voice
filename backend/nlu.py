"""
Natural Language Understanding (NLU) Module

Handles intent recognition and entity extraction for the voice assistant.
"""

import re
from enum import Enum
from typing import Dict, List, Optional, Any
from datetime import datetime
import spacy
from thefuzz import process

# Load spaCy model for NER
try:
    nlp = spacy.load("en_core_web_sm")
except:
    import subprocess
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
                r"\b(going to|gonna|will).*\b(rain|snow|sunny|cloudy)\b",
                r"\b(is it|will it).*\b(rain|snow|sunny|cloudy)\b",
            ],
            Intent.CALENDAR_DELETE: [
                r"\b(delete|remove|cancel).*\b(appointment|meeting|event)\b",
                r"\b(cancel my)\b",
                r"\b(delete|remove).*\b(previously|last|recent).*\b(created|appointment|meeting|event)\b",
            ],
            Intent.CALENDAR_CREATE: [
                r"\b(create|add|schedule|book|make).*\b(appointment|meeting|event)\b",
                r"\b(schedule me|book me|set up)\b",
            ],
            Intent.CALENDAR_UPDATE: [
                r"\b(update|change|modify|edit|reschedule).*\b(appointment|meeting|event)\b",
                r"\b(move|shift|postpone)\b",
                r"\b(change|update|modify|edit)\s+(?:the\s+)?(?:place|location|venue|date|time|title|description)\s+(?:of|for)\s+(?:my|the)?\s*(?:next|upcoming|last|previous|recent).*\b(appointment|meeting|event)\b",
            ],
            Intent.CALENDAR_LIST: [
                r"\b(list|show|get|what|tell me).*\b(appointments|meetings|events|calendar|schedule)\b",
                r"\b(what do i have|what's on my|what is on my)\b",
                r"\b(where|when|what).*\b(next|upcoming).*\b(appointment|meeting|event)\b",
                r"\b(next|upcoming).*\b(appointment|meeting|event)\b",
                r"\b(where|when|what|there).*\b(is|are).*\b(my|the).*\b(appointment|meeting|event)\b",
                r"\b(my|the).*\b(appointment|meeting|event).*\b(on|for)\b",  # "my appointment on 12th January"
            ],
            Intent.CALENDAR_GET: [
                r"\b(get|show|what is).*\b(appointment|meeting|event)\b.*\b(id|number)\b",
                r"\b(details of|information about|tell me about).*\b(appointment|meeting|event)\b",
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
        
        # If intent is unknown, check conversation history for context
        if intent == Intent.UNKNOWN and conversation_history:
            # Look at recent conversation to infer intent
            recent_turns = conversation_history[-3:] if len(conversation_history) > 3 else conversation_history
            for turn in reversed(recent_turns):
                if turn.get("intent") and turn["intent"] != Intent.UNKNOWN.value:
                    # If assistant just asked a question, likely a follow-up
                    if turn.get("role") == "assistant" and "?" in turn.get("text", ""):
                        # Use the previous intent as context
                        previous_intent = turn.get("intent")
                        if previous_intent:
                            # Map string intent back to Intent enum
                            for intent_enum in Intent:
                                if intent_enum.value == previous_intent:
                                    intent = intent_enum
                                    break
                        break
        
        # Extract entities based on intent
        entities = {}
        if intent in [Intent.WEATHER_QUERY]:
            entities = self._extract_weather_entities(text, text_lower, conversation_history)
        elif intent in [Intent.CALENDAR_CREATE, Intent.CALENDAR_UPDATE]:
            entities = self._extract_calendar_entities(text, text_lower)
        elif intent in [Intent.CALENDAR_GET, Intent.CALENDAR_DELETE]:
            entities = self._extract_calendar_id_entities(text, text_lower)
        elif intent == Intent.CALENDAR_LIST:
            entities = self._extract_list_entities(text, text_lower)
        elif intent == Intent.UNKNOWN:
            # Try to extract any entities even if intent is unknown (might be a follow-up)
            # Check conversation history to see if there's a pending weather query
            is_weather_followup = False
            if conversation_history:
                for turn in reversed(conversation_history[-3:]):
                    if turn.get("intent") == "weather_query" and turn.get("role") == "assistant":
                        # Check if assistant asked for location
                        if "location" in turn.get("text", "").lower() or "where" in turn.get("text", "").lower():
                            is_weather_followup = True
                            break
            
            if is_weather_followup:
                # Likely a location response, try to extract as location
                entities = self._extract_weather_entities(text, text_lower, conversation_history)
                # If no location found, try spaCy NER on the text directly
                if not entities.get("location"):
                    doc = nlp(text)
                    locations = [ent.text for ent in doc.ents if ent.label_ in ["GPE", "LOC"]]
                    if locations:
                        entities["location"] = locations[0]
            else:
                # Try calendar first (for appointment descriptions)
                entities = self._extract_calendar_entities(text, text_lower)
                if not entities:
                    entities = self._extract_weather_entities(text, text_lower, conversation_history)
        
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
    
    def _extract_weather_entities(self, text: str, text_lower: str, conversation_history: List[Dict] = None) -> Dict[str, Any]:
        """Extract weather-related entities"""
        entities = {}
        
        # Check for location references like "there" first (before NER)
        if any(word in text_lower for word in ["there", "that place", "that city", "that location"]):
            # Mark that we need to resolve "there" - this will be handled by dialog_manager
            entities["_needs_location_resolution"] = True
        
        # Extract location using spaCy NER
        doc = nlp(text)
        locations = [ent.text for ent in doc.ents if ent.label_ in ["GPE", "LOC"]]
        if locations:
            entities["location"] = locations[0]
        # If spaCy NER fails, try fuzzy matching against known cities
        elif not entities.get("location"):
            known_cities = ["Frankfurt", "Berlin", "Munich", "Zurich", "Paris", "London", "New York", "Tokyo", "Moscow", "Rome", "Madrid", "Amsterdam", "Vienna", "Stockholm", "Copenhagen", "Dublin", "Brussels", "Warsaw", "Prague", "Budapest", "Athens", "Lisbon", "Oslo", "Helsinki"]
            # Try fuzzy matching on the full text and individual words
            fuzzy_result = process.extractOne(text, known_cities, score_cutoff=70)
            if fuzzy_result:
                entities["location"] = fuzzy_result[0]
            else:
                # Try fuzzy matching on individual capitalized words
                words = text.split()
                for word in words:
                    clean_word = word.strip().rstrip('.,!?;:')
                    if clean_word and clean_word[0].isupper() and len(clean_word) > 2:
                        fuzzy_result = process.extractOne(clean_word, known_cities, score_cutoff=70)
                        if fuzzy_result:
                            entities["location"] = fuzzy_result[0]
                            break
        # If no location found and text is short (likely a single-word response), try to extract as location
        if not entities.get("location") and len(text.split()) <= 2:
            words = text.split()
            # Single word case
            if len(words) == 1:
                clean_text = words[0].strip().rstrip('.,!?;:')
                if clean_text and clean_text[0].isupper() and len(clean_text) > 2:
                    # Check if it's not a common word
                    common_words = {"Friday", "Saturday", "Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Today", "Tomorrow", "Yes", "No", "Okay", "OK", "What", "Tell", "Is", "Will", "Can", "Show", "How"}
                    if clean_text not in common_words:
                        entities["location"] = clean_text
            # Two words case - handle speech recognition errors (e.g., "Frank food" instead of "Frankfurt")
            elif len(words) == 2:
                first_word = words[0].strip().rstrip('.,!?;:')
                if first_word and first_word[0].isupper() and len(first_word) > 2:
                    # Check if first word looks like a location name (common city name patterns)
                    # This handles cases like "Frank food" -> "Frank" (partial match for "Frankfurt")
                    common_words = {"Friday", "Saturday", "Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Today", "Tomorrow", "What", "Tell", "Is", "Will", "Can", "Show", "How", "The", "This", "That"}
                    if first_word not in common_words:
                        # Try to match against known location patterns
                        # If it starts with common location prefixes, treat as location
                        location_prefixes = ["Frank", "New", "San", "Los", "Las", "Saint", "St", "Mount", "Fort", "Port"]
                        if any(first_word.startswith(prefix) for prefix in location_prefixes) or len(first_word) >= 4:
                            entities["location"] = first_word
        elif conversation_history:
            # Check for location references like "there", "that place", etc.
            if any(word in text_lower for word in ["there", "that place", "that city", "that location"]):
                # Look for location in recent conversation history
                for turn in reversed(conversation_history[-5:]):  # Check last 5 turns
                    if turn.get("role") == "assistant":
                        # Extract location from assistant's previous response
                        assistant_text = turn.get("text", "")
                        # Better pattern: matches "in Frankfurt", "for Frankfurt", "at Frankfurt"
                        location_match = re.search(r'\b(?:in|for|at)\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)?)\b', assistant_text)
                        if location_match:
                            entities["location"] = location_match.group(1)
                            break
                    elif turn.get("role") == "user":
                        # Extract location from user's previous query
                        user_text = turn.get("text", "")
                        user_doc = nlp(user_text)
                        user_locations = [ent.text for ent in user_doc.ents if ent.label_ in ["GPE", "LOC"]]
                        if user_locations:
                            entities["location"] = user_locations[0]
                            break
        
        # Extract date/time
        dates = [ent.text for ent in doc.ents if ent.label_ == "DATE"]
        if dates:
            entities["date"] = dates[0]
        else:
            # Also check for day names directly (spaCy might miss them)
            day_names = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
            for day in day_names:
                if day in text_lower:
                    entities["date"] = day
                    break
            
            # Check for relative dates
            if "today" in text_lower:
                entities["date"] = "today"
            elif "tomorrow" in text_lower:
                entities["date"] = "tomorrow"
        
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
        
        # First, try to extract appointment_id if this is an update context
        # Look for patterns like "ID number 6", "Appointment ID is 6", "ID6", "number 6", "6"
        id_patterns = [
            r'\b(?:appointment\s+)?id\s*(?:number\s+|is\s+)?(\d+)\b',  # "ID 6", "ID6", "appointment ID 6"
            r'\b(?:id|number)\s+(?:is\s+)?(\d+)\b',  # "ID is 6", "number 6"
            r'\bappointment\s+id\s+is\s+(\d+)\b',  # "appointment ID is 6"
            r'\bid\s*(\d+)\b',  # "ID6" (no space)
        ]
        for pattern in id_patterns:
            id_match = re.search(pattern, text_lower)
            if id_match:
                entities["appointment_id"] = int(id_match.group(1))
                break
        
        # If no ID found with patterns, try standalone number (only if context suggests ID is expected)
        if not entities.get("appointment_id") and len(text.strip()) < 30:
            # Short text might be just an ID response
            num_match = re.search(r'^\s*(\d+)\s*\.?\s*$', text.strip())
            if num_match:
                # Check if it's a reasonable ID (1-1000, not a time)
                num = int(num_match.group(1))
                if 1 <= num <= 1000:
                    entities["appointment_id"] = num
        
        doc = nlp(text)
        
        # Extract location/place for calendar updates (e.g., "Change the place to...")
        # IMPORTANT: Only extract location if it's a new value, NOT from phrases like "change place for my appointment"
        # We should NOT extract location from "Change the place for my appointment" - that's just identifying the appointment
        # We SHOULD extract from "Change the place to Room 205" or "location is Room 205"
        
        # Pattern 1: "change location to X" or "location is X" (has new value)
        # Pattern 1.5: "change location of [appointment] to X" - extract X as new location
        # Pattern 2: "at X" or "in X" (when it's clearly a location name)
        location_patterns = [
            r'(?:change|update|set|move)\s+(?:the\s+)?(?:place|location|venue)\s+of\s+[^\.]+?\s+to\s+([^\.]+?)(?:\s*\.|$)',  # "change location of my next appointment to Room 205"
            r'(?:change|update|set|move)\s+(?:the\s+)?(?:place|location|venue)\s+to\s+([^\.]+?)(?:\s*\.|$)',  # "change location to Room 205"
            r'(?:place|location|venue)\s+(?:is|will be|should be)\s+([^\.]+?)(?:\s*\.|$)',  # "location is Room 205"
        ]
        for pattern in location_patterns:
            match = re.search(pattern, text_lower)
            if match:
                location = match.group(1).strip()
                # Clean up common words at the end
                location = re.sub(r'\s+(?:for|my|appointment|tomorrow|today|the|a|an)\s*$', '', location).strip()
                # Don't extract if it contains words like "my appointment" or "for" - that's not a location value
                if location and len(location) > 1 and not re.search(r'\b(my|appointment|tomorrow|today|for|the|a|an)\b', location.lower()):
                    entities["location"] = location
                    break
        
        # Pattern 2: "at X" or "in X" when it's clearly a location name (short, capitalized, not common words)
        if not entities.get("location"):
            at_in_match = re.search(r'\b(?:at|in)\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)?)(?:\s*\.|$)', text)
            if at_in_match:
                location = at_in_match.group(1).strip()
                # Only extract if it looks like a real location (not "my appointment", "the place", etc.)
                if location and len(location) < 30 and not re.search(r'\b(my|appointment|tomorrow|today|for|the|place|location)\b', location.lower()):
                    entities["location"] = location
        
        # Also try spaCy NER for location if not found yet
        if not entities.get("location"):
            for ent in doc.ents:
                if ent.label_ in ["GPE", "LOC", "FAC"]:  # GPE=Geopolitical, LOC=Location, FAC=Facility
                    entities["location"] = ent.text
                    break
        
        # Extract dates and times
        # BUT: If we found an appointment_id, don't extract "6" or similar as a date (it's an ID)
        for ent in doc.ents:
            if ent.label_ == "DATE":
                # Don't extract date if it's just a number and we already have appointment_id
                # This prevents "6" from being extracted as date when it's an appointment ID
                if entities.get("appointment_id") and ent.text.strip().isdigit():
                    continue
                entities["date"] = ent.text
            elif ent.label_ == "TIME":
                entities["time"] = ent.text
        
        # If spaCy only extracted a year (like "2026" from "March 15, 2026"), try regex to get full date
        if entities.get("date") and len(entities["date"].strip()) <= 4 and entities["date"].isdigit():
            # Try to extract full date patterns: "March 15, 2026", "15 March 2026", "March 1st, 2026", etc.
            date_patterns = [
                r'\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2})(?:st|nd|rd|th)?\s*,?\s*(\d{4})\b',
                r'\b(\d{1,2})(?:st|nd|rd|th)?\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})\b',
                r'\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2})(?:st|nd|rd|th)?\s+(\d{4})\b',
            ]
            for pattern in date_patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    # Reconstruct the full date string from the match
                    full_date = match.group(0)
                    entities["date"] = full_date
                    break
        
        # Extract start_time and end_time separately if both are mentioned
        # Improved patterns to handle various formats: "12 p.m", "12pm", "12 PM", "15", "12, 0, 0"
        # IMPORTANT: Only extract times if explicitly mentioned with time keywords, NOT standalone numbers/words
        start_time_patterns = [
            r'(?:start|starting|from|at)\s+(?:is\s+|be\s+|as\s+)?(\d{1,2}(?::\d{2})?\s*(?:am|pm|a\.m|p\.m|AM|PM)?)',
            r'(?:starting\s+time|start\s+time|starts?\s+at|begin\s+at)\s+(?:would\s+be|will\s+be|is|at|as)?\s*(\d{1,2}(?::\d{2})?\s*(?:am|pm|a\.m|p\.m|AM|PM)?)',
        ]
        end_time_patterns = [
            r'(?:end|ending|until|to|in\s+time|handing|handing\s+time)\s+(?:is\s+|be\s+|as\s+)?(\d{1,2}(?::\d{2})?\s*(?:am|pm|a\.m|p\.m|AM|PM)?)',
            r'(?:ending\s+time|end\s+time|ends?\s+at|n-time|in\s+time)\s+(?:would\s+be|will\s+be|is|at|as)?\s*(\d{1,2}(?::\d{2})?\s*(?:am|pm|a\.m|p\.m|AM|PM)?)',
        ]
        
        # List of ordinal words that should NEVER be extracted as times
        # NOTE: "twelfth" removed because users often say "twelfth" to mean 12:00
        ordinal_words = {"first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth", "ninth", "tenth",
                        "eleventh", "thirteenth", "fourteenth", "fifteenth", "sixteenth", "seventeenth",
                        "eighteenth", "nineteenth", "twentieth", "twenty-first", "twenty-second", "twenty-third",
                        "twenty-fourth", "twenty-fifth", "twenty-sixth", "twenty-seventh", "twenty-eighth",
                        "twenty-ninth", "thirtieth", "thirty-first"}
        
        # FIRST: Try "X till Y" or "X to Y" pattern (e.g., "12 PM till 5 PM")
        # This should run BEFORE individual time extraction to catch both times at once
        till_to_match = re.search(r'(\d{1,2}(?::\d{2})?\s*(?:p\s*\.?\s*m\s*\.?|a\s*\.?\s*m\s*\.?|pm|am|PM|AM)?)\s+(?:till|until|to)\s+(\d{1,2}(?::\d{2})?\s*(?:p\s*\.?\s*m\s*\.?|a\s*\.?\s*m\s*\.?|pm|am|PM|AM)?)', text_lower)
        if till_to_match:
            start = till_to_match.group(1).strip()
            end = till_to_match.group(2).strip()
            # Clean up
            start = re.sub(r'\s*\.\s*', '.', start).replace(' ', '').replace('.', '')
            end = re.sub(r'\s*\.\s*', '.', end).replace(' ', '').replace('.', '')
            entities["start_time"] = start
            entities["end_time"] = end
        
        # Also try "from X to Y" pattern
        from_to_match = re.search(r'from\s+(\d{1,2}(?::\d{2})?\s*(?:p\s*\.?\s*m\s*\.?|a\s*\.?\s*m\s*\.?|pm|am|PM|AM)?)\s+to\s+(\d{1,2}(?::\d{2})?\s*(?:p\s*\.?\s*m\s*\.?|a\s*\.?\s*m\s*\.?|pm|am|PM|AM)?)', text_lower)
        if from_to_match and not entities.get("start_time"):
            start = from_to_match.group(1).strip()
            end = from_to_match.group(2).strip()
            # Clean up
            start = re.sub(r'\s*\.\s*', '.', start).replace(' ', '').replace('.', '')
            end = re.sub(r'\s*\.\s*', '.', end).replace(' ', '').replace('.', '')
            entities["start_time"] = start
            entities["end_time"] = end
        
        # Try to extract start_time (only if explicitly mentioned with time keywords and not already extracted)
        if not entities.get("start_time"):
            for pattern in start_time_patterns:
                match = re.search(pattern, text_lower)
                if match:
                    time_str = match.group(1).strip().lower()
                    # Skip if it's an ordinal word (like "first", "second") - these are dates, not times
                    if time_str in ordinal_words:
                        continue
                    # Clean up: "p.m." or "p. m." -> "pm"
                    time_str = time_str.replace('.', '').replace(' ', '')
                    entities["start_time"] = time_str
                    break
        
        # Try to extract end_time (only if explicitly mentioned with time keywords and not already extracted)
        if not entities.get("end_time"):
            for pattern in end_time_patterns:
                match = re.search(pattern, text_lower)
                if match:
                    time_str = match.group(1).strip().lower()
                    # Skip if it's an ordinal word (like "first", "second") - these are dates, not times
                    if time_str in ordinal_words:
                        continue
                    # Clean up: "p.m." or "p. m." -> "pm"
                    time_str = time_str.replace('.', '').replace(' ', '')
                    entities["end_time"] = time_str
                    break
        
        # If no date found via NER, try regex patterns for common date formats
        if "date" not in entities:
            date_patterns = [
                # Worded ordinals: "first January", "second March", "third December" (NEW - must come first)
                r'\b((?:first|second|third|fourth|fifth|twenty|thirty)\s+(?:january|february|march|april|may|june|july|august|september|october|november|december))\b',
                # Ordinal dates: "1st January", "22nd March", "3rd December" (with optional year)
                r'\b(\d{1,2}(?:st|nd|rd|th)?\s+(?:january|february|march|april|may|june|july|august|september|october|november|december)(?:\s+\d{4})?)\b',
                # Ordinal dates with word form: "first January", "twenty-second March" (extended)
                r'\b((?:first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|eleventh|twelfth|thirteenth|fourteenth|fifteenth|sixteenth|seventeenth|eighteenth|nineteenth|twentieth|twenty-first|twenty-second|twenty-third|twenty-fourth|twenty-fifth|twenty-sixth|twenty-seventh|twenty-eighth|twenty-ninth|thirtieth|thirty-first)\s+(?:january|february|march|april|may|june|july|august|september|october|november|december))',
                # Month first: "January 1st", "March 22nd" (with optional year)
                r'\b((?:january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2}(?:st|nd|rd|th)?(?:\s+\d{4})?)\b',
                # Numeric dates: "1/1/2024", "12-25-2024"
                r'\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b',
                # Short month names with ordinal: "1st Jan", "22nd Mar"
                r'\b(\d{1,2}(?:st|nd|rd|th)\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*)\b',
            ]
            for pattern in date_patterns:
                match = re.search(pattern, text_lower)
                if match:
                    entities["date"] = match.group(1)
                    break
            
            # If still no date found, check for standalone ordinal words in calendar context
            # This handles cases like "appointment for first" where "first" means "first of the month"
            if "date" not in entities:
                ordinal_standalone = re.search(r'\b(for|on|at)\s+(first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|eleventh|twelfth|thirteenth|fourteenth|fifteenth|sixteenth|seventeenth|eighteenth|nineteenth|twentieth|twenty-first|twenty-second|twenty-third|twenty-fourth|twenty-fifth|twenty-sixth|twenty-seventh|twenty-eighth|twenty-ninth|thirtieth|thirty-first)\b', text_lower)
                if ordinal_standalone:
                    ordinal_word = ordinal_standalone.group(2)
                    # Convert to numeric format (e.g., "first" -> "1st")
                    ordinal_map = {
                        "first": "1st", "second": "2nd", "third": "3rd", "fourth": "4th", "fifth": "5th",
                        "sixth": "6th", "seventh": "7th", "eighth": "8th", "ninth": "9th", "tenth": "10th",
                        "eleventh": "11th", "twelfth": "12th", "thirteenth": "13th", "fourteenth": "14th",
                        "fifteenth": "15th", "sixteenth": "16th", "seventeenth": "17th", "eighteenth": "18th",
                        "nineteenth": "19th", "twentieth": "20th", "twenty-first": "21st", "twenty-second": "22nd",
                        "twenty-third": "23rd", "twenty-fourth": "24th", "twenty-fifth": "25th",
                        "twenty-sixth": "26th", "twenty-seventh": "27th", "twenty-eighth": "28th",
                        "twenty-ninth": "29th", "thirtieth": "30th", "thirty-first": "31st"
                    }
                    if ordinal_word in ordinal_map:
                        entities["date"] = ordinal_map[ordinal_word]
        
        # Extract description/title (everything after certain keywords)
        # Improved pattern to handle filler words like "is", "would be", "be"
        # Capture multiple words until we hit time/date keywords or end of sentence
        # Priority: "to the new description which is X" > "new description is X" > "description is X" > "description X"
        
        # Pattern 0: "to the new description which is X" or "to the new title which is X" (for update context)
        to_new_desc_match = re.search(r'to\s+the\s+new\s+(?:description|title)\s+which\s+is\s+([^\.]+?)(?:\s*\.|$)', text_lower)
        if to_new_desc_match:
            desc = to_new_desc_match.group(1).strip()
            # Clean up common filler words at the end
            desc = re.sub(r'\s+(?:and|the|a|an|is|are|was|were)\s*$', '', desc).strip()
            if desc and not re.search(r'\bid\s*\d+', desc.lower()):  # Don't extract if it contains ID pattern
                entities["description"] = desc
        
        # Pattern 0.5: "change [field] of [appointment] to X" - extract X as the new value
        # This handles "change description of my next appointment to Meeting with Professor X"
        if not entities.get("description"):
            change_to_match = re.search(r'change\s+(?:the\s+)?(?:description|title)\s+of\s+[^\.]+?\s+to\s+([^\.]+?)(?:\s*\.|$)', text_lower)
            if change_to_match:
                desc = change_to_match.group(1).strip()
                desc = re.sub(r'\s+(?:and|the|a|an|is|are|was|were)\s*$', '', desc).strip()
                if desc and not re.search(r'\b(?:my|the|next|upcoming|last|previous|tomorrow\'?s?|today\'?s?)\s+(?:appointment|meeting|event)', desc.lower()):
                    entities["description"] = desc
                desc = change_to_match.group(1).strip()
                # Clean up common filler words
                desc = re.sub(r'\s+(?:and|the|a|an|is|are|was|were)\s*$', '', desc).strip()
                # Don't extract if it's an appointment identifier
                if desc and not re.search(r'\b(?:my|the|next|upcoming|last|previous|tomorrow\'?s?|today\'?s?)\s+(?:appointment|meeting|event)', desc.lower()):
                    entities["description"] = desc
        
        # Pattern 1: "new description is X" or "the new description is X"
        if not entities.get("description"):
            new_desc_match = re.search(r'(?:the\s+)?new\s+description\s+is\s+([^\.]+?)(?:\s*\.|$)', text_lower)
            if new_desc_match:
                desc = new_desc_match.group(1).strip()
                # Clean up common filler words at the end
                desc = re.sub(r'\s+(?:and|the|a|an|is|are|was|were)\s*$', '', desc).strip()
                if desc and not re.search(r'\bid\s*\d+', desc.lower()):  # Don't extract if it contains ID pattern
                    entities["description"] = desc
        
        # Pattern 2: Regular "description is X" or "description X" (only if not already found)
        # BUT: Skip if this is in update context with "change the description of X" - we don't want to extract X as description
        if not entities.get("description"):
            # Check if this looks like "change the description of X" where X is NOT the new description
            change_desc_pattern = r'change\s+(?:the\s+)?(?:description|title)\s+of\s+'
            if re.search(change_desc_pattern, text_lower):
                pass
            else:
                title_match = re.search(r'(?:title|call it|named|description)\s+(?:is\s+|would be\s+|be\s+)?(?:of\s+)?([^\.]+?)(?:\s+(?:and|ending|end|start|starting|time|from|to|on|at|for|when|that|has|id)\s+|\s*\.|$)', text_lower)
                if title_match:
                    desc = title_match.group(1).strip()
                    # Clean up common filler words at the start (like "of", "that has", etc.) and end
                    desc = re.sub(r'^(?:of|the|a|an|that\s+has?|has?)\s+', '', desc).strip()
                    desc = re.sub(r'\s+(?:and|the|a|an|is|are|was|were|that|has|id)\s*$', '', desc).strip()
                    # Don't extract if it contains appointment date references like "tomorrow's appointment", "my appointment"
                    if desc and not re.search(r'\b(?:tomorrow\'?s?|today\'?s?|my|the)\s+(?:appointment|meeting|event)', desc.lower()):
                        # Don't extract if it looks like an ID pattern (e.g., "id6", "id 6", "employment id 6")
                        if not re.search(r'\b(?:id|employment|appointment)\s*\d+', desc.lower()) and not desc.lower().strip().endswith('id'):
                            entities["description"] = desc
        
        # Pattern 1.5: "title XYZ" or "with title XYZ" (without filler words) - only if no description yet
        if not entities.get("description") and re.search(r'(?:with\s+)?title\s+([A-Za-z0-9]+)(?:\s+for|\s+on|\s+at|$)', text_lower):
            title_match = re.search(r'(?:with\s+)?title\s+([A-Za-z0-9]+)(?:\s+for|\s+on|\s+at|$)', text_lower)
            if title_match:
                desc = title_match.group(1).strip()
                if desc:
                    entities["description"] = desc
        
        # Pattern 2: "for XYZ" or "about XYZ" before date - capture multiple words
        # Only run if we haven't found a description yet
        # BUT: Skip if this is in update context with "change [field] for/of my [next/tomorrow] appointment" - we don't want to extract appointment identifier as description
        if not entities.get("description"):
            # Check if this looks like "change [field] for/of my [next/tomorrow] appointment" where the "for/of" part is identifying the appointment
            change_field_pattern = r'change\s+(?:the\s+)?(?:date|time|place|location|venue|title|description)\s+(?:for|of)\s+'
            if re.search(change_field_pattern, text_lower):
                pass
            else:
                desc_patterns = [
                    r"(?:for|about|regarding)\s+([^\.]+?)(?:\s+(?:for|on|at|and|ending|end|start|starting|time|from|to|when)\s+|\s*\.|$)",
                    r"(?:appointment|meeting|event)\s+(?:for|about|with)\s+([^\.]+?)(?:\s+(?:for|on|at|and|ending|end|start|starting|time|from|to|when)\s+|\s*\.|$)",
                ]
                for pattern in desc_patterns:
                    match = re.search(pattern, text_lower)
                    if match:
                        desc = match.group(1).strip()
                        # Clean up common filler words at the end
                        desc = re.sub(r'\s+(?:and|the|a|an|is|are|was|were)\s*$', '', desc).strip()
                        # Don't accept appointment identifiers like "my next appointment", "my appointment tomorrow", "the appointment"
                        if desc and desc.lower() not in ['appointment', 'meeting', 'event'] and not re.search(r'\d{4}', desc) and not re.search(r'\b(?:id|number)\s*\d+', desc.lower()):
                            # Don't extract if it contains appointment references like "my next appointment", "my appointment tomorrow"
                            if not re.search(r'\b(?:my|the|next|upcoming|last|previous|tomorrow\'?s?|today\'?s?)\s+(?:appointment|meeting|event)', desc.lower()):
                                entities["description"] = desc
                                break
        
        # If no description found, try to extract text before date keywords
        if "description" not in entities:
            # Look for text between action words and date - extract multiple words before "for/on/at"
            before_date = re.search(r'(?:add|create|schedule|book|make)\s+(?:an?\s+)?(?:appointment|meeting|event)?\s*(?:with\s+title\s+)?([^\.]+?)\s+(?:for|on|at|and|ending|end|start|starting|time)\s+', text_lower)
            if before_date:
                desc = before_date.group(1).strip()
                # Clean up common words and don't accept dates
                desc = re.sub(r'\b(appointment|meeting|event|with|title|the|a|an|is|are|was|were)\b', '', desc).strip()
                # Remove leading/trailing punctuation
                desc = re.sub(r'^[.,!?\s]+|[.,!?\s]+$', '', desc).strip()
                if desc and len(desc) > 0 and not re.search(r'\d{4}', desc):
                    entities["description"] = desc
        
        # If still no description and this might be a short follow-up response (like "X, Y, Z")
        if "description" not in entities:
            # Check if this looks like a description (short text, letters/commas, no action words)
            action_words = ['add', 'create', 'schedule', 'book', 'make', 'appointment', 'meeting', 'event', 'for', 'on', 'at', 'when', 'where']
            has_action_words = any(word in text_lower for word in action_words)
            
            if not has_action_words and len(text.strip()) < 50:
                # Might be just a description like "X, Y, Z" or "XYZ"
                clean_text = text.strip().rstrip('.,!?')
                # Remove common filler words but keep the main content
                clean_text = re.sub(r'\b(its|it|the|a|an|is|are|was|were|this|that)\b', '', clean_text.lower()).strip()
                # Clean up commas and normalize spaces
                clean_text = re.sub(r'\s*,\s*', ' ', clean_text).strip()
                # Remove leading/trailing punctuation
                clean_text = re.sub(r'^[.,!?\s]+|[.,!?\s]+$', '', clean_text).strip()
                
                if clean_text and len(clean_text) > 0:
                    # Check if it's a numeric time (e.g., "17", "17000" for 17:00)
                    numeric_time_match = re.match(r'^(\d{1,2})(\d{2})?(\d{2})?$', clean_text)
                    if numeric_time_match:
                        # Handle numeric times like "17" (17:00) or "17000" (17:00:00)
                        hour = int(numeric_time_match.group(1))
                        if hour <= 23:
                            # If we're waiting for end_time and start_time is already set, treat as end_time
                            # Otherwise, treat as start_time if we're in a calendar_create context
                            if hour >= 0 and hour <= 23:
                                time_str = f"{hour:02d}:00"
                                # Check if we need start_time or end_time based on context
                                # For now, if end_time is missing, use as end_time, else start_time
                                if not entities.get("end_time") and entities.get("start_time"):
                                    entities["end_time"] = time_str
                                elif not entities.get("start_time"):
                                    entities["start_time"] = time_str
                    elif not re.search(r'\d{2,}', clean_text):
                        # Don't accept if it's just common words
                        if clean_text.lower() not in ['yes', 'no', 'ok', 'okay', 'sure', 'thanks', 'thank you']:
                            entities["description"] = clean_text
        
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
        
        # Also try regex patterns for date extraction (same as in _extract_calendar_entities)
        # This helps catch dates like "12th January" that spaCy might miss
        if not entities.get("date"):
            # Try regex patterns for common date formats
            date_patterns = [
                # Ordinal dates: "1st January", "22nd March", "3rd December" (with optional year)
                r'\b(\d{1,2}(?:st|nd|rd|th)?\s+(?:january|february|march|april|may|june|july|august|september|october|november|december)(?:\s+\d{4})?)\b',
                # Month first: "January 1st", "March 22nd" (with optional year)
                r'\b((?:january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2}(?:st|nd|rd|th)?(?:\s+\d{4})?)\b',
            ]
            for pattern in date_patterns:
                match = re.search(pattern, text_lower)
                if match:
                    entities["date"] = match.group(1)
                    break
        
        # Check for "all" or "today" or "tomorrow" or "next" or "upcoming"
        if "all" in text_lower:
            entities["scope"] = "all"
        elif "today" in text_lower:
            entities["scope"] = "today"
        elif "tomorrow" in text_lower:
            entities["scope"] = "tomorrow"
        elif "next" in text_lower or "upcoming" in text_lower:
            entities["scope"] = "next"
        
        return entities
