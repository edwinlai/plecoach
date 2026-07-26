interface TranscriptStreamInfo {
  id?: string;
  timestamp?: number;
  attributes?: Record<string, string>;
}

export interface TranscriptFragment {
  text: string;
  participantInfo: {
    identity: string;
  };
  streamInfo?: TranscriptStreamInfo;
}

export interface TranscriptTurn {
  id: string;
  participantIdentity: string;
  text: string;
  segmentIds: string[];
  transcribedTrackId: string;
  lastTimestamp: number;
}

const SEGMENT_ID_ATTRIBUTE = "lk.segment_id";
const TRANSCRIBED_TRACK_ID_ATTRIBUTE = "lk.transcribed_track_id";
export const MAX_TURN_SEGMENT_GAP_MS = 8_000;

function segmentId(
  fragment: TranscriptFragment,
  fallbackIndex: number,
): string {
  return (
    fragment.streamInfo?.attributes?.[SEGMENT_ID_ATTRIBUTE] ??
    fragment.streamInfo?.id ??
    `segment-${fallbackIndex}`
  );
}

function coalesceSegmentRevisions(
  fragments: readonly TranscriptFragment[],
): Array<TranscriptFragment & { segmentId: string }> {
  const coalesced: Array<TranscriptFragment & { segmentId: string }> = [];
  const positions = new Map<string, number>();

  fragments.forEach((fragment, index) => {
    const id = segmentId(fragment, index);
    const revisionKey = `${fragment.participantInfo.identity}:${id}`;
    const existingPosition = positions.get(revisionKey);
    const withId = { ...fragment, segmentId: id };

    if (existingPosition === undefined) {
      positions.set(revisionKey, coalesced.length);
      coalesced.push(withId);
    } else {
      coalesced[existingPosition] = withId;
    }
  });

  return coalesced;
}

function boundarySeparator(left: string, right: string): string {
  const leftCharacter = left.at(-1) ?? "";
  const rightCharacter = right.at(0) ?? "";
  const latinOrNumber = /[\p{Letter}\p{Number}]/u;
  const cjk = /\p{Script=Han}/u;

  if (
    latinOrNumber.test(leftCharacter) &&
    latinOrNumber.test(rightCharacter) &&
    !cjk.test(leftCharacter) &&
    !cjk.test(rightCharacter)
  ) {
    return " ";
  }
  return "";
}

export function mergeTranscriptText(current: string, next: string): string {
  const left = current.trim();
  const right = next.trim();

  if (!left) return right;
  if (!right) return left;

  // Distinct segment IDs can contain intentional repetition or self-correction.
  // Preserve every recognized word; same-ID revisions were coalesced above.
  return `${left}${boundarySeparator(left, right)}${right}`;
}

function validTimestamp(value: number | undefined): value is number {
  return typeof value === "number" && Number.isFinite(value) && value > 0;
}

function canExtendTurn(
  turn: TranscriptTurn,
  fragment: TranscriptFragment,
): boolean {
  const timestamp = fragment.streamInfo?.timestamp;
  const trackId =
    fragment.streamInfo?.attributes?.[TRANSCRIBED_TRACK_ID_ATTRIBUTE] ?? "";

  return (
    turn.participantIdentity === fragment.participantInfo.identity &&
    Boolean(trackId) &&
    trackId === turn.transcribedTrackId &&
    validTimestamp(timestamp) &&
    validTimestamp(turn.lastTimestamp) &&
    timestamp >= turn.lastTimestamp &&
    timestamp - turn.lastTimestamp <= MAX_TURN_SEGMENT_GAP_MS
  );
}

/**
 * Present transcription segments as conversational turns. A speaker change is
 * always a boundary. Nearby segments from the same microphone stay in one row,
 * while long gaps, track changes, and reconnects begin a new row.
 */
export function groupTranscriptTurns(
  fragments: readonly TranscriptFragment[],
): TranscriptTurn[] {
  const turns: TranscriptTurn[] = [];

  for (const fragment of coalesceSegmentRevisions(fragments)) {
    const text = fragment.text.trim();
    const participantIdentity = fragment.participantInfo.identity;
    if (!text || !participantIdentity) continue;

    const previous = turns.at(-1);
    if (previous && canExtendTurn(previous, fragment)) {
      previous.text = mergeTranscriptText(previous.text, text);
      previous.segmentIds.push(fragment.segmentId);
      previous.lastTimestamp = fragment.streamInfo?.timestamp ?? 0;
      continue;
    }

    const transcribedTrackId =
      fragment.streamInfo?.attributes?.[TRANSCRIBED_TRACK_ID_ATTRIBUTE] ?? "";
    turns.push({
      id: `${participantIdentity}:${fragment.segmentId}`,
      participantIdentity,
      text,
      segmentIds: [fragment.segmentId],
      transcribedTrackId,
      lastTimestamp: fragment.streamInfo?.timestamp ?? 0,
    });
  }

  return turns;
}
