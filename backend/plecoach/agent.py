"""LiveKit voice-agent entrypoint for Plecoach.

The module is safe to import without credentials.  Provider clients and the
Redis connection are constructed only after LiveKit dispatches a session job.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Literal

from livekit import agents
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    ConversationItemAddedEvent,
    JobContext,
    RunContext,
    TurnHandlingOptions,
    function_tool,
    inference,
)
from livekit.agents.llm import ChatMessage, ToolError

from .config import (
    LiveKitConfigurationError,
    livekit_agent_name,
    livekit_tts_config,
    load_livekit_config,
)
from .store import RedisStore
from .tutor import (
    Assistance,
    CardAssessment,
    RedisTutorStoreAdapter,
    TutorContext,
    TutorStore,
    build_initial_greeting,
    build_tutor_instructions,
)

logger = logging.getLogger("plecoach.agent")

DEFAULT_STT_MODEL = "deepgram/nova-3"
DEFAULT_LLM_MODEL = "google/gemma-4-31b-it"
ASSESSMENT_TOPIC = "plecoach.card-assessment"


@dataclass(frozen=True, slots=True)
class DispatchMetadata:
    session_id: str
    learner_id: str


def parse_dispatch_metadata(raw: str | None) -> DispatchMetadata:
    """Validate the small reference payload supplied by API agent dispatch."""

    try:
        value = json.loads(raw or "")
    except json.JSONDecodeError as exc:
        raise ValueError("LiveKit job metadata must be valid JSON") from exc
    if not isinstance(value, dict):
        raise ValueError("LiveKit job metadata must be a JSON object")
    session_id = value.get("session_id")
    learner_id = value.get("learner_id")
    if not isinstance(session_id, str) or not session_id.strip():
        raise ValueError("LiveKit job metadata is missing session_id")
    if not isinstance(learner_id, str) or not learner_id.strip():
        raise ValueError("LiveKit job metadata is missing learner_id")
    return DispatchMetadata(
        session_id=session_id.strip(),
        learner_id=learner_id.strip(),
    )


def _json_value(value: Any) -> Any:
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return model_dump(mode="json")
    return value


def _compact_mastery(value: Any) -> Any:
    """Keep realtime packets well below LiveKit's reliable-data size limit."""

    raw = _json_value(value)
    if not isinstance(raw, dict):
        return raw
    allowed = (
        "state",
        "comprehension_score",
        "usage_score",
        "assessment_count",
        "independent_successes",
        "last_assessed_at",
        "next_review_at",
    )
    return {key: raw[key] for key in allowed if key in raw}


@dataclass(slots=True)
class TutorRuntime:
    """Per-room dependencies made available to LiveKit function tools."""

    context: TutorContext
    store: TutorStore
    publish_event: Callable[[dict[str, Any]], Awaitable[None]]
    pending_writes: set[asyncio.Task[Any]] = field(default_factory=set)
    state_lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    @property
    def card_ids(self) -> frozenset[str]:
        return frozenset(card.card_id for card in self.context.target_cards)

    def write_soon(self, awaitable: Awaitable[Any]) -> None:
        task = asyncio.create_task(awaitable)
        self.pending_writes.add(task)
        task.add_done_callback(self._write_finished)

    async def append_transcript(
        self,
        role: Literal["student", "tutor"],
        text: str,
    ) -> Any:
        """Serialize session mutations so transcript and mastery writes cannot race."""

        async with self.state_lock:
            return await self.store.append_transcript(
                self.context.session_id,
                role,
                text,
            )

    async def record_assessment(self, assessment: CardAssessment) -> Any:
        """Serialize mastery and session writes with committed transcript writes."""

        async with self.state_lock:
            return await self.store.record_assessment(
                session_id=self.context.session_id,
                card_id=assessment.card_id,
                comprehension=assessment.comprehension,
                independent_usage=assessment.independent_usage,
                confidence=assessment.confidence,
                evidence=assessment.evidence,
                assistance=assessment.assistance,
            )

    def _write_finished(self, task: asyncio.Task[Any]) -> None:
        self.pending_writes.discard(task)
        if task.cancelled():
            return
        error = task.exception()
        if error is not None:
            logger.exception("Failed to persist a conversation turn", exc_info=error)

    async def drain_writes(self) -> None:
        if self.pending_writes:
            await asyncio.gather(*tuple(self.pending_writes), return_exceptions=True)


