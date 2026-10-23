"""
Pipecat voice agent for Parallel AI — real-time speech-to-speech via Gemini Live.

Uses Pipecat framework to handle:
- Bidirectional audio streaming with Plivo telephony
- Gemini Live API for native speech recognition + speech synthesis
- Function calling to save notes and look up teammate activity
- Automatic call transcript saved on hangup
"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timezone

from dotenv import load_dotenv
from loguru import logger

from pipecat.frames.frames import (
    Frame,
    LLMMessagesAppendFrame,
    TranscriptionFrame,
    TextFrame,
    TTSStartedFrame,
    TTSStoppedFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.serializers.plivo import PlivoFrameSerializer
from pipecat.services.google.gemini_live.llm import GeminiLiveLLMService
from pipecat.transports.websocket.fastapi import (
    FastAPIWebsocketParams,
    FastAPIWebsocketTransport,
)
from pipecat.services.llm_service import FunctionCallParams

from database import SessionLocal
from models import (
    User as UserORM,
    Message as MessageORM,
    Activity as ActivityORM,
)

load_dotenv()

# ─── Configuration ───────────────────────────────────────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv(
    "GEMINI_MODEL", "models/gemini-2.5-flash-native-audio-preview-12-2025"
)
GEMINI_VOICE = os.getenv("GEMINI_VOICE", "Puck")


# ─── Transcript Collector (captures text from the call) ──────

class TranscriptCollector(FrameProcessor):
    """Listens for transcription and text frames to build a call transcript."""

    def __init__(self, caller_name: str, **kwargs):
        super().__init__(**kwargs)
        self.caller_name = caller_name
        self.transcript_lines: list[dict] = []  # {"speaker": ..., "text": ...}
        self._current_speaker = "agent"

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        # User speech transcription (from Plivo audio -> Gemini)
        if isinstance(frame, TranscriptionFrame):
            text = frame.text if hasattr(frame, "text") else str(frame)
            text = text.strip()
            if text:
                self.transcript_lines.append({
                    "speaker": self.caller_name,
                    "text": text,
                })
                logger.info(f"[Transcript] {self.caller_name}: {text[:80]}")

        # Agent text output (Gemini response text, if available)
        elif isinstance(frame, TextFrame):
            text = frame.text if hasattr(frame, "text") else str(frame)
            text = text.strip()
            if text:
                self.transcript_lines.append({
                    "speaker": "Agent",
                    "text": text,
                })
                logger.info(f"[Transcript] Agent: {text[:80]}")

        # Pass frame through unchanged
        await self.push_frame(frame, direction)

    def get_transcript_text(self) -> str:
        """Return formatted transcript string."""
        if not self.transcript_lines:
            return ""
        lines = []
        for entry in self.transcript_lines:
            lines.append(f"{entry['speaker']}: {entry['text']}")
        return "\n".join(lines)

    def get_summary_text(self) -> str:
        """Return a short summary for the activity feed."""
        if not self.transcript_lines:
            return "Voice call (no transcript captured)"
        user_msgs = [e["text"] for e in self.transcript_lines if e["speaker"] == self.caller_name]
        if user_msgs:
            preview = "; ".join(user_msgs)[:120]
            return f"[Voice Call] {preview}"
        return f"[Voice Call] {len(self.transcript_lines)} exchanges"


# ─── DB Helpers ──────────────────────────────────────────────

def _get_team_context(caller_name: str) -> str:
    """Build a text snapshot of recent team activity + shared conversation."""
    db = SessionLocal()
    try:
        activities = (
            db.query(ActivityORM)
            .order_by(ActivityORM.created_at.desc())
            .limit(15)
            .all()
        )
        activity_text = (
            "\n".join(f"- {a.user_name}: {a.summary}" for a in reversed(activities))
            or "(none)"
        )

        messages = (
            db.query(MessageORM)
            .order_by(MessageORM.created_at.asc())
            .limit(30)
            .all()
        )
        history = (
            "\n".join(f"{m.sender_name}: {m.content[:300]}" for m in messages)
            or "(none)"
        )

        return (
            f"== TEAM ACTIVITY ==\n{activity_text}\n\n"
            f"== SHARED CONVERSATION ==\n{history}"
        )
    finally:
        db.close()


def _build_voice_system_prompt(caller_name: str) -> str:
    context = _get_team_context(caller_name)
    return (
        f"You are {caller_name}'s personal AI voice assistant in the Parallel AI "
        f"team workspace.\n\n"
        f"You are having a real-time phone conversation. Keep responses concise "
        f"and natural for voice — avoid markdown, bullet points, or special "
        f"characters.\n\n"
        f"{context}\n\n"
        f"You speak only to {caller_name}. Refer to teammates by name. "
        f"If asked what someone is working on, use the activity and conversation "
        f"history above.\n\n"
        f"You have two tools:\n"
        f"  1) save_to_workspace — save an important note from this call so "
        f"teammates can see it.\n"
        f"  2) get_teammate_status — look up what a teammate has been doing.\n\n"
        f"Use them when the caller asks you to remember something or wants to "
        f"know what a teammate is up to.\n\n"
        f"IMPORTANT: At the end of the conversation, always use save_to_workspace "
        f"to save a brief summary of what was discussed, so it appears in the "
        f"team dashboard.\n\n"
        f"Be friendly, professional, and helpful."
    )


def _save_db_message(caller_name: str, content: str, role: str = "user"):
    """Persist a single message row to the database."""
    db = SessionLocal()
    try:
        user = db.query(UserORM).filter(UserORM.name == caller_name).first()
        if not user:
            logger.warning(f"User '{caller_name}' not found in DB")
            return
        db.add(
            MessageORM(
                id=str(uuid.uuid4()),
                user_id=user.id,
                sender_id=f"voice:{user.id}",
                sender_name=f"{caller_name} (voice)",
                role=role,
                content=content,
                created_at=datetime.now(timezone.utc),
            )
        )
        db.commit()
    except Exception as e:
        logger.error(f"_save_db_message error: {e}")
    finally:
        db.close()


def _save_db_activity(caller_name: str, summary: str):
    """Persist a single activity row to the database."""
    db = SessionLocal()
    try:
        user = db.query(UserORM).filter(UserORM.name == caller_name).first()
        if not user:
            return
        db.add(
            ActivityORM(
                id=str(uuid.uuid4()),
                user_id=user.id,
                user_name=caller_name,
                summary=summary,
                created_at=datetime.now(timezone.utc),
            )
        )
        db.commit()
    except Exception as e:
        logger.error(f"_save_db_activity error: {e}")
    finally:
        db.close()


def _save_call_transcript(caller_name: str, transcript: str, summary: str):
    """Save the full call transcript + summary to chat and activity after hangup."""
    db = SessionLocal()
    try:
        user = db.query(UserORM).filter(UserORM.name == caller_name).first()
        if not user:
            return

        now = datetime.now(timezone.utc)

        # Save transcript as a message in the chatbox
        db.add(MessageORM(
            id=str(uuid.uuid4()),
            user_id=user.id,
            sender_id=f"voice:{user.id}",
            sender_name=f"{caller_name} (voice call)",
            role="assistant",
            content=f"[Call Transcript]\n{transcript}",
            created_at=now,
        ))

        # Save activity summary
        db.add(ActivityORM(
            id=str(uuid.uuid4()),
            user_id=user.id,
            user_name=caller_name,
            summary=summary,
            created_at=now,
        ))

        db.commit()
        logger.info(f"Saved call transcript for {caller_name} ({len(transcript)} chars)")
    except Exception as e:
        logger.error(f"_save_call_transcript error: {e}")
    finally:
        db.close()


def _save_transcript_to_google_doc(caller_name: str, transcript: str):
    """Optionally save the transcript to a Google Doc via Composio (best-effort)."""
    try:
        from config import COMPOSIO_API_KEY, get_composio_client, CLIENTS, OPENAI_MODEL

        composio = get_composio_client()
        if not composio:
            logger.info("Composio not configured — skipping Google Doc save")
            return

        user_id = f"parallel-{caller_name.lower()}"

        # Try to get Google Docs tool
        tools = []
        try:
            got = composio.tools.get(user_id=user_id, tools=["GOOGLEDOCS_CREATE_DOCUMENT"])
            if got:
                tools = got
        except Exception:
            logger.info("Google Docs not connected for user — skipping doc save")
            return

        if not tools:
            return

        # Get OpenAI client
        name_lower = caller_name.strip().lower()
        client = CLIENTS.get(name_lower) or CLIENTS.get("sean") or next(iter(CLIENTS.values()), None)
        if not client:
            return

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        doc_title = f"Parallel AI - Voice Call - {caller_name} - {now_str}"

        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            tools=tools,
            messages=[
                {"role": "system", "content": "Create the Google Doc with the exact content provided."},
                {"role": "user", "content": (
                    f"Create a Google Doc titled '{doc_title}' with this content:\n\n"
                    f"VOICE CALL TRANSCRIPT\n"
                    f"Caller: {caller_name}\n"
                    f"Date: {now_str}\n"
                    f"{'='*40}\n\n"
                    f"{transcript}"
                )},
            ],
        )

        result = composio.provider.handle_tool_calls(response=response, user_id=user_id)
        logger.info(f"Google Doc created for call transcript: {str(result)[:200]}")

    except Exception as e:
        logger.error(f"Google Doc save failed (non-critical): {e}")


# ─── Function-call handlers (called by Gemini via Pipecat) ───

async def handle_save_to_workspace(params: FunctionCallParams):
    """Save a note from the voice call into the Parallel workspace."""
    message = params.arguments.get("message", "")
    caller_name = params.arguments.get("_caller", "Unknown")
    if not message:
        await params.result_callback({"status": "error", "reason": "empty message"})
        return
    try:
        _save_db_message(caller_name, message, role="user")
        _save_db_activity(caller_name, f"[Voice Note] {message[:60]}")
        logger.info(f"Saved voice note for {caller_name}: {message[:80]}")
        await params.result_callback(
            {"status": "success", "saved": message[:100]}
        )
    except Exception as e:
        await params.result_callback({"status": "error", "reason": str(e)})


async def handle_get_teammate_status(params: FunctionCallParams):
    """Look up recent activity for a teammate."""
    teammate = params.arguments.get("teammate_name", "")
    db = SessionLocal()
    try:
        rows = (
            db.query(ActivityORM)
            .filter(ActivityORM.user_name.ilike(f"%{teammate}%"))
            .order_by(ActivityORM.created_at.desc())
            .limit(5)
            .all()
        )
        if rows:
            text = "; ".join(a.summary for a in rows)
            await params.result_callback(
                {"teammate": teammate, "recent_activity": text}
            )
        else:
            await params.result_callback(
                {"teammate": teammate, "recent_activity": "No recent activity found."}
            )
    except Exception as e:
        await params.result_callback({"status": "error", "reason": str(e)})
    finally:
        db.close()


# ─── Main entry point ───────────────────────────────────────

async def run_agent(
    websocket,
    call_id: str,
    stream_id: str,
    caller_name: str,
    auth_id: str = "",
    auth_token: str = "",
) -> PipelineTask:
    """Run the Pipecat voice pipeline for one phone call.

    Args:
        websocket: FastAPI WebSocket connection (from Plivo Stream)
        call_id: Plivo call identifier
        stream_id: Plivo stream identifier
        caller_name: "Sean" or "Yug"
        auth_id: Plivo Auth ID
        auth_token: Plivo Auth Token

    Returns:
        The completed PipelineTask.
    """
    logger.info(
        f"Starting voice agent for {caller_name} | call={call_id} stream={stream_id}"
    )

    # Record call start
    _save_db_activity(caller_name, "[Voice Call] Started live voice call")

    # ── Transcript collector ──
    transcript_collector = TranscriptCollector(caller_name=caller_name)

    # ── Plivo serializer ──
    serializer = PlivoFrameSerializer(
        stream_id=stream_id,
        call_id=call_id,
        auth_id=auth_id or os.getenv("PLIVO_AUTH_ID", ""),
        auth_token=auth_token or os.getenv("PLIVO_AUTH_TOKEN", ""),
    )

    # ── WebSocket transport ──
    transport = FastAPIWebsocketTransport(
        websocket=websocket,
        params=FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            add_wav_header=False,
            serializer=serializer,
        ),
    )

    # ── Gemini Live LLM (speech-to-speech) ──
    system_prompt = _build_voice_system_prompt(caller_name)

    llm = GeminiLiveLLMService(
        api_key=GEMINI_API_KEY,
        model=GEMINI_MODEL,
        voice_id=GEMINI_VOICE,
        system_instruction=system_prompt,
    )

    # ── Register function-call handlers ──
    async def _save_wrapper(params: FunctionCallParams):
        params.arguments = dict(params.arguments)
        params.arguments["_caller"] = caller_name
        await handle_save_to_workspace(params)

    async def _teammate_wrapper(params: FunctionCallParams):
        await handle_get_teammate_status(params)

    llm.register_function("save_to_workspace", _save_wrapper)
    llm.register_function("get_teammate_status", _teammate_wrapper)

    # ── Pipeline (with transcript collector between LLM and output) ──
    pipeline = Pipeline(
        [
            transport.input(),        # Audio from Plivo
            llm,                      # Gemini Live (speech-to-speech + function calling)
            transcript_collector,     # Capture text/transcriptions
            transport.output(),       # Audio back to Plivo
        ]
    )

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            allow_interruptions=True,
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
    )

    # ── Send a greeting after Gemini session is ready ──
    async def send_greeting():
        await asyncio.sleep(1.5)
        logger.info(f"Sending greeting to {caller_name}")
        await task.queue_frames(
            [
                LLMMessagesAppendFrame(
                    messages=[
                        {
                            "role": "user",
                            "content": (
                                f"Greet me briefly. My name is {caller_name}. "
                                f"I'm calling into my Parallel AI workspace."
                            ),
                        }
                    ],
                    run_llm=True,
                )
            ]
        )

    asyncio.create_task(send_greeting())

    # ── Run the pipeline (blocks until call ends / hangup) ──
    runner = PipelineRunner()
    await runner.run(task)

    logger.info(f"Voice pipeline finished for {caller_name}")

    # NOTE: Transcript saving is handled by main.py after hangup.
    # It fetches the Plivo call recording, transcribes with Whisper,
    # cleans up with OpenAI, then saves to chat + Google Doc.
    # We do NOT save here to avoid duplicate/raw entries.

    return task
