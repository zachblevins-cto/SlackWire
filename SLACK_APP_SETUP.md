# Slack App Setup Guide

This guide will walk you through creating and configuring a Slack app for the AI News Bot.

## Step 1: Create a New Slack App

1. Go to [api.slack.com/apps](https://api.slack.com/apps)
2. Click "Create New App"
3. Choose "From scratch"
4. Enter:
   - App Name: `AI News Bot`
   - Pick a workspace to develop your app

## Step 2: Configure Socket Mode

1. In your app settings, go to "Socket Mode" (under Settings)
2. Enable Socket Mode
3. Click "Generate" to create an app-level token
4. Name it: `socket-token`
5. Add scope: `connections:write`
6. Copy the token (starts with `xapp-`) - this is your `SLACK_APP_TOKEN`

## Step 3: Configure Bot Token Scopes

1. Go to "OAuth & Permissions" (under Features)
2. Scroll to "Scopes" → "Bot Token Scopes"
3. Add these OAuth scopes:
   - `chat:write` - Send messages
   - `channels:read` - View basic channel info
   - `app_mentions:read` - View messages that mention @bot
   - `commands` - Add slash commands

## Step 4: Install App to Workspace

1. Still in "OAuth & Permissions"
2. Click "Install to Workspace" at the top
3. Review permissions and click "Allow"
4. Copy the "Bot User OAuth Token" (starts with `xoxb-`) - this is your `SLACK_BOT_TOKEN`

## Step 5: Enable Event Subscriptions

1. Go to "Event Subscriptions" (under Features)
2. Toggle "Enable Events" to On
3. Under "Subscribe to bot events", add:
   - `app_mention` - When someone mentions the bot
4. Save changes

## Step 6: Add Slash Commands (Optional)

1. Go to "Slash Commands" (under Features)
2. Click "Create New Command"
3. Add command:
   - Command: `/ai-news-status`
   - Request URL: Leave empty (handled by Socket Mode)
   - Short Description: `Check AI News Bot status`
4. Save

## Step 7: Get Channel ID

1. In Slack, right-click on the channel where you want the bot to post
2. Select "View channel details"
3. At the bottom, you'll see the Channel ID (starts with `C`)
4. Copy this - this is your `SLACK_CHANNEL_ID`

## Step 8: Invite Bot to Channel

1. In your Slack channel, type: `/invite @AI News Bot`
2. The bot should now have access to post in this channel

## Step 9: Configure Environment Variables

1. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```

2. Edit `.env` and add your tokens:
   ```
   SLACK_BOT_TOKEN=xoxb-your-bot-token
   SLACK_APP_TOKEN=xapp-your-app-token
   SLACK_CHANNEL_ID=C1234567890
   ```

## Troubleshooting

### Bot not responding
- Check that Socket Mode is enabled
- Verify all tokens are correct
- Check bot has been invited to the channel

### Permission errors
- Ensure all required scopes are added
- Reinstall the app after adding new scopes

### Rate limiting
- The bot posts in batches to avoid rate limits
- Adjust `CHECK_INTERVAL_MINUTES` if needed

## Security Notes

- Never commit your `.env` file
- Keep your tokens secret
- Rotate tokens if compromised
- Use environment variables in production