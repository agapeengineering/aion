/** Relative server lifetime anchored to a monotonic clock, independent of wall-clock skew. */
export function verificationDeadline(seconds: number, receivedAt = performance.now()): number {
  return Number.isFinite(seconds) && seconds > 0 && seconds <= 600
    ? receivedAt + seconds * 1000
    : 0;
}
