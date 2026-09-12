/*!
 * Copyright (c) Friendly Captcha GmbH 2023.
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/.
 */
import { APIEndpoint, CreateWidgetOptions } from "../types/widget.js";
import { WidgetHandle } from "./widgetHandle.js";
import { RiskIntelligenceGenerateData, RiskIntelligenceOptions, RiskIntelligenceClearOptions } from "../types/riskIntelligence.js";
import { RiskIntelligenceHandle } from "./riskIntelligenceHandle.js";
/**
 * Options when creating a new SDK instance.
 * @public
 */
export interface FriendlyCaptchaSDKOptions {
    /**
     * Start the background agent (and solver) immediately, defaults to `true`.
     */
    startAgent?: boolean;
    /**
     * The API endpoint to use, defaults to `https://global.frcapi.com`.
     *
     * Supports the following shortcuts:
     * - `eu` - `https://eu.frcapi.com`
     * - `global` - `https://global.frcapi.com`
     */
    apiEndpoint?: APIEndpoint;
    /**
     * Whether to disable the patching of `window.eval`. Useful when the patching breaks your site, which in particular
     * may affect some hot reloading functionality for Webpack (in `dev` mode).
     */
    disableEvalPatching?: boolean;
    /**
     * Opaque context that associates this SDK with a Friendly Guard screening flow.
     * You should never need to set this option, this is for (internal) Friendly Guard interstitial integrations only.
     *
     * @internal
     */
    guardContext?: string;
}
/**
 * Main entry point for V2 of the Friendly Captcha SDK. This class keeps track of widgets and allows you to create widgets programmatically.
 *
 * Generally there should only be one instance of this SDK in your website.
 * @public
 */
export declare class FriendlyCaptchaSDK {
    private apiEndpoint?;
    /**
     * The Friendly Guard context for this page (not relevant for ordinary Friendly Captcha integrations).
     * @internal
     */
    private guardContext?;
    /**
     * Multiple agents may be running at the same time, this is the case if someone uses widgets with different endpoints on a single page.
     * This is a mapping from the origin to the IFrame.
     */
    private agents;
    /**
     * A mapping from the agent ID to its local state.
     */
    private agentState;
    /**
     * Mapping of widget ID to the widget handle.
     */
    private widgets;
    /**
     * @internal
     */
    private bus;
    private _attached;
    /**
     * A promise that resolves to all the widgets that are currently attached.
     * @public
     */
    attached: Promise<WidgetHandle[]>;
    /**
     * A mapping of random IDs to promises that resolve to a risk intelligence
     * token generation response. Each call to `riskIntelligence()` will return
     * a promise that gets a unique ID. The mapping is used for tying the agent
     * message to its reply.
     */
    private riskIntelligencePromises;
    /**
     * A mapping of random IDs to promises that resolve when a risk intelligence
     * clear request completes. Each call to `clearRiskIntelligence()`  will return
     * a promise that gets a unique ID. The mapping is used for tying the agent message
     * to its reply.
     */
    private clearRiskIntelligencePromises;
    /**
     * A list of handles (objects that manage a Risk Intelligence DOM element)
     * associated with the SDK instance.
     */
    private riskIntelligenceHandles;
    /**
     * @internal
     */
    private signals;
    private getRetryOrigins;
    constructor(opts?: FriendlyCaptchaSDKOptions);
    private onReceiveMessage;
    private handleRiskIntelligenceMessage;
    private handleWidgetLanguageChange;
    private handleSignalsGetMessage;
    private handleStoreMessage;
    /**
     * Ensures an agent iframe exists for the configured primary origin in `retryOrigins`.
     *
     * Reuses an existing iframe when possible (within this SDK instance and across SDK
     * instances on the same page), otherwise creates and registers a new one with retry
     * failover across `retryOrigins`.
     *
     * @param retryOrigins - Ordered retry origins with the primary origin at index 0.
     * @returns String - The agent ID for the reused or newly created iframe.
     */
    private ensureAgentIFrame;
    /**
     * @internal
     */
    private setupPeriodicRefresh;
    /**
     * @internal
     */
    private getRetryTimeout;
    /**
     * Attaches a widget to given element or elements if they are not attached to yet.
     *
     * You can pass one or more HTML elements to attach to, or undefined. If `undefined` is passed, the HTML page is scanned
     * for unattached widget elements (= elements with the `frc-captcha` class).
     *
     * Returns handles to the newly-attached elements.
     * @public
     */
    attach(elements?: HTMLElement | HTMLElement[] | NodeListOf<Element>): WidgetHandle[];
    /**
     * Creates a Friendly Captcha widget with given options under given HTML element.
     * @public
     */
    createWidget(opts: CreateWidgetOptions): WidgetHandle;
    /**
     * Creates a Risk Intelligence token generation request, returning a Promise that resolves
     * to the generated token.
     *
     * @public
     */
    riskIntelligence(opts: RiskIntelligenceOptions): Promise<RiskIntelligenceGenerateData>;
    /**
     * Clears cached Risk Intelligence tokens. Cached tokens for a given sitekey can be cleared
     * by specifying it; if a sitekey is not specified, all tokens will be cleared from the cache.
     *
     * @public
     */
    clearRiskIntelligence(opts?: RiskIntelligenceClearOptions): Promise<any>;
    /**
     * Returns all current widgets known about (in an unspecified order).
     * @public
     */
    getAllWidgets(): WidgetHandle[];
    /**
     * Retrieves a widget by its widget ID.
     * @public
     */
    getWidgetById(id: string): WidgetHandle | undefined;
    /**
     * Returns all current Risk Intelligence handles known about (in an unspecified order).
     * @public
     */
    getAllRiskIntelligenceHandles(): RiskIntelligenceHandle[];
    /**
     * Completely remove all widgets and background agents related to the SDK on this page.
     * @public
     */
    clear(): void;
}
//# sourceMappingURL=sdk.d.ts.map