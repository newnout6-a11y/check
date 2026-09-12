/*!
 * Copyright (c) Friendly Captcha GmbH 2023.
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/.
 */
/**
 * Returns a pseudo-random ID of given length from [a-zA-Z0-9], or a custom alphabet
 */
export declare function randomId(length: number, chars?: string): string;
/**
 * Returns a shuffled copy of the input array using Fisher-Yates (input is not mutated).
 *
 * @private
 */
export declare function shuffledCopy<T>(values: T[]): T[];
//# sourceMappingURL=random.d.ts.map