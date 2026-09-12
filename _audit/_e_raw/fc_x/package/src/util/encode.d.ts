/**
 * Encodes a string to Base64 URL format. If TextEncoder is not available, returns an empty string.
 * @param str {string} The string to encode.
 * @return {string} The Base64 URL encoded string, or an empty string if TextEncoder is not available.
 *
 * @private
 */
export declare function encodeStringToBase64Url(str: string): string;
/**
 * Encodes a Uint8Array to Base64 URL format.
 * @param bytes {Uint8Array} The byte array to encode.
 * @returns {string} The Base64 URL encoded string.
 *
 * @private
 */
export declare function encodeBase64Url(bytes: Uint8Array): string;
//# sourceMappingURL=encode.d.ts.map