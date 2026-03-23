# Voice Agent - Romanian TTS Optimization

## Problem Statement
User has a voice agent repository where the Romanian voice sounds too robotic. The goal is to make the Romanian TTS voice sound more human-like and natural.

## What's Been Implemented (Jan 2026)

### Voice Settings Optimization
- **Stability**: Increased from 0.35 to 0.6 for consistent, clear Romanian pronunciation
- **Similarity Boost**: Set to 0.75 for natural voice timbre
- **Style**: Added 0.4 for natural expressiveness without over-acting
- **Speaker Boost**: Enabled for enhanced clarity and presence

### Text Preprocessing for Natural Speech
- Added natural breath pauses after sentences (... markers)
- Improved comma handling for natural rhythm
- Romanian greeting patterns get slight emphasis pauses
- Natural pause before question words (Cu ce, Cum, Ce, Când, Unde)

### Configuration Endpoints
- `/api/voice-settings` - View and understand current TTS settings
- `/api/health` - Shows voice configuration status

## Architecture
- Backend: FastAPI with ElevenLabs TTS integration
- TTS Model: eleven_multilingual_v2
- Voice ID: EXAVITQu4vr4xnSDxMaL (Sarah - good for Romanian)

## Requirements for Production
- ElevenLabs API Key (set `ELEVENLABS_API_KEY` in .env)
- Twilio credentials for phone integration
- OpenAI API key for LLM responses

## Backlog / Future Improvements (P1-P2)
- [ ] Add SSML support for more control over speech
- [ ] Add real-time voice tuning endpoint
- [ ] Alternative voice options for Romanian
- [ ] A/B testing framework for voice settings
