import type { DeduplicationKeyFn } from "./types.js";

/**
 * Default key derivation: stringified URL only.
 * This intentionally ignores `options` (e.g. headers, body) so that
 * concurrent GET /users/1 calls are always collapsed, even when the
 * caller did not customise the key function.
 *
 * For mutation-safe deduplication (POST, PUT …) supply a custom
 * `keyFn` via `DeduplicationConfig.keyFn`.
 */
const defaultKeyFn: DeduplicationKeyFn = (url) => url.toString();

/**
 * Clone `result` if it is a `Response` — necessary because `Response` bodies
 * are single-consumption streams.  Non-Response values (fallback objects, etc.)
 * are returned as-is.
 */
function cloneIfResponse<R>(result: R): R {
  if (result instanceof Response) {
    return result.clone() as unknown as R;
  }
  return result;
}

/**
 * Tracks in-flight requests and coalesces identical concurrent calls
 * into a single shared Promise.
 *
 * Lifecycle
 * ---------
 * 1. First caller for key K → starts the network call, stores the raw
 *    Promise in the map, and returns a `.then(clone)` chain so the
 *    original `Response` body stream is never consumed by anyone.
 * 2. Subsequent callers for K (while the first is still pending) →
 *    attach their own `.then(clone)` to the same shared Promise, each
 *    receiving an independent cloned `Response`.
 * 3. Once the shared Promise settles the entry is deleted, so the *next*
 *    caller after settlement triggers a fresh network request.
 *
 * Response cloning
 * ----------------
 * `fetch()` returns a `Response` whose body is a one-time-readable stream.
 * If two callers received the *same* `Response` object, whichever reads
 * `.json()` / `.text()` first would disturb the body for the other.
 * To avoid this, the raw result is kept in the inflight map and every
 * caller — including the first one — receives `response.clone()`, leaving
 * the stored original unconsumed and safe to clone again.
 */
export class RequestDeduplicator {
  /** Stores the raw (un-cloned) shared Promise for each in-flight key. */
  private readonly inflight: Map<string, Promise<unknown>> = new Map();
  private readonly keyFn: DeduplicationKeyFn;

  constructor(keyFn?: DeduplicationKeyFn) {
    this.keyFn = keyFn ?? defaultKeyFn;
  }

  /**
   * Execute `fetcher` if no identical request is already in-flight,
   * otherwise attach to the existing Promise.  In either case the caller
   * receives `Response.clone()` so body streams are independent.
   *
   * @param url     - Same value passed to the outer resilientFetch.
   * @param options - Same value passed to the outer resilientFetch.
   * @param fetcher - A thunk that performs the actual network call.
   */
  execute<R>(
    url: string | URL,
    options: RequestInit | undefined,
    fetcher: () => Promise<R>
  ): Promise<R> {
    const key = this.keyFn(url, options);

    // null means: "skip deduplication for this request"
    if (key === null) {
      return fetcher();
    }

    if (this.inflight.has(key)) {
      // Attach to the existing in-flight promise and return a fresh clone
      // so this caller's Response stream is fully independent.
      return (this.inflight.get(key) as Promise<R>).then(cloneIfResponse);
    }

    const raw = fetcher().finally(() => {
      this.inflight.delete(key);
    });

    this.inflight.set(key, raw);

    // The first caller also gets a clone so the raw result stored in the
    // map is never body-consumed, keeping it safe to clone for latecomers.
    return raw.then(cloneIfResponse);
  }

  /** Number of in-flight deduplicated requests. Useful for tests. */
  get size(): number {
    return this.inflight.size;
  }
}
