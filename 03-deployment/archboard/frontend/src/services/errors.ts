import type { ErrorCode } from './types';

const STATUS: Record<ErrorCode, number> = {
  UNAUTHENTICATED: 401,
  FORBIDDEN: 403,
  NOT_FOUND: 404,
  VALIDATION: 422,
  LINK_INVALID: 404,
  LINK_REVOKED: 410,
  LINK_EXPIRED: 410,
  LINK_EXHAUSTED: 410,
  SESSION_ENDED: 409,
  SESSION_ARCHIVED: 410,
  SESSION_FULL: 409,
  EDIT_LOCKED: 403,
  PARTICIPANT_REMOVED: 403,
  CONFLICT: 409,
};

/** Error thrown by every backend implementation. */
export class ApiError extends Error {
  readonly status: number;
  constructor(
    readonly code: ErrorCode,
    message: string,
  ) {
    super(message);
    this.name = 'ApiError';
    this.status = STATUS[code];
  }
}

export function isApiError(err: unknown, code?: ErrorCode): err is ApiError {
  return err instanceof ApiError && (code === undefined || err.code === code);
}

export function errorMessage(err: unknown): string {
  if (err instanceof Error) return err.message;
  return 'Something went wrong';
}