class PlecoachTutor(Agent):
    """Mandarin tutor with a transcript-backed mastery assessment tool."""

    def __init__(self, context: TutorContext) -> None:
        super().__init__(instructions=build_tutor_instructions(context))

    @function_tool()
    async def record_card_assessment(
        self,
        context: RunContext[TutorRuntime],
        card_id: str,
        comprehension: float | None,
        independent_usage: float | None,
        confidence: float,
        evidence: str,
        assistance: Assistance,
    ) -> str:
        """Record current-session evidence for one target flashcard.

        Use only after the student's own Mandarin transcript clearly demonstrates
        comprehension, incorrect understanding, correct use, or incorrect use.

        Args:
            card_id: Exact target-card identifier from the session instructions.
            comprehension: Observed understanding from 0 to 1, or null if unobserved.
            independent_usage: Contextual independent use from 0 to 1, or null.
            confidence: Confidence in the transcript-backed judgment from 0 to 1.
            evidence: Exact Mandarin words spoken by the student in this session.
            assistance: none, hint, or revealed.
        """

        runtime = context.userdata
        if card_id not in runtime.card_ids:
            raise ToolError("这个编号不属于本次目标词卡，请继续自然聊天。")
        try:
            assessment = CardAssessment.create(
                card_id=card_id,
                comprehension=comprehension,
                independent_usage=independent_usage,
                confidence=confidence,
                evidence=evidence,
                assistance=assistance,
            )
        except ValueError as exc:
            raise ToolError(
                "这次证据不足或参数不一致，请继续用中文交流，获得更清楚的学生原话后再评估。"
            ) from exc

        # A mastery mutation must finish even if the learner begins speaking.
        context.disallow_interruptions()
        mastery = await runtime.record_assessment(assessment)
        event = assessment.as_event()
        event["mastery"] = _compact_mastery(mastery)
        try:
            await runtime.publish_event(event)
        except Exception:
            # Redis is authoritative and the frontend also polls session state.
            # A transient best-effort data-channel failure must not undo mastery.
            logger.exception("Failed to publish realtime assessment update")

        # Tool output is Mandarin and tells the model not to expose scoring.
        return "已经保存这次观察。请继续自然聊天，不要向学生说明分数或评估过程。"


def create_tutor_store() -> RedisTutorStoreAdapter:
    """Create the production Redis adapter lazily for a dispatched job."""

    return RedisTutorStoreAdapter(RedisStore(redis_url=os.getenv("REDIS_URL")))


def _attach_transcript_persistence(
    session: AgentSession[TutorRuntime],
    runtime: TutorRuntime,
) -> None:
    """Persist only committed LiveKit chat items, avoiding partial-STT duplicates."""

    @session.on("conversation_item_added")
    def on_conversation_item_added(event: ConversationItemAddedEvent) -> None:
        item = event.item
        if not isinstance(item, ChatMessage):
            return
        role: Literal["student", "tutor"] | None = None
        if item.role == "user":
            role = "student"
        elif item.role == "assistant":
            role = "tutor"
        text = item.text_content.strip()
        if role is None or not text:
            return
        runtime.write_soon(
            runtime.append_transcript(
                role,
                text,
            )
        )


server = AgentServer()


@server.rtc_session(agent_name=livekit_agent_name())
async def plecoach_session(ctx: JobContext) -> None:
    """Load Redis session context and start the managed LiveKit voice pipeline."""

    dispatch = parse_dispatch_metadata(ctx.job.metadata)
    store = create_tutor_store()
    try:
        raw_context = await store.get_session_context(dispatch.session_id)
        tutor_context = TutorContext.from_value(
            raw_context,
            session_id=dispatch.session_id,
            learner_id=dispatch.learner_id,
        )
        if tutor_context.learner_id != dispatch.learner_id:
            raise ValueError("Dispatched learner does not own the tutoring session")
    except Exception:
        await store.close()
        raise

    async def publish_event(payload: dict[str, Any]) -> None:
        await ctx.room.local_participant.publish_data(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            reliable=True,
            topic=ASSESSMENT_TOPIC,
        )

    runtime = TutorRuntime(
        context=tutor_context,
        store=store,
        publish_event=publish_event,
    )
    tts_config = livekit_tts_config()

    async def cleanup() -> None:
        await runtime.drain_writes()
        complete_session = getattr(store, "complete_session", None)
        if callable(complete_session):
            try:
                await complete_session(tutor_context.session_id)
            except Exception:
                logger.exception("Failed to mark tutoring session complete")
        await store.close()

    ctx.add_shutdown_callback(cleanup)

    target_words = [card.simplified for card in tutor_context.target_cards]
    session = AgentSession[TutorRuntime](
        userdata=runtime,
        stt=inference.STT(
            model=os.getenv("LIVEKIT_STT_MODEL", DEFAULT_STT_MODEL),
            language=os.getenv("LIVEKIT_STT_LANGUAGE", "zh-CN"),
            extra_kwargs={"keyterm": target_words},
        ),
        llm=inference.LLM(
            model=os.getenv("LIVEKIT_LLM_MODEL", DEFAULT_LLM_MODEL),
        ),
        tts=inference.TTS(
            model=tts_config.model,
            voice=tts_config.voice,
            language=tts_config.language,
        ),
        turn_handling=TurnHandlingOptions(
            turn_detection=inference.TurnDetector(),
        ),
        use_tts_aligned_transcript=True,
        max_tool_steps=3,
    )
    _attach_transcript_persistence(session, runtime)

    logger.info(
        "Starting Mandarin tutoring session",
        extra={
            "session_id": tutor_context.session_id,
            "learner_id": tutor_context.learner_id,
            "target_count": len(tutor_context.target_cards),
        },
    )
    await session.start(room=ctx.room, agent=PlecoachTutor(tutor_context))
    # A generated first turn can be delayed by a cold inference path or cancelled
    # by early microphone input. Start with a short fixed Mandarin question so the
    # room becomes responsive as soon as the tutor joins.
    opening = session.say(
        build_initial_greeting(tutor_context),
        allow_interruptions=False,
    )
    await opening.wait_for_playout()


if __name__ == "__main__":
    try:
        load_livekit_config()
    except LiveKitConfigurationError as exc:
        raise SystemExit(f"LiveKit configuration error: {exc}") from exc
    agents.cli.run_app(server)
