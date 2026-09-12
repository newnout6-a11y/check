/*!
 * Copyright (c) Friendly Captcha GmbH 2023.
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/.
 */
import { RiskIntelligenceGenerateData } from "../types/riskIntelligence";
import { StartMode } from "../types/widget";
import { FRCEventMap } from "./events";
/**
 * This provides a handle for configuring and managing a Risk Intelligence request
 * via an HTML element.
 *
 * This class is only instantiated by the SDK - do not create a handle yourself.
 *
 * @public
 */
export declare class RiskIntelligenceHandle {
    /**
     * The element that configures the Risk Intelligence request,
     * and under which the hidden input element is mounted.
     */
    private readonly e;
    /**
     * This will be undefined if we explicitly asked for no hidden form field.
     */
    private hiddenFormEl?;
    /**
     * A timeout ID used for firing an expiration event when this handle's
     * token expires.
     */
    private timeout;
    private data;
    /**
     * A function that closes over configuration parameters from the HTML element's
     * `data-*` attributes, used for requesting Risk Intelligence.
     */
    private requestRiskIntelligence;
    /**
     * The field in the form that should be set, `null` if no form field should be set.
     * You usually don't want to change this.
     *
     * Defaults to `"frc-risk-intelligence-token"`.
     */
    private formFieldName;
    private startMode;
    /**
     * This class is only instantiated by the SDK by calling FriendlyCaptchaSDK.attach()
     * Do not create a handle manually.
     *
     * @internal
     */
    constructor(opts: {
        element: HTMLElement;
        formFieldName?: string;
        startMode?: StartMode;
        riskIntelligence: () => Promise<RiskIntelligenceGenerateData>;
    });
    private handleStartMode;
    private request;
    /**
     * @returns Risk Intelligence data if request is done and `null` if not.
     */
    getData(): RiskIntelligenceGenerateData | null;
    /**
     * @returns The HTML element used to configure the Risk Intelligence request.
     */
    getElement(): HTMLElement;
    /**
     * Shorthand for `this.getElement().addEventListener`  (that is strictly typed in Typescript)
     */
    addEventListener<K extends keyof FRCEventMap>(type: K, listener: (this: HTMLElement, ev: FRCEventMap[K]) => any | {
        handleEvent: (ev: FRCEventMap[K]) => any;
    }, options?: AddEventListenerOptions): void;
    /**
     * Shorthand for `this.getElement().removeEventListener` (that is strictly typed in Typescript)
     */
    removeEventListener<K extends keyof FRCEventMap>(type: K, listener: (this: HTMLElement, ev: FRCEventMap[K]) => any | {
        handleEvent: (ev: FRCEventMap[K]) => any;
    }, options?: EventListenerOptions): void;
}
//# sourceMappingURL=riskIntelligenceHandle.d.ts.map