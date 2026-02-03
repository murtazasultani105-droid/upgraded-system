# API Guardian

API Guardian is a professional rate limiting and abuse detection system designed to protect public and private APIs from excessive usage and malicious behavior.

## Features
- Token-based rate limiting
- Automatic IP blocking
- Abuse detection
- Request logging
- Real-time protection via middleware

## Use Cases
- SaaS platforms
- Public APIs
- Fintech applications
- Backend services
- Microservices architecture

## Tech Stack
- Python
- FastAPI
- SQLite

## Installation

```bash
pip install fastapi uvicorn
uvicorn api_guardian:app --reload
