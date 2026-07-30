"""FastAPI entrypoint for deck import, planning, and LiveKit connection setup."""

from __future__ import annotations

import json
import os
import re
import uuid
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Annotated

from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    Response,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware

from .config import (
    LiveKitConfig,
    LiveKitConfigurationError,
    livekit_configuration_errors,
    load_livekit_config,
)
from .pleco_parser import MAX_XML_BYTES, PlecoParseError, parse_pleco_xml
from .session_planner import InvalidSelectionError, SessionPlanner
from .schemas import (
    ConnectionDetails,
    ConnectionRequest,
    DeckResponse,
    HealthResponse,
    ImportResponse,
    LegacyConnectionRequest,
    SessionCreateRequest,
    SessionRecord,
)
from .store import (
    DeckNotFoundError,
    RedisStore,
    SessionNotFoundError,
    Store,
)

_LEARNER_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,80}$")


def get_store(request: Request) -> Store:
    return request.app.state.store


StoreDependency = Annotated[Store, Depends(get_store)]


def get_session_planner(request: Request) -> SessionPlanner:
    return request.app.state.session_planner


SessionPlannerDependency = Annotated[SessionPlanner, Depends(get_session_planner)]


def _cors_origins() -> list[str]:
    raw = os.getenv(
        "CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
    )
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


def _connection_token(
    *,
    room_name: str,
    participant_identity: str,
    participant_name: str,
    metadata: str,
    configuration: LiveKitConfig | None = None,
) -> str:
    """Create a participant JWT that explicitly dispatches the named agent."""

    config = configuration or _require_livekit_configuration()

    try:
        from livekit import api
    except ImportError as exc:  # pragma: no cover - packaging/startup guard
        raise HTTPException(
            status_code=503, detail="The LiveKit server SDK is unavailable."
        ) from exc

    return (
        api.AccessToken(config.api_key, config.api_secret)
        .with_identity(participant_identity)
        .with_name(participant_name)
        .with_grants(
            api.VideoGrants(
                room_join=True,
                room=room_name,
                can_publish=True,
                can_subscribe=True,
                can_publish_data=True,
            )
        )
        .with_room_config(
            api.RoomConfiguration(
                agents=[
                    api.RoomAgentDispatch(
                        agent_name=config.agent_name,
                        metadata=metadata,
                    )
                ]
            )
        )
        .with_ttl(timedelta(hours=2))
        .to_jwt()
    )


def _require_livekit_configuration() -> LiveKitConfig:
    try:
        return load_livekit_config()
    except LiveKitConfigurationError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"LiveKit configuration is invalid: {exc}",
        ) from exc


