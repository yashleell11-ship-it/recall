/**
 * The pieces of the network layer that both `api.ts` and `mock.ts` need.
 *
 * They live here rather than in `api.ts` because the fixture backend raises the
 * same error type the real one does — importing it from `api.ts`, which imports
 * `mock.ts`, would be a cycle.
 */

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export const MOCK = process.env.NEXT_PUBLIC_MOCK === "1";

export class ApiError extends Error {
  readonly status: number;
  readonly path: string;

  constructor(status: number, path: string, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.path = path;
  }
}

/** Turn anything thrown by fetch or the API into one readable sentence. */
export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    return err.status === 0
      ? `Could not reach the API at ${API_BASE}.`
      : `${err.message} (${err.status})`;
  }
  if (err instanceof Error) return err.message;
  return "Something went wrong.";
}
