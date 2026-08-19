/**
 * Session rules (AUTH-09 / OD-03).
 *
 * The inactivity period is APPROVED: TDMS signs a user out after 30 minutes
 * without activity.
 *
 * Whether a maximum session duration applies in addition to the inactivity
 * timeout has NOT been approved, so TDMS applies no maximum. The constant below
 * stays `null` until a value is approved; it is not a default.
 */

/** Approved: 30 minutes of inactivity ends the TDMS session. */
export const INACTIVITY_TIMEOUT_MINUTES = 30;

export const INACTIVITY_TIMEOUT_MS = INACTIVITY_TIMEOUT_MINUTES * 60_000;

/** Not approved. `null` means no maximum session duration is enforced. */
export const MAXIMUM_SESSION_DURATION_MINUTES: number | null = null;

/** Browser events that count as user activity for the inactivity timer. */
export const ACTIVITY_EVENTS = ['pointerdown', 'keydown', 'wheel', 'touchstart', 'focus'] as const;