def create_app(store: Store | None = None) -> FastAPI:
    injected_store = store

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        owns_store = injected_store is None
        application.state.store = injected_store or RedisStore()
        # A failed Redis connection should fail production startup: there is no
        # silent in-process persistence fallback.
        await application.state.store.ping()
        application.state.session_planner = SessionPlanner(application.state.store)
        try:
            yield
        finally:
            if owns_store:
                await application.state.store.close()

    application = FastAPI(
        title="Plecoach API",
        version="0.1.0",
        description="Pleco deck import, lesson planning, and LiveKit session access.",
        lifespan=lifespan,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @application.get("/api/health", response_model=HealthResponse)
    async def health(response: Response, state: StoreDependency) -> HealthResponse:
        try:
            redis_ok = await state.ping()
        except Exception:
            redis_ok = False
        livekit_configured = not livekit_configuration_errors()
        if not redis_ok or not livekit_configured:
            response.status_code = 503
        return HealthResponse(
            status="ok" if redis_ok and livekit_configured else "degraded",
            redis="ok" if redis_ok else "unavailable",
            livekit_configured=livekit_configured,
        )

    @application.post("/api/decks/import", response_model=ImportResponse)
    async def import_deck(
        state: StoreDependency,
        file: UploadFile = File(...),
        learner_id: str = Form(...),
    ) -> ImportResponse:
        if not _LEARNER_ID_RE.fullmatch(learner_id):
            raise HTTPException(
                status_code=422,
                detail="learner_id must contain only letters, numbers, '_' or '-'.",
            )
        filename = file.filename or "Pleco deck.xml"
        xml_bytes = await file.read(MAX_XML_BYTES + 1)
        await file.close()
        try:
            cards = parse_pleco_xml(xml_bytes)
        except PlecoParseError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return await state.import_cards(learner_id, cards, filename)

    async def deck_for(learner_id: str, state: Store) -> DeckResponse:
        try:
            return await state.get_deck(learner_id)
        except (DeckNotFoundError, ValueError) as exc:
            status = 404 if isinstance(exc, DeckNotFoundError) else 422
            raise HTTPException(status_code=status, detail=str(exc)) from exc

    @application.get("/api/decks/current", response_model=DeckResponse)
    async def current_deck(learner_id: str, state: StoreDependency) -> DeckResponse:
        """Compatibility alias for clients that keep learner ID in a query."""

        return await deck_for(learner_id, state)

    @application.get("/api/decks/{learner_id}", response_model=DeckResponse)
    async def get_deck(learner_id: str, state: StoreDependency) -> DeckResponse:
        return await deck_for(learner_id, state)

    @application.delete("/api/learners/{learner_id}", status_code=204)
    async def delete_learner(
        learner_id: str,
        state: StoreDependency,
    ) -> Response:
        try:
            await state.delete_learner_data(learner_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return Response(status_code=204)

    @application.post("/api/sessions", response_model=SessionRecord, status_code=201)
    async def create_session(
        request: SessionCreateRequest, planner: SessionPlannerDependency
    ) -> SessionRecord:
        try:
            return await planner.create_session(
                learner_id=request.learner_id,
                category_paths=request.category_paths,
                target_count=request.target_count,
            )
        except DeckNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except InvalidSelectionError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @application.get("/api/sessions/{session_id}", response_model=SessionRecord)
    async def get_session(session_id: str, state: StoreDependency) -> SessionRecord:
        try:
            return await state.get_session(session_id)
        except SessionNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    async def issue_connection(
        session_id: str, request: ConnectionRequest, state: Store
    ) -> ConnectionDetails:
        config = _require_livekit_configuration()
        try:
            session = await state.get_session(session_id)
            if request.topic is not None:
                session = await state.set_session_topic(session_id, request.topic)
        except SessionNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        suffix = uuid.uuid4().hex[:8]
        participant_identity = request.participant_identity or (
            f"{session.learner_id[:60]}-{suffix}"
        )
        participant_name = request.participant_name or "Learner"
        metadata = json.dumps(
            {"session_id": session.session_id, "learner_id": session.learner_id},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        token = _connection_token(
            room_name=session.room_name,
            participant_identity=participant_identity,
            participant_name=participant_name,
            metadata=metadata,
            configuration=config,
        )
        return ConnectionDetails(
            server_url=config.url,
            token=token,
            participant_token=token,
            room_name=session.room_name,
            session_id=session.session_id,
            participant_identity=participant_identity,
        )

    @application.post(
        "/api/sessions/{session_id}/connection", response_model=ConnectionDetails
    )
    async def connection_details(
        session_id: str,
        request: ConnectionRequest,
        state: StoreDependency,
    ) -> ConnectionDetails:
        return await issue_connection(session_id, request, state)

    @application.post("/api/connection-details", response_model=ConnectionDetails)
    async def legacy_connection_details(
        request: LegacyConnectionRequest, state: StoreDependency
    ) -> ConnectionDetails:
        try:
            session = await state.get_session(request.session_id)
        except SessionNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        if session.learner_id != request.learner_id:
            raise HTTPException(
                status_code=409, detail="The session does not belong to this learner."
            )
        return await issue_connection(request.session_id, request, state)

    return application


app = create_app()
