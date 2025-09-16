#!/usr/bin/env python3
"""Test Slack connection"""

import os
from dotenv import load_dotenv
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

# Load environment variables
load_dotenv()

def test_slack_connection():
    bot_token = os.getenv('SLACK_BOT_TOKEN')
    app_token = os.getenv('SLACK_APP_TOKEN')
    channel_id = os.getenv('SLACK_CHANNEL_ID')
    
    print("Testing Slack connection...")
    print(f"Bot token: {bot_token[:20]}...")
    print(f"App token: {app_token[:20]}...")
    print(f"Channel ID: {channel_id}")
    
    # Test with WebClient
    client = WebClient(token=bot_token)
    
    try:
        # Test auth
        print("\n1. Testing authentication...")
        result = client.auth_test()
        print(f"✅ Auth successful! Bot name: {result['user']}")
        
        # Test channel access
        print("\n2. Testing channel access...")
        result = client.conversations_info(channel=channel_id)
        print(f"✅ Channel found: #{result['channel']['name']}")
        
        # Test posting
        print("\n3. Testing message posting...")
        result = client.chat_postMessage(
            channel=channel_id,
            text="🧪 Test message from SlackWire bot"
        )
        print(f"✅ Message posted successfully!")
        
        # Test with blocks
        print("\n4. Testing block message...")
        result = client.chat_postMessage(
            channel=channel_id,
            blocks=[
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": "🧪 SlackWire Test"
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "If you see this, the bot can post messages with blocks!"
                    }
                }
            ],
            text="SlackWire test with blocks"
        )
        print(f"✅ Block message posted successfully!")
        
    except SlackApiError as e:
        print(f"\n❌ Slack API Error: {e.response['error']}")
        print(f"Details: {e.response}")

if __name__ == "__main__":
    test_slack_connection()