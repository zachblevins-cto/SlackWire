#!/bin/bash

echo "🤖 AI News Slack Bot Setup"
echo "=========================="

# Create virtual environment
echo "Creating virtual environment..."
python3 -m venv venv

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install -r requirements.txt

# Create .env file from example
if [ ! -f .env ]; then
    echo "Creating .env file..."
    cp .env.example .env
    echo ""
    echo "⚠️  IMPORTANT: Edit .env file with your Slack credentials!"
    echo "   - SLACK_BOT_TOKEN"
    echo "   - SLACK_APP_TOKEN" 
    echo "   - SLACK_CHANNEL_ID"
    echo ""
    echo "📖 See SLACK_APP_SETUP.md for detailed instructions"
else
    echo ".env file already exists"
fi

echo ""
echo "✅ Setup complete!"
echo ""
echo "To start the bot:"
echo "  1. source venv/bin/activate"
echo "  2. python main.py"