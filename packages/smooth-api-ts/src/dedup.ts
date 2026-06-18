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
 * Tracks in-flight requests and coalesces identical concurrent calls
 * into a single shared Promise.
 *
 * Lifecycle
 * ---------
 * 1. First caller for key K → stores the Promise in the map, executes
 *    the network call, then removes the key when it settles.
 * 2. Subsequent callers for K (while the first is still pending) →
 *    immediately receive the **same** Promise reference.
 * 3. Once the first call settles the entry is deleted, so the *next*
 *    caller after settlement triggers a fresh network request.
 */
export class RequestDeduplicator {
  private readonly inflight: Map<string, Promise<Response>> = new Map();
  private readonly keyFn: DeduplicationKeyFn;

  constructor(keyFn?: DeduplicationKeyFn) {
    this.keyFn = keyFn ?? defaultKeyFn;
  }

  /**
   * Execute `fetcher` if no identical request is already in-flight,
   * otherwise return the existing Promise.
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
      return this.inflight.get(key)! as Promise<R>;
    }

    const promise = fetcher().finally(() => {
      this.inflight.delete(key);
    });

    this.inflight.set(key, promise as unknown as Promise<Response>);
    return promise;
  }

  /** Number of in-flight deduplicated requests. Useful for tests. */
  get size(): number {
    return this.inflight.size;
  }
}
