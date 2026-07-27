from __future__ import annotations

import logging

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from app.core.config import settings
from app.services.llm import generate_answer
from app.services.retriever import retrieve_chunks
from app.slack.workspace_mapper import get_or_create_user, get_org_id_for_team

logger = logging.getLogger(__name__)


def _build_slack_app() -> App:
    return App(
        token=settings.slack_bot_token,
        signing_secret=settings.slack_signing_secret,
    )


def _handle_question(question: str, team_id: str, user_id: str, say, thread_ts=None) -> None:
    """Core RAG pipeline called by both /ask and @mention handlers."""
    org_id = get_org_id_for_team(team_id)

    if not org_id:
        say(
            text="⚠️ This Slack workspace hasn't been connected to KnowledgeAssist yet. "
                 "Ask your admin to complete the setup.",
            thread_ts=thread_ts,
        )
        return

    # Get or create internal user mapping
    internal_user_id = get_or_create_user(
        slack_user_id=user_id,
        slack_team_id=team_id,
        org_id=org_id,
    )

    # RAG pipeline
    try:
        chunks = retrieve_chunks(question=question, org_id=org_id)
        answer, was_confident = generate_answer(question=question, chunks=chunks)

        # Build source reference string
        seen_docs: dict[str, str] = {}
        for chunk in chunks:
            seen_docs[chunk.document_id] = chunk.original_name
        sources_str = ", ".join(f"_{name}_" for name in seen_docs.values()) if seen_docs else "N/A"

        # Format Slack Block Kit response
        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Answer:*\n{answer}",
                },
            }
        ]

        if seen_docs and was_confident:
            blocks.append(
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": f"📄 *Sources:* {sources_str}",
                        }
                    ],
                }
            )

        if not was_confident:
            blocks.append(
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": "ℹ️ _This question wasn't covered by available documents. Please contact HR/IT._",
                        }
                    ],
                }
            )

        say(blocks=blocks, text=answer, thread_ts=thread_ts)

    except Exception as exc:
        logger.error("Slack RAG pipeline error: %s", exc, exc_info=True)
        say(
            text="❌ Something went wrong while processing your question. Please try again.",
            thread_ts=thread_ts,
        )


def register_handlers(app: App) -> None:
    """Register all Slack event/command handlers on the app instance."""

    @app.command("/ask")
    def handle_ask_command(ack, body, say):
        """Handle /ask slash command."""
        ack()  # Acknowledge immediately (Slack requires <3s response)

        question = body.get("text", "").strip()
        if not question:
            say("Please provide a question: `/ask What is the vacation policy?`")
            return

        team_id = body.get("team_id", "")
        user_id = body.get("user_id", "")
        logger.info("/ask from user=%s team=%s: %s", user_id, team_id, question)

        _handle_question(question=question, team_id=team_id, user_id=user_id, say=say)

    @app.event("app_mention")
    def handle_mention(event, say):
        """Handle @KnowledgeAssist mentions in channels."""
        # Strip the bot mention from the message text
        text = event.get("text", "")
        # Remove <@BOTID> prefix
        question = " ".join(
            word for word in text.split()
            if not word.startswith("<@")
        ).strip()

        if not question:
            say(
                text="Hi! Ask me anything about company policies. Example: `@KnowledgeAssist What is the vacation policy?`",
                thread_ts=event.get("ts"),
            )
            return

        team_id = event.get("team", "")
        user_id = event.get("user", "")
        thread_ts = event.get("thread_ts") or event.get("ts")

        logger.info("@mention from user=%s team=%s: %s", user_id, team_id, question)
        _handle_question(question=question, team_id=team_id, user_id=user_id, say=say, thread_ts=thread_ts)

    @app.event("message")
    def handle_dm(event, say):
        """Handle direct messages to the bot."""
        # Only handle DMs (channel_type == 'im'), not channel messages
        if event.get("channel_type") != "im":
            return

        # Ignore bot's own messages
        if event.get("bot_id"):
            return

        question = event.get("text", "").strip()
        if not question:
            return

        team_id = event.get("team", "")
        user_id = event.get("user", "")
        logger.info("DM from user=%s team=%s: %s", user_id, team_id, question)

        _handle_question(question=question, team_id=team_id, user_id=user_id, say=say)


def start_slack_bot() -> None:
    """
    Start the Slack Bolt app in Socket Mode.
    Called in a background thread from main.py's lifespan hook.
    Blocks indefinitely (SocketModeHandler.start() is blocking).
    """
    if not settings.slack_enabled:
        logger.info("Slack disabled — skipping bot startup")
        return

    logger.info("Starting Slack bot in Socket Mode...")
    app = _build_slack_app()
    register_handlers(app)

    handler = SocketModeHandler(app, settings.slack_app_token)
    handler.start()  # Blocks until process exits
