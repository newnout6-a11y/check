export declare const SESSION_COUNT_KEY = "frc_sc";
export declare const SESSION_ID_KEY = "frc_sid";
/**
 * @internal
 */
export declare function sessionCount(increase: boolean): string;
/**
 * @internal
 */
export declare function sessionId(): string;
/**
 * Key value storage with different layers.
 *
 * It has support for:
 *   - SessionStorage
 *   - In Memory store (i.e. a `Map<string, string>`)
 *
 * @internal
 */
export declare class Store {
    private storePrefix;
    /**
     * Fallback memory-only store
     */
    private mem;
    constructor(prefix: string);
    get(key: string): string | undefined;
    set(key: string, value: string | undefined): void;
}
//# sourceMappingURL=persist.d.ts.map