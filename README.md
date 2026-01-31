# Vienna - AI Agent Orchestration System

An intelligent, production-ready system that orchestrates AI agents to execute tasks across Gmail and GitHub using natural language commands.

## Overview

Vienna is an AI-powered agent orchestration platform that allows you to control multiple services through simple, natural language commands. It intelligently parses your requests, determines the best execution strategy, and seamlessly coordinates actions across Gmail and GitHub.

### What You Can Do

```
You: Show me my latest 10 emails

[Beautiful formatted table with your emails]

You: List my GitHub repositories sorted by stars

[Formatted table with your repositories]

You: Email john@example.com the names of my top 5 repositories

[Fetches repos → Composes email → Sends with repo list]
```

### Key Highlights

- 🧠 **Intelligent Intent Parsing**: Powered by Claude Sonnet 4 for sophisticated command understanding
- ⚡ **Smart Execution**: Automatically determines whether to run tasks in parallel or sequence
- 🔗 **Data Flow**: Seamlessly passes data between tasks for complex multi-step operations
- 🔐 **Enterprise Security**: OAuth 2.0 with encrypted token storage and automatic refresh
- 🎨 **Beautiful Interface**: Rich, color-coded terminal UI with formatted tables
- 🐳 **Cloud Native**: Docker-ready with comprehensive deployment options
- 💾 **Persistent State**: MongoDB integration for conversation history and results

---

## Features

### Natural Language Processing

Vienna uses Claude Sonnet 4 to understand complex natural language commands and automatically:
- Parses intent from freeform text
- Identifies which agents to use
- Determines optimal execution strategy (parallel vs sequential)
- Handles follow-up context from conversation history

### Multi-Agent Support

#### Gmail Agent
- **Read Emails**: Fetch emails with filters (date, sender, unread status)
- **Send Emails**: Compose and send emails with CC support
- **Search**: Advanced Gmail search with full query syntax support
- **Smart Filtering**: Date-based filters (today, this week) and custom queries

#### GitHub Agent
- **List Repositories**: View repos with sorting (stars, updates, created date)
- **Repository Details**: Get comprehensive repo information including:
  - Stars, forks, and watchers
  - Language breakdown
  - Top contributors
  - README preview
  - Recent activity

### Execution Modes

#### Parallel Execution
Run independent tasks simultaneously for maximum efficiency:
```
You: Show my emails and list my repos

⚡ Both tasks execute at the same time
✓ Results combined and displayed
```

#### Sequential Execution
Chain tasks with intelligent data flow:
```
You: Email the names of my top 5 repos to john@example.com

1. Fetch top 5 repos from GitHub
2. Extract repo names
3. Compose email with repo list
4. Send to recipient
```

### Security & Authentication

- **OAuth 2.0**: Industry-standard authentication for Gmail and GitHub
- **Lazy Authentication**: Only authenticates when needed, not on startup
- **Token Encryption**: Fernet encryption with additional salt layer
- **Secure Storage**: All tokens encrypted before MongoDB storage
- **Auto Refresh**: Gmail tokens automatically refreshed when expired
- **No Plaintext**: Tokens never stored or logged in readable form

### Data Management

- **MongoDB Atlas**: Cloud-based persistent storage
- **Session Management**: Track user sessions and conversation history
- **Result Caching**: Store task results for reference
- **User Preferences**: Maintain per-user settings and defaults
- **Audit Trail**: Complete execution history with timestamps

### User Experience

- **Rich Terminal UI**: Color-coded, formatted output
- **Real-time Progress**: Live status updates during execution
- **Smart Error Messages**: Helpful hints for resolution
- **Conversation History**: View and reference past commands
- **Status Monitoring**: Check agent connection status
- **Contextual Help**: Built-in examples and documentation

---

## Quick Start

### Prerequisites

- **Python 3.11+** or **Docker**
- **MongoDB Atlas** account (free tier available)
- **Anthropic API** key
- **Gmail OAuth** credentials from Google Cloud Console
- **GitHub OAuth** application

### Installation

#### Option 1: Docker (Recommended)

```bash
# Clone and configure
git clone https://github.com/theMillenniumFalcon/vienna
cd vienna
cp .env.example .env
# Edit .env with your credentials

# Run with Docker Compose
docker-compose run --rm vienna
```

#### Option 2: Local Python

```bash
# Clone and setup
git clone https://github.com/theMillenniumFalcon/vienna
cd vienna

# Install dependencies
pip install uv
uv sync

# Configure
cp .env.example .env
# Edit .env with your credentials

# Run
python main.py
```

