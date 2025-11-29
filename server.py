import asyncio
import websockets
import json
import random
import string
import os

# Load board and pawns from shared directory
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SHARED_DIR = os.path.join(SCRIPT_DIR, "..", "shared", "monopoly-online-shared")

with open(os.path.join(SHARED_DIR, "monopoly-wroclaw.json"), "r") as f:
    BOARD_DATA = json.load(f)

with open(os.path.join(SHARED_DIR, "pawn-set-1.json"), "r") as f:
    PAWN_DATA = json.load(f)

# Game state storage
lobbies = {}  # lobby_code -> lobby data
players = {}  # websocket -> player data
STARTING_BALANCE = 1500


def generate_lobby_code():
    """Generate a unique 6-character lobby code."""
    while True:
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        if code not in lobbies:
            return code


def get_available_pawn(lobby_code):
    """Get the next available pawn for a lobby."""
    used_pawns = [p["pawn"] for p in lobbies[lobby_code]["players"].values()]
    for pawn in PAWN_DATA["pawns"]:
        if pawn["name"] not in used_pawns:
            return pawn["name"]
    return None


async def send_json(websocket, data):
    """Helper to send JSON data to a websocket."""
    await websocket.send(json.dumps(data))
    print(f"Sent: {json.dumps(data, indent=2)}")


async def broadcast_to_lobby(lobby_code, data, exclude=None):
    """Broadcast a message to all players in a lobby."""
    if lobby_code not in lobbies:
        return
    for ws in lobbies[lobby_code]["players"]:
        if ws != exclude:
            await send_json(ws, data)


async def handle_game_create(websocket, data):
    """Handle GAME_CREATE request."""
    username = data.get("username")
    if not username:
        return {"type": "ERROR", "data": {"code": 400, "message": "Username is required"}}
    
    lobby_code = generate_lobby_code()
    pawn = PAWN_DATA["pawns"][0]["name"]  # First player gets first pawn
    
    lobbies[lobby_code] = {
        "players": {websocket: {"username": username, "pawn": pawn, "position": 0, "balance": STARTING_BALANCE, "owned-properties": [], "has_rolled": False}},
        "host": websocket,
        "started": False,
        "current_turn_index": 0,
        "player_order": [websocket]
    }
    players[websocket] = {"lobby": lobby_code, "username": username}
    
    # Send NEW_GAME response
    await send_json(websocket, {
        "type": "NEW_GAME",
        "data": {
            "lobby-code": lobby_code,
            "board": BOARD_DATA["board"],
            "pawns": PAWN_DATA["pawns"]
        }
    })
    
    # Send NEW_PLAYER response
    await send_json(websocket, {
        "type": "NEW_PLAYER",
        "data": {
            "player": {
                "username": username,
                "pawn": pawn
            }
        }
    })
    
    return None


async def handle_request_join(websocket, data):
    """Handle REQUEST_JOIN request."""
    username = data.get("username")
    lobby_code = data.get("lobby")
    
    if not username:
        return {"type": "ERROR", "data": {"code": 400, "message": "Username is required"}}
    if not lobby_code:
        return {"type": "ERROR", "data": {"code": 400, "message": "Lobby code is required"}}
    if lobby_code not in lobbies:
        return {"type": "ERROR", "data": {"code": 404, "message": "Lobby not found"}}
    if lobbies[lobby_code]["started"]:
        return {"type": "ERROR", "data": {"code": 403, "message": "Game already started"}}
    
    # Check if username is already taken in lobby
    for player_data in lobbies[lobby_code]["players"].values():
        if player_data["username"] == username:
            return {"type": "ERROR", "data": {"code": 409, "message": "Username already taken"}}
    
    pawn = get_available_pawn(lobby_code)
    if not pawn:
        return {"type": "ERROR", "data": {"code": 403, "message": "Lobby is full"}}
    
    # Add player to lobby
    lobbies[lobby_code]["players"][websocket] = {
        "username": username,
        "pawn": pawn,
        "position": 0,
        "balance": STARTING_BALANCE,
        "owned-properties": [],
        "has_rolled": False
    }
    lobbies[lobby_code]["player_order"].append(websocket)
    players[websocket] = {"lobby": lobby_code, "username": username}
    
    # Send JOIN_GAME to the joining player
    existing_players = [
        {"username": p["username"], "pawn": p["pawn"]}
        for p in lobbies[lobby_code]["players"].values()
    ]
    
    await send_json(websocket, {
        "type": "JOIN_GAME",
        "data": {
            "board": BOARD_DATA["board"],
            "pawns": PAWN_DATA["pawns"],
            "players": existing_players
        }
    })
    
    # Broadcast NEW_PLAYER to all other players in lobby
    await broadcast_to_lobby(lobby_code, {
        "type": "NEW_PLAYER",
        "data": {
            "player": {
                "username": username,
                "pawn": pawn
            }
        }
    }, exclude=websocket)
    
    return None


async def handle_game_start(websocket, data):
    """Handle GAME_START request."""
    if websocket not in players:
        return {"type": "ERROR", "data": {"code": 403, "message": "Not in a lobby"}}
    
    lobby_code = players[websocket]["lobby"]
    
    if lobbies[lobby_code]["host"] != websocket:
        return {"type": "ERROR", "data": {"code": 403, "message": "Only host can start the game"}}
    
    if len(lobbies[lobby_code]["players"]) < 2:
        return {"type": "ERROR", "data": {"code": 400, "message": "Need at least 2 players to start"}}
    
    lobbies[lobby_code]["started"] = True
    lobbies[lobby_code]["current_turn_index"] = 0
    
    # Broadcast GAME_START to all players
    await broadcast_to_lobby(lobby_code, {"type": "GAME_START", "data": {}})
    
    # Send NEXT_TURN with first player
    first_player_ws = lobbies[lobby_code]["player_order"][0]
    first_player = lobbies[lobby_code]["players"][first_player_ws]
    
    await broadcast_to_lobby(lobby_code, {
        "type": "NEXT_TURN",
        "data": {"player": first_player["username"]}
    })
    
    # Send PLAYER_DATA to each player
    for ws, player_data in lobbies[lobby_code]["players"].items():
        await send_json(ws, {
            "type": "PLAYER_DATA",
            "data": {
                "username": player_data["username"],
                "balance": player_data["balance"],
                "owned-properties": player_data["owned-properties"]
            }
        })
    
    return None


async def handle_finish_turn(websocket, data):
    """Handle FINISH_TURN request."""
    if websocket not in players:
        return {"type": "ERROR", "data": {"code": 403, "message": "Not in a lobby"}}
    
    lobby_code = players[websocket]["lobby"]
    lobby = lobbies[lobby_code]
    
    if not lobby["started"]:
        return {"type": "ERROR", "data": {"code": 400, "message": "Game not started"}}
    
    current_ws = lobby["player_order"][lobby["current_turn_index"]]
    if current_ws != websocket:
        return {"type": "ERROR", "data": {"code": 403, "message": "Not your turn"}}
    
    # Reset has_rolled for current player
    lobby["players"][websocket]["has_rolled"] = False
    
    # Move to next player
    lobby["current_turn_index"] = (lobby["current_turn_index"] + 1) % len(lobby["player_order"])
    next_ws = lobby["player_order"][lobby["current_turn_index"]]
    next_player = lobby["players"][next_ws]
    
    await broadcast_to_lobby(lobby_code, {
        "type": "NEXT_TURN",
        "data": {"player": next_player["username"]}
    })
    
    return None


async def handle_request_roll(websocket, data):
    """Handle REQUEST_ROLL request."""
    if websocket not in players:
        return {"type": "ERROR", "data": {"code": 403, "message": "Not in a lobby"}}
    
    lobby_code = players[websocket]["lobby"]
    lobby = lobbies[lobby_code]
    
    if not lobby["started"]:
        return {"type": "ERROR", "data": {"code": 400, "message": "Game not started"}}
    
    current_ws = lobby["player_order"][lobby["current_turn_index"]]
    if current_ws != websocket:
        return {"type": "ERROR", "data": {"code": 403, "message": "Not your turn"}}
    
    player = lobby["players"][websocket]
    
    # Check if player has already rolled this turn
    if player["has_rolled"]:
        return {"type": "ERROR", "data": {"code": 403, "message": "Already rolled this turn"}}
    
    # Mark that player has rolled
    player["has_rolled"] = True
    
    # Roll two dice
    dice1 = random.randint(1, 6)
    dice2 = random.randint(1, 6)
    total = dice1 + dice2
    
    old_position = player["position"]
    new_position = (old_position + total) % 40  # 40 board spaces
    player["position"] = new_position
    
    # Check if passed start
    if new_position < old_position:
        player["balance"] += 200
        await send_json(websocket, {
            "type": "TRANSACTION",
            "data": {
                "balance-change": 200,
                "balance-sync": player["balance"]
            }
        })
    
    # Broadcast SET_POSITION to all
    await broadcast_to_lobby(lobby_code, {
        "type": "SET_POSITION",
        "data": {
            "player": player["username"],
            "position": new_position
        }
    })
    
    # Check landed tile and send CHOICE if purchasable
    tile = BOARD_DATA["board"][new_position]
    if tile["properties"]["purchasable"]:
        # Check if property is already owned
        property_owned = False
        owner_ws = None
        for ws, p_data in lobby["players"].items():
            if new_position in p_data["owned-properties"]:
                property_owned = True
                owner_ws = ws
                break
        
        if not property_owned:
            # Send choice to buy
            price = tile["owner-costs"][0]
            await send_json(websocket, {
                "type": "CHOICE",
                "data": {
                    "OPTIONS": [
                        {"label": "BUY", "description": f"Buy {tile['name']} for ${price}"},
                        {"label": "PASS", "description": "Do nothing"}
                    ]
                }
            })
        elif owner_ws != websocket:
            # Pay rent to owner
            owner = lobby["players"][owner_ws]
            # Find property level (for now assume level 0)
            rent = tile["trespass-costs"][0]
            
            player["balance"] -= rent
            owner["balance"] += rent
            
            await send_json(websocket, {
                "type": "TRANSACTION",
                "data": {
                    "balance-change": -rent,
                    "balance-sync": player["balance"]
                }
            })
            await send_json(owner_ws, {
                "type": "TRANSACTION",
                "data": {
                    "balance-change": rent,
                    "balance-sync": owner["balance"]
                }
            })
    
    return None


async def handle_choice_response(websocket, data):
    """Handle CHOICE_RESPONSE from client."""
    if websocket not in players:
        return {"type": "ERROR", "data": {"code": 403, "message": "Not in a lobby"}}
    
    lobby_code = players[websocket]["lobby"]
    lobby = lobbies[lobby_code]
    player = lobby["players"][websocket]
    
    label = data.get("label")
    position = player["position"]
    tile = BOARD_DATA["board"][position]
    
    if label == "BUY":
        price = tile["owner-costs"][0]
        if player["balance"] >= price:
            player["balance"] -= price
            player["owned-properties"].append(position)
            
            await send_json(websocket, {
                "type": "TRANSACTION",
                "data": {
                    "balance-change": -price,
                    "balance-sync": player["balance"]
                }
            })
            
            await send_json(websocket, {
                "type": "PROPERTY_TRANSFER",
                "data": {
                    "property": {
                        "id": tile["id"],
                        "name": tile["name"],
                        "color": tile["color"],
                        "level": 0
                    }
                }
            })
        else:
            return {"type": "ERROR", "data": {"code": 400, "message": "Insufficient funds"}}
    
    return None


async def handle_message(websocket):
    """Main message handler for WebSocket connections."""
    try:
        async for message in websocket:
            try:
                data = json.loads(message)
                print(f"Received: {json.dumps(data, indent=2)}")
                
                msg_type = data.get("type")
                msg_data = data.get("data", {})
                
                error = None
                
                if msg_type == "GAME_CREATE":
                    error = await handle_game_create(websocket, msg_data)
                elif msg_type == "REQUEST_JOIN":
                    error = await handle_request_join(websocket, msg_data)
                elif msg_type == "GAME_START":
                    error = await handle_game_start(websocket, msg_data)
                elif msg_type == "FINISH_TURN":
                    error = await handle_finish_turn(websocket, msg_data)
                elif msg_type == "REQUEST_ROLL":
                    error = await handle_request_roll(websocket, msg_data)
                elif msg_type == "CHOICE_RESPONSE":
                    error = await handle_choice_response(websocket, msg_data)
                else:
                    error = {"type": "ERROR", "data": {"code": 400, "message": f"Unknown message type: {msg_type}"}}
                
                if error:
                    await send_json(websocket, error)
                    
            except json.JSONDecodeError:
                print(f"Invalid JSON received: {message}")
                await send_json(websocket, {"type": "ERROR", "data": {"code": 400, "message": "Invalid JSON"}})
    finally:
        # Clean up on disconnect
        if websocket in players:
            lobby_code = players[websocket]["lobby"]
            if lobby_code in lobbies:
                if websocket in lobbies[lobby_code]["players"]:
                    del lobbies[lobby_code]["players"][websocket]
                if websocket in lobbies[lobby_code]["player_order"]:
                    lobbies[lobby_code]["player_order"].remove(websocket)
                if not lobbies[lobby_code]["players"]:
                    del lobbies[lobby_code]
            del players[websocket]


async def main():
    async with websockets.serve(handle_message, "localhost", 8080):
        print("WebSocket server running on ws://localhost:8080")
        await asyncio.Future()  # Run forever

if __name__ == "__main__":
    asyncio.run(main())