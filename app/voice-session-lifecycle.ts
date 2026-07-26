import { DisconnectReason } from "livekit-client";

export interface RoomDisconnection {
  userRequested: boolean;
  wasConnected: boolean;
  reason?: DisconnectReason;
  priorError?: string | null;
}

export interface RoomDisconnectionDisposition {
  shouldExit: boolean;
  error: string | null;
}

export function resolveRoomDisconnection({
  userRequested,
  wasConnected,
  reason,
  priorError,
}: RoomDisconnection): RoomDisconnectionDisposition {
  if (userRequested) {
    return { shouldExit: true, error: null };
  }

  const preservedError = priorError?.trim();
  if (
    preservedError &&
    (!wasConnected || reason === DisconnectReason.JOIN_FAILURE)
  ) {
    return { shouldExit: false, error: preservedError };
  }

  if (!wasConnected || reason === DisconnectReason.JOIN_FAILURE) {
    return {
      shouldExit: false,
      error:
        "Plecoach couldn’t connect to the voice room. Check your network and LiveKit configuration, then try again.",
    };
  }

  if (reason === DisconnectReason.DUPLICATE_IDENTITY) {
    return {
      shouldExit: false,
      error:
        "This session was opened in another tab or device. Close it there, then try again.",
    };
  }

  if (
    reason === DisconnectReason.PARTICIPANT_REMOVED ||
    reason === DisconnectReason.ROOM_DELETED ||
    reason === DisconnectReason.ROOM_CLOSED
  ) {
    return {
      shouldExit: false,
      error: "The voice room was closed. Try reconnecting or return to your deck.",
    };
  }

  if (reason === DisconnectReason.AGENT_ERROR) {
    return {
      shouldExit: false,
      error:
        "The tutor encountered an error and the voice room closed. Try reconnecting.",
    };
  }

  return {
    shouldExit: false,
    error:
      "The voice connection ended unexpectedly. Try reconnecting or return to your deck.",
  };
}
