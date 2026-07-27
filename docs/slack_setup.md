# Slack App Setup Guide

This guide walks you through creating a Slack app, enabling Socket Mode, and connecting it to the Company Knowledge Assistant backend.

---

## Step 1: Create a Slack App

1. Go to [api.slack.com/apps](https://api.slack.com/apps)
2. Click **Create New App** → **From scratch**
3. Give it a name (e.g., `KnowledgeAssist`) and select your Slack workspace
4. Click **Create App**

---

## Step 2: Enable Socket Mode

Socket Mode lets the bot receive events without a public URL — perfect for Railway deployments.

1. In your app settings, go to **Settings → Socket Mode**
2. Toggle **Enable Socket Mode** → ON
3. Give the App-Level Token a name (e.g., `socket-token`)
4. Select scope: `connections:write`
5. Click **Generate** → copy the **App-Level Token** (`xapp-...`)
6. Set it as `SLACK_APP_TOKEN` in your backend `.env`

---

## Step 3: Configure OAuth Scopes

1. Go to **Features → OAuth & Permissions**
2. Under **Bot Token Scopes**, add:

| Scope | Purpose |
|-------|---------|
| `app_mentions:read` | Detect @mentions |
| `chat:write` | Send messages |
| `commands` | Handle `/ask` slash command |
| `im:history` | Read DMs |
| `im:write` | Reply in DMs |
| `channels:history` | Read channel messages where bot is invited |

3. Scroll up and click **Install to Workspace** → authorize
4. Copy the **Bot User OAuth Token** (`xoxb-...`)
5. Set it as `SLACK_BOT_TOKEN` in your backend `.env`

---

## Step 4: Get the Signing Secret

1. Go to **Settings → Basic Information**
2. Under **App Credentials**, copy the **Signing Secret**
3. Set it as `SLACK_SIGNING_SECRET` in your backend `.env`

---

## Step 5: Create the `/ask` Slash Command

1. Go to **Features → Slash Commands**
2. Click **Create New Command**
3. Fill in:
   - Command: `/ask`
   - Request URL: `https://your-railway-backend.up.railway.app/slack/events`
     *(With Socket Mode this URL isn't actually called, but Slack still requires it — use any valid HTTPS URL)*
   - Short Description: `Ask a question about company policies`
   - Usage Hint: `[your question]`
4. Click **Save**

---

## Step 6: Enable Event Subscriptions

1. Go to **Features → Event Subscriptions**
2. Toggle **Enable Events** → ON
3. Under **Subscribe to bot events**, add:
   - `app_mention` — for @mentions in channels
   - `message.im` — for direct messages

---

## Step 7: Map Slack Workspace → Organization

After the bot is running, add a row to the `slack_workspaces` table in Supabase:

```sql
INSERT INTO slack_workspaces (org_id, slack_team_id, slack_team_name)
VALUES (
  'your-org-uuid-here',     -- from the organizations table
  'T0123456789',            -- Slack Team ID (found in workspace URL or Slack admin)
  'Acme Corp'
);
```

The Slack Team ID can be found at: **Slack Admin → Settings → Workspace Settings → Workspace ID**

---

## Step 8: Test the Integration

1. Start the backend with Slack env vars set: `uvicorn main:app --reload`
2. In your Slack workspace, invite the bot to a channel: `/invite @KnowledgeAssist`
3. Try: `/ask What is the vacation policy?`
4. Or @mention: `@KnowledgeAssist what are the sick leave rules?`

The bot will reply in-thread with the answer and the source document name.

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Bot not responding | Check `SLACK_APP_TOKEN` starts with `xapp-`, not `xoxb-` |
| "dispatch_failed" error | Check `SLACK_SIGNING_SECRET` matches your app's signing secret |
| No org found for workspace | Add the workspace→org mapping in `slack_workspaces` table |
| Bot replies but no answer | Check `ANTHROPIC_API_KEY` and `VOYAGE_API_KEY` are set |
