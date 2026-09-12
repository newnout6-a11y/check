/*!
 * Copyright (c) Friendly Captcha GmbH 2023.
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/.
 */
/**
 * By using this instead of the browser built-in URLSearchParams we can save shipping a 11kb polyfill in the polyfilled version.
 * @param queryString (starting with a `"?"`)
 * @returns an object like `{a: "3", b: "bla"}`
 *
 * @internal
 */
export declare function parseQuery(queryString: string): Record<string, string>;
//# sourceMappingURL=urlDecode.d.ts.map