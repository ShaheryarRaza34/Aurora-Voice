# Aurora Voice Assistant

A modular dialog system that integrates Automatic Speech Recognition (ASR), Natural Language Understanding (NLU), Dialog Management, and Text-to-Speech (TTS) synthesis. The system provides voice-based interaction for weather queries and calendar management through a web-based interface.

## Features

- **Weather Queries**: Get weather forecasts for specified locations and dates
- **Calendar Management**: Full CRUD operations (create, read, update, delete appointments)
- **Multi-turn Conversations**: Context preservation across conversation turns
- **Natural Language Interaction**: Support for various phrasings and natural expressions
- **Error Recovery**: Robust handling of speech recognition errors and ambiguous inputs

## Architecture

The system follows a modular architecture:

- **ASR Module**: faster-whisper (tiny.en model) for speech-to-text conversion
- **NLU Module**: spaCy-based intent recognition and entity extraction with regex patterns
- **Dialog Manager**: Context-aware conversation orchestration with multi-turn support
- **TTS Module**: Piper TTS for text-to-speech synthesis
- **Services**: Weather API integration and Calendar API integration
- **Storage**: MySQL database for conversation history and context persistence

## Prerequisites

- Docker and Docker Compose installed
- At least 4GB of available RAM
- Internet connection for initial model downloads

## Quick Start

1. **Clone the repository** (if applicable) or navigate to the project directory

2. **Set up environment variables**:

   ```bash
   cp .env.example .env
   ```

   Edit `.env` file and update the MySQL password and other configuration as needed.

3. **Build and start the services**:

   ```bash
   docker compose up --build
   ```

4. **Access the application**:
   - Frontend: Open your browser and navigate to `http://localhost:5173`
   - Backend API: Available at `http://localhost:8000`
   - API Documentation: `http://localhost:8000/docs`

## Project Structure

```
Aurora-Voice/
├── backend/              # Backend FastAPI application
│   ├── Dockerfile        # Backend container definition
│   ├── requirements.txt  # Python dependencies
│   ├── server.py         # FastAPI server and WebSocket handler
│   ├── nlu.py            # Natural Language Understanding module
│   ├── dialog_manager.py # Dialog management logic
│   ├── calendar_service.py # Calendar API integration
│   ├── weather_service.py  # Weather API integration
│   └── conversation_manager.py # Conversation history management
├── frontend/             # Frontend web application
│   ├── Dockerfile        # Frontend container definition
│   └── index.html        # Web interface
├── models/               # TTS model files
│   ├── en_US-amy-low.onnx
│   └── en_US-amy-low.onnx.json
├── docker-compose.yml    # Docker Compose configuration
├── .env.example          # Environment variables template
└── README.md             # This file
```

## Services

### MySQL Database

- **Container**: `aurora-mysql`
- **Port**: `3307` (host) → `3306` (container)
- **Database**: `aurora_assistant`
- **Persistent Storage**: Data is stored in a Docker volume

### Backend API

- **Container**: `aurora-backend`
- **Port**: `8000`
- **Health Check**: Available at `http://localhost:8000/health`
- **WebSocket**: `ws://localhost:8000/ws`

### Frontend

- **Container**: `aurora-frontend`
- **Port**: `5173`
- **Access**: `http://localhost:5173`

## Configuration

### Environment Variables

Copy `.env.example` to `.env` and configure the following variables:

- `MYSQL_ROOT_PASSWORD`: MySQL root password (change this in production!)
- `MYSQL_DATABASE`: Database name (default: `aurora_assistant`)
- `ASR_MODEL`: Whisper model to use (default: `tiny.en`)
- `ASR_DEVICE`: Device for ASR processing (default: `cpu`)
- `ASR_COMPUTE`: Compute type for ASR (default: `int8`)
- `PIPER_MODEL`: Path to TTS model file
- `BACKEND_PORT`: Backend API port (default: `8000`)
- `FRONTEND_PORT`: Frontend web port (default: `5173`)

### Updating docker-compose.yml

The `docker-compose.yml` file can be updated to use environment variables from `.env` file. Currently, it uses hardcoded values. To use `.env` variables, update the file to reference `${VARIABLE_NAME}` syntax.

## Usage

1. **Start the application**: Click the microphone button in the web interface
2. **Grant microphone permissions**: Allow browser access to your microphone
3. **Speak your request**:
   - Weather: "What's the weather in Frankfurt?"
   - Calendar: "Create an appointment for tomorrow at 3 PM"
   - List: "Show my appointments"
   - Update: "Change the location of my next appointment to Room 205"
   - Delete: "Delete my appointment tomorrow"

## Development

### Rebuilding containers after code changes:

```bash
docker compose up --build
```

### Viewing logs:

```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f backend
docker compose logs -f frontend
docker compose logs -f mysql
```

### Stopping services:

```bash
docker compose down
```

### Stopping and removing volumes (⚠️ deletes database data):

```bash
docker compose down -v
```

## Troubleshooting

### Port conflicts

If ports 3307, 8000, or 5173 are already in use:

- Update the port mappings in `docker-compose.yml`
- Update the corresponding environment variables in `.env`

### Database connection issues

- Ensure MySQL container is healthy: `docker compose ps`
- Check MySQL logs: `docker compose logs mysql`
- Verify environment variables are correctly set

### Microphone not working

- Ensure you've granted browser permissions for microphone access
- Check browser console for errors
- Verify WebSocket connection is established (check browser Network tab)

### Model files missing

- Ensure the `models/` directory contains the TTS model files
- The model files should be present before building the containers

## API Endpoints

- `GET /health` - Health check endpoint
- `WS /ws` - WebSocket endpoint for audio streaming and conversation

## License

This project is part of the Natural Language Systems course.

## Team Members

- Shaheryar RAZA - 3875616
- Arhama - 3865473
