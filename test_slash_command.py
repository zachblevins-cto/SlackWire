#!/usr/bin/env python3
"""
Test script to verify slash command handling and Socket Mode connection
"""

import os
import asyncio
import json
from datetime import datetime
from dotenv import load_dotenv
from slack_sdk.web.async_client import AsyncWebClient
from slack_sdk.socket_mode.aiohttp import SocketModeClient

# Load environment variables
load_dotenv()

async def test_slash_command_registration():
    """Test if slash commands are properly registered"""

    bot_token = os.getenv('SLACK_BOT_TOKEN')
    app_token = os.getenv('SLACK_APP_TOKEN')

    if not bot_token or not app_token:
        print("❌ Missing SLACK_BOT_TOKEN or SLACK_APP_TOKEN in .env")
        return False

    print(f"✅ Bot token found: {bot_token[:20]}...")
    print(f"✅ App token found: {app_token[:20]}...")

    # Test Web API connection
    web_client = AsyncWebClient(token=bot_token)

    try:
        # Test auth
        auth_response = await web_client.auth_test()
        print(f"✅ Bot authenticated as: {auth_response['user']} (ID: {auth_response['user_id']})")
        print(f"   Team: {auth_response['team']} (ID: {auth_response['team_id']})")

        # Check bot permissions
        if 'ok' in auth_response and auth_response['ok']:
            print("✅ Bot has valid authentication")

    except Exception as e:
        print(f"❌ Auth test failed: {e}")
        return False

    # Test Socket Mode connection
    socket_client = SocketModeClient(
        app_token=app_token,
        web_client=web_client
    )

    print("\n📡 Testing Socket Mode connection...")

    received_events = []

    @socket_client.socket_mode_request_listeners.append
    async def handle_test_request(client, req):
        """Test handler to capture events"""
        event_type = req.type
        timestamp = datetime.now().isoformat()

        print(f"  📨 Received event: {event_type} at {timestamp}")
        print(f"     Envelope ID: {req.envelope_id}")

        if req.type == "slash_commands":
            command = req.payload.get("command", "unknown")
            print(f"     Command: {command}")
            print(f"     User: {req.payload.get('user_id')}")
            print(f"     Channel: {req.payload.get('channel_id')}")

        received_events.append({
            "type": event_type,
            "timestamp": timestamp,
            "payload": req.payload if req.type == "slash_commands" else None
        })

        # Always acknowledge
        from slack_sdk.socket_mode.response import SocketModeResponse
        response = SocketModeResponse(envelope_id=req.envelope_id)
        await client.send_socket_mode_response(response)
        print(f"  ✅ Acknowledged {req.envelope_id}")

    try:
        # Connect to Socket Mode
        await socket_client.connect()
        print("✅ Connected to Slack Socket Mode")

        print("\n⏳ Listening for events for 30 seconds...")
        print("   Try running /ai-news-latest in Slack now!")

        # Listen for 30 seconds
        await asyncio.sleep(30)

        print(f"\n📊 Received {len(received_events)} events:")
        for event in received_events:
            print(f"   - {event['type']} at {event['timestamp']}")
            if event['payload'] and event['type'] == 'slash_commands':
                print(f"     Command: {event['payload'].get('command')}")

        # Disconnect
        await socket_client.disconnect()
        print("\n✅ Test completed successfully")

        return True

    except Exception as e:
        print(f"❌ Socket Mode connection failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def check_slash_commands_api():
    """Check registered slash commands via API"""
    bot_token = os.getenv('SLACK_BOT_TOKEN')

    web_client = AsyncWebClient(token=bot_token)

    print("\n📋 Checking registered commands...")

    try:
        # This requires admin permissions, might fail
        response = await web_client.api_call(
            api_method="apps.manifest.export",
            params={}
        )

        if response.get("ok"):
            manifest = response.get("manifest", {})
            commands = manifest.get("features", {}).get("slash_commands", [])
            print(f"Found {len(commands)} slash commands:")
            for cmd in commands:
                print(f"  - {cmd.get('command')}: {cmd.get('description')}")
        else:
            print("Note: Cannot check app manifest (requires admin permissions)")

    except Exception as e:
        print(f"Note: Cannot check app manifest: {e}")

    print("\n💡 Make sure your Slack app has:")
    print("   1. Socket Mode enabled")
    print("   2. Slash commands created (like /ai-news-latest)")
    print("   3. Bot Token Scopes: chat:write, commands")
    print("   4. Event Subscriptions enabled (if using Socket Mode)")
    print("   5. App installed to workspace")

async def main():
    print("=" * 60)
    print("🧪 SlackWire Slash Command Test")
    print("=" * 60)

    # Run tests
    success = await test_slash_command_registration()
    await check_slash_commands_api()

    if success:
        print("\n✅ All tests passed!")
    else:
        print("\n❌ Some tests failed. Check the output above.")

    print("\nIf slash commands still show 'dispatch_failed':")
    print("1. Check that the app is installed to your workspace")
    print("2. Verify slash commands are created in the Slack app settings")
    print("3. Ensure Socket Mode is enabled with a valid app token")
    print("4. Check that the bot has required permissions")

if __name__ == "__main__":
    asyncio.run(main())