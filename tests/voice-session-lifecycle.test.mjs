import assert from "node:assert/strict";
import test from "node:test";

import { DisconnectReason } from "livekit-client";
import { resolveRoomDisconnection } from "../app/voice-session-lifecycle.ts";

test("an explicit learner exit returns to the deck", () => {
  assert.deepEqual(
    resolveRoomDisconnection({
      userRequested: true,
      wasConnected: true,
      reason: DisconnectReason.CLIENT_INITIATED,
    }),
    { shouldExit: true, error: null },
  );
});

test("an initial connection failure stays on screen and preserves its error", () => {
  assert.deepEqual(
    resolveRoomDisconnection({
      userRequested: false,
      wasConnected: false,
      reason: DisconnectReason.JOIN_FAILURE,
      priorError: "token is not valid",
    }),
    { shouldExit: false, error: "token is not valid" },
  );
});

test("an initial disconnect without an SDK error gets actionable feedback", () => {
  const result = resolveRoomDisconnection({
    userRequested: false,
    wasConnected: false,
  });

  assert.equal(result.shouldExit, false);
  assert.match(result.error ?? "", /couldn’t connect/i);
});

test("a duplicate identity explains why an established session ended", () => {
  const result = resolveRoomDisconnection({
    userRequested: false,
    wasConnected: true,
    reason: DisconnectReason.DUPLICATE_IDENTITY,
  });

  assert.equal(result.shouldExit, false);
  assert.match(result.error ?? "", /another tab or device/i);
});

test("an unexpected established-room disconnect remains recoverable", () => {
  const result = resolveRoomDisconnection({
    userRequested: false,
    wasConnected: true,
    reason: DisconnectReason.SIGNAL_CLOSE,
  });

  assert.equal(result.shouldExit, false);
  assert.match(result.error ?? "", /ended unexpectedly/i);
});

test("an established-room disconnect supersedes an older media error", () => {
  const result = resolveRoomDisconnection({
    userRequested: false,
    wasConnected: true,
    reason: DisconnectReason.DUPLICATE_IDENTITY,
    priorError: "Microphone permission was denied",
  });

  assert.equal(result.shouldExit, false);
  assert.match(result.error ?? "", /another tab or device/i);
});
