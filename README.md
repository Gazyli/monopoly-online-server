# Monopoly Online Server

A Python WebSocket server for the Monopoly Online game.

## Requirements

- Python 3.8+
- websockets library

## Installation

1. Clone the repository:
   ```bash
   mkdir server
   cd server
   git clone https://github.com/Gazyli/monopoly-online-server.git
   cd monopoly-online-server
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Running the Server

Start the server:
```bash
python server.py
```

The server will start on `ws://localhost:8080`.

## Communication Protocol

The server communicates using JSON messages over WebSocket. See [comm-protocol.md](../shared/monopoly-online-shared/comm-protocol.md) for the full protocol specification.

### Supported Message Types

| Client → Server | Description |
|-----------------|-------------|
| `GAME_CREATE` | Create a new game lobby |
| `REQUEST_JOIN` | Join an existing lobby |
| `GAME_START` | Start the game (host only) |
| `REQUEST_ROLL` | Roll dice and move |
| `FINISH_TURN` | End your turn |
| `CHOICE_RESPONSE` | Respond to a choice prompt |

| Server → Client | Description |
|-----------------|-------------|
| `NEW_GAME` | Lobby created successfully |
| `NEW_PLAYER` | A player joined the lobby |
| `JOIN_GAME` | Successfully joined a lobby |
| `GAME_START` | Game has started |
| `NEXT_TURN` | It's a player's turn |
| `PLAYER_DATA` | Player balance and properties |
| `SET_POSITION` | Player moved to a new position |
| `TRANSACTION` | Balance change occurred |
| `PROPERTY_TRANSFER` | Property ownership changed |
| `CHOICE` | Player must make a choice |
| `ERROR` | An error occurred |

## Project Structure

```
server/monopoly-online-server/
├── server.py          # Main WebSocket server
├── requirements.txt   # Python dependencies
└── README.md          # This file

shared/monopoly-online-shared/
├── comm-protocol.md       # Communication protocol docs
├── monopoly-wroclaw.json  # Board configuration
└── pawn-set-1.json        # Pawn colors configuration
```
