# Aurora Voice Assistant

A local voice assistant capable of providing weather information and managing calendar appointments. All processing happens locally without cloud services.

## Features

- **Voice Interaction**: Speak naturally to interact with the assistant
- **Weather Forecasts**: Get weather information for any location
- **Calendar Management**: Create, list, update, and delete appointments
- **Local Processing**: All speech recognition and synthesis happens locally
- **Conversation History**: Maintains context across the conversation

## Architecture

- **Backend**: FastAPI with Whisper (ASR), Piper (TTS), and WebSocket communication
- **Frontend**: Clean HTML/CSS/JavaScript interface with real-time audio streaming
- **NLU**: spaCy-based intent recognition and entity extraction
- **Services**: Integration with weather and calendar APIs

## Setup and Running

### Prerequisites

- Docker and Docker Compose
- At least 4GB RAM
- Microphone access

### Quick Start

1. **Build and start the containers**:
   ```bash
   docker-compose up --build
   ```

2. **Access the application**:
   - Open your browser to `http://localhost:5173`
   - Click the microphone button and allow microphone access
   - Start speaking!

### Stopping the Application

```bash
docker-compose down
```

## Usage Examples

### Weather Queries
- "What's the weather today?"
- "Tell me the forecast for Zurich"
- "Will it rain tomorrow?"

### Calendar Management
- "Create an appointment for team meeting tomorrow at 2 PM"
- "List my appointments"
- "Show me appointment number 5"
- "Delete appointment 3"
- "Update appointment 2 to next Monday"

## System Requirements

The system uses:
- **ASR**: Faster-Whisper (medium.en model)
- **TTS**: Piper (en_US-amy-low voice)
- **NLU**: spaCy en_core_web_sm
- **Backend**: Python 3.11 with FastAPI
- **Frontend**: Vanilla JavaScript with Web Audio API

## APIs Used

- **Weather API**: `https://api.responsible-nlp.net/weather.php`
- **Calendar API**: `https://api.responsible-nlp.net/calendar.php`

## Development

### Project Structure

```
Aurora-Voice/
├── backend/
│   ├── server.py                 # Main FastAPI server
│   ├── nlu.py                    # Natural Language Understanding
│   ├── dialog_manager.py         # Dialog orchestration
│   ├── conversation_manager.py   # Conversation history
│   ├── weather_service.py        # Weather API integration
│   ├── calendar_service.py       # Calendar API integration
│   ├── requirements.txt          # Python dependencies
│   └── Dockerfile                # Backend container
├── frontend/
│   ├── index.html                # Web interface
│   └── Dockerfile                # Frontend container
├── models/
│   ├── en_US-amy-low.onnx       # Piper TTS model
│   └── en_US-amy-low.onnx.json  # Model config
└── docker-compose.yml            # Docker orchestration
```

## Troubleshooting

### Microphone not working
- Ensure browser has microphone permissions
- Check if another application is using the microphone

### WebSocket connection fails
- Ensure backend is fully started (check logs)
- Wait 30-60 seconds after starting for models to load

### Poor transcription quality
- Speak clearly and at a moderate pace
- Reduce background noise
- Check microphone input level

## License

This project is for educational purposes.
