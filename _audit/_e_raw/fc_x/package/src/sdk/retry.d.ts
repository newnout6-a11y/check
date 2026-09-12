/*!
 * Copyright (c) Friendly Captcha GmbH 2023.
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/.
 */
/**
 * Build a retry origin list with these rules:
 * 1) The first entry is the primary origin (origins[0]).
 * 2) Remaining entries are fallback origins (origins[1..]) in shuffled order.
 *
 * Example:
 * origins = ["https://0.example.com", "https://1.example.com", "https://2.example.com", "https://3.example.com"]
 * shuffled fallbacks (example) = ["https://2.example.com", "https://3.example.com", "https://1.example.com"]
 * output origins = [
 *   "https://0.example.com",
 *   "https://2.example.com",
 *   "https://3.example.com",
 *   "https://1.example.com"
 * ]
 *
 * @private
 */
export declare function getRetryOrigins(origins: string[]): string[];
/**
 * Returns the index in retryOrigins to use for a given attempt number.
 *
 * - Attempts 0, 1, and 2 map to index 0 (primary).
 * - Following attempts map to fallback indices in order.
 * - If attempts exceed unique fallbacks, a random fallback index is used.
 *
 * @private
 */
export declare function getRetryOriginIndex(attemptNumber: number, retryOrigins: string[]): number;
/**
 * Builds a retry URL by replacing the source origin with `nextOrigin` and
 * appending a `retry=<n>` query parameter.
 *
 * - Supports absolute and relative `src` values.
 * - Normalizes `nextOrigin` to its origin (ignoring trailing slashes/paths).
 * - Assumes `src` does not contain a URL fragment (`#...`).
 *
 * @private
 */
export declare function getRetrySrc(src: string, nextOrigin: string, retryCount: number): string;
//# sourceMappingURL=retry.d.ts.map