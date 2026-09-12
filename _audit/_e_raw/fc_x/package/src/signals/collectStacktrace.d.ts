/*!
 * Copyright (c) Friendly Captcha GmbH 2023.
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/.
 */
/**
 * @internal
 */
export type RootTraceRecord = {
    /** Date.now() */
    d: number;
    /** Performance.now() */
    pnow: number;
    /** Name */
    n: string;
    /** Stack trace */
    st: string;
};
/**
 * Defensively patch native functions to capture stack traces.
 */
export declare const patchNativeFunctions: (opts: {
    disableEvalPatching?: boolean;
}) => () => RootTraceRecord[];
//# sourceMappingURL=collectStacktrace.d.ts.map