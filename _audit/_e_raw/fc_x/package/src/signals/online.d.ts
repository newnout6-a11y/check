/*!
 * Copyright (c) Friendly Captcha GmbH 2023.
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/.
 */
import { OnlineMetricStateVector } from "../types/signals";
/**
 * @internal
 */
export type OnlineMetric = {
    s: OnlineMetricStateVector;
    add(v: number): void;
};
/**
 * @internal
 */
export declare function buildOnlineMetric(): OnlineMetric;
//# sourceMappingURL=online.d.ts.map