/*!
 * Copyright (c) Friendly Captcha GmbH 2023.
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/.
 */
export interface FlatPromise<T = any, E = any> {
    resolve: (value?: T) => void;
    reject: (reason?: E) => void;
    promise: Promise<T>;
}
/**
 * Creates a promise with the resolve and reject function outside of it, useful for tasks that may complete at any time.
 * Based on MIT licensed https://github.com/arikw/flat-promise, with typings added by gzuidhof.
 * @param executor
 */
export declare function flatPromise<T = any, E = any>(executor?: (resolve: (value?: T) => void, reject: (reason?: E) => void) => void | Promise<void>): FlatPromise<T, E>;
//# sourceMappingURL=flatPromise.d.ts.map