### Initial Setup

1. **MongoDB Atlas**
   - Create free cluster at [mongodb.com/cloud/atlas](https://www.mongodb.com/cloud/atlas)
   - Create database user with password
   - Whitelist IP address (0.0.0.0/0 for development)
   - Copy connection string to `.env`

2. **Gmail OAuth**
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Create OAuth 2.0 credentials (Desktop app type)
   - Add redirect URI: `http://localhost:8080/oauth2callback`
   - Copy client ID and secret to `.env`

3. **GitHub OAuth**
   - Go to GitHub Settings → Developer settings → OAuth Apps
   - Create new OAuth App
   - Authorization callback URL: `http://localhost:8080/github/callback`
   - Copy client ID and secret to `.env`

4. **Generate Encryption Key**
   ```bash
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```
   Add output to `.env` as `ENCRYPTION_KEY`

---

## Usage

### Starting Vienna

```bash
# Using uv (recommended)
uv run main.py

# Local installation (plain Python)
python main.py

# Docker
docker-compose run --rm vienna
```

### Command Examples

#### Gmail Operations

```bash
# Read emails
Show me my latest 10 emails
Show emails from today
Find unread emails

# Search emails
Find emails from GitHub
Search for emails about "meeting"
Show emails from john@example.com

# Send emails
Send an email to john@example.com about tomorrow's meeting
Email the team about project updates
```

#### GitHub Operations

```bash
# List repositories
Show my GitHub repositories
List my repos sorted by stars
Show my 5 most popular projects

# Repository details
Get details about my project called awesome-app
Show information for repository myproject
Tell me about my latest repository
```

#### Combined Operations

```bash
# Parallel execution
Show my emails and list my repos
Check my Gmail and GitHub activity

# Sequential execution (data flows between tasks)
Email john@example.com the names of my top 5 repositories
Send my repo list to team@company.com
Email peter@example.com details about project awesome-app
```

### Utility Commands

- `help` - Display examples and available commands
- `status` - Check Gmail and GitHub connection status
- `history` - Show recent command history
- `clear` - Clear the terminal screen
- `exit` / `quit` / `bye` - Exit Vienna

---

## Architecture

### System Flow

```
┌─────────────────────────────────────────────────────────┐
│                     User Input                          │
│              (Natural Language Command)                 │
└───────────────────────┬─────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────┐
│               Intent Parser (Claude AI)                 │
│        • Understands natural language                   │
│        • Determines agent(s) to use                     │
│        • Plans execution strategy                       │
└───────────────────────┬─────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────┐
│              Execution Engine                           │
│        • Manages task orchestration                     │
│        • Handles parallel/sequential execution          │
│        • Manages data flow between tasks                │
└───────────┬───────────────────────────┬─────────────────┘
            │                           │
            ▼                           ▼
    ┌───────────────┐          ┌───────────────┐
    │  Gmail Agent  │          │ GitHub Agent  │
    │               │          │               │
    │  • Read       │          │  • List Repos │
    │  • Send       │          │  • Get Repo   │
    │  • Search     │          │               │
    └───────┬───────┘          └───────┬───────┘
            │                          │
            ▼                          ▼
    ┌───────────────┐          ┌───────────────┐
    │   Gmail API   │          │  GitHub API   │
    └───────┬───────┘          └───────┬───────┘
            │                          │
            └────────────┬─────────────┘
                         ▼
            ┌─────────────────────────┐
            │   MongoDB Atlas         │
            │   • Store results       │
            │   • Save history        │
            │   • Cache tokens        │
            └────────────┬────────────┘
                         ▼
            ┌─────────────────────────┐
            │   Terminal Display      │
            │   • Format results      │
            │   • Show progress       │
            │   • Display errors      │
            └─────────────────────────┘
```

### Core Components

#### Intent Parser
- Powered by Claude Sonnet 4
- Converts natural language to structured execution plans
- Maintains conversation context for follow-up queries
- Validates task feasibility against available agents

#### Execution Engine
- Orchestrates task execution
- Implements parallel and sequential execution modes
- Manages task dependencies
- Handles data extraction and template filling
- Provides comprehensive error handling

#### Agent System
- **Base Agent**: Abstract class defining agent interface
- **Gmail Agent**: Email operations via Gmail API
- **GitHub Agent**: Repository operations via GitHub API
- Extensible design for adding new agents

#### Authentication Layer
- OAuth 2.0 flow management
- Token encryption/decryption
- Automatic token refresh
- Credential storage in MongoDB
- Lazy authentication (only when needed)

#### Data Persistence
- MongoDB Atlas integration
- User and session management
- Task execution history
- Encrypted credential storage
- Conversation context tracking

---

## Configuration

### Environment Variables

Vienna is configured via environment variables in `.env`:

```env
# MongoDB Atlas Connection
MONGODB_URI=mongodb+srv://username:password@cluster.mongodb.net/
DATABASE_NAME=vienna

# Anthropic API
ANTHROPIC_API_KEY=sk-ant-api03-...

# Gmail OAuth (Google Cloud Console)
GMAIL_CLIENT_ID=123456789.apps.googleusercontent.com
GMAIL_CLIENT_SECRET=GOCSPX-...
GMAIL_REDIRECT_URI=http://localhost:8080/oauth2callback

# GitHub OAuth (Developer Settings)
GITHUB_CLIENT_ID=Iv1.abc123def456
GITHUB_CLIENT_SECRET=abcdef123456789...
GITHUB_REDIRECT_URI=http://localhost:8080/github/callback

# Security
ENCRYPTION_KEY=your-fernet-key-here
TOKEN_SALT=random-salt-string

# Logging
LOG_LEVEL=INFO
LOG_FILE=vienna.log
```

### Agent Configuration

Agents are configured in `src/config/agent_registry.yaml`:

```yaml
agents:
  gmail:
    name: GmailAgent
    type: email
    description: Manage Gmail emails
    oauth_required: true
    scopes:
      - https://www.googleapis.com/auth/gmail.readonly
      - https://www.googleapis.com/auth/gmail.send
    modes:
      read:
        description: Retrieve emails from Gmail
        parameters:
          - query (optional)
          - max_results (optional, default: 10)
          - date_filter (optional: today, this_week)
      # ... more modes
```

---

## Project Structure

```
vienna/
├── src/
│   ├── agents/                      # Agent implementations
│   │   ├── base_agent.py           # Abstract base class
│   │   ├── gmail_agent.py          # Gmail operations
│   │   └── github_agent.py         # GitHub operations
│   │
│   ├── core/                        # Core orchestration
│   │   ├── intent_parser.py        # Claude-powered NLP
│   │   ├── execution_engine.py     # Task orchestration
│   │   └── context_manager.py      # Execution state management
│   │
│   ├── auth/                        # Authentication & security
│   │   ├── credential_store.py     # Token encryption
│   │   └── oauth_manager.py        # OAuth 2.0 flows
│   │
│   ├── database/                    # Data persistence
│   │   ├── mongodb_client.py       # MongoDB client
│   │   └── models.py               # Data models & operations
│   │
│   ├── config/                      # Configuration
│   │   ├── settings.py             # Environment settings
│   │   └── agent_registry.yaml     # Agent definitions
│   │
│   └── cli/                         # Terminal interface
│       └── terminal.py             # Rich UI components
│
├── main.py                          # Application entry point
├── Dockerfile                       # Docker configuration
├── docker-compose.yml              # Docker Compose setup
├── pyproject.toml                  # Python dependencies
└── .env.example                    # Environment template
```

---

## Technology Stack

### Core Technologies

- **Language**: Python 3.11+
- **LLM**: Claude Sonnet 4 (Anthropic API)
- **Database**: MongoDB Atlas
- **Package Manager**: uv (fast Python package installer)
- **Container**: Docker & Docker Compose

### APIs & Integrations

- **Gmail API**: Google API Client Library
- **GitHub API**: PyGithub
- **OAuth 2.0**: google-auth-oauthlib

### Libraries

- **Rich**: Terminal formatting and tables
- **Pydantic**: Data validation and settings
- **Cryptography**: Fernet encryption
- **PyMongo**: MongoDB driver
- **asyncio**: Asynchronous task execution

---

## Docker Deployment

### Quick Start

```bash
# Using Docker Compose (recommended)
docker-compose run --rm vienna

# Using Docker directly
docker build -t vienna .
docker run -it --rm --env-file .env -p 8080:8080 vienna
```

### Production Deployment

Vienna includes production-ready Docker configuration with:

- **Multi-stage builds**: Optimized image size
- **Health checks**: Automatic container monitoring
- **Resource limits**: CPU and memory constraints
- **Volume mounts**: Persistent logs
- **Security**: Non-root user, minimal attack surface

---

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

### Development Setup

```bash
# Clone repository
git clone https://github.com/theMillenniumFalcon/vienna
cd vienna

# Install development dependencies
uv sync

# Code formatting
black src/
isort src/

# Type checking
mypy src/
```

---