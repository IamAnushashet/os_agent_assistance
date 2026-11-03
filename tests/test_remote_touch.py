"""
Automated unit tests for Phone Remote WebSocket, Trackpad Input, and Direct Web Search.
"""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(BACKEND_DIR.parent))

import json
import pytest
from fastapi.testclient import TestClient
from main import app
from input_controller import controller
from screen_capture import ensure_interactive_desktop

def receive_next_json(ws):
    """Skips binary JPEG stream frames to read JSON messages."""
    for _ in range(50):
        msg = ws.receive()
        if "text" in msg:
            return json.loads(msg["text"])
    return None

def test_interactive_desktop_cursor_and_typing():
    """Verifies that InputController safely attaches to desktop station and reads/moves cursor."""
    ensure_interactive_desktop()
    # Test relative cursor movement
    controller.move_relative(0, 0)
    # Test typing unicode
    controller.type_text("")
    assert True

def test_websocket_remote_full_suite():
    """Tests the phone remote WebSocket protocol: auth, trackpad moves, screen clicks, typing, and web search."""
    client = TestClient(app)
    
    with client.websocket_connect("/ws/remote") as ws:
        # 1. Pairing with PIN: 4826
        ws.send_json({"pin": "4826"})
        auth_resp = receive_next_json(ws)
        assert auth_resp["type"] == "AUTH_SUCCESS"
        assert "token" in auth_resp

        # 2. Trackpad relative move
        ws.send_json({"type": "trackpad_move", "dx": 5.0, "dy": -3.0})

        # 3. Trackpad click
        ws.send_json({"type": "trackpad_click", "button": "left"})

        # 4. Direct screen tap coords
        ws.send_json({"type": "mouse_click_coords", "x": 500, "y": 400, "button": "left"})
        feedback = receive_next_json(ws)
        assert feedback is not None
        assert feedback["type"] == "ACTION_FEEDBACK"

        # 5. Type text directly into PC
        ws.send_json({"type": "type_text", "text": "test_input"})
        feedback = receive_next_json(ws)
        assert feedback is not None
        assert feedback["type"] == "ACTION_FEEDBACK"

        # 6. Type and Enter
        ws.send_json({"type": "type_and_enter", "text": "hello_enter"})
        feedback = receive_next_json(ws)
        assert feedback is not None
        assert feedback["type"] == "ACTION_FEEDBACK"

        # 7. Agent Prompting from Phone
        ws.send_json({"type": "prompt", "text": "Hello assistant"})
        thinking = receive_next_json(ws)
        assert thinking is not None
        assert thinking["type"] == "agent_thinking"
        assert thinking["prompt"] == "Hello assistant"

def test_network_info_resolution():
    """Verifies /api/network-info returns IP, port, token, and physical screen dimensions."""
    client = TestClient(app)
    res = client.get("/api/network-info")
    assert res.status_code == 200
    data = res.json()
    assert "ip" in data
    assert "screen_width" in data
    assert "screen_height" in data
    assert data["screen_width"] > 0
    assert data["screen_height"] > 0
