/*!
 * Copyright (c) Friendly Captcha GmbH 2023.
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/.
 */
import { FriendlyCaptchaSDK } from "../sdk/sdk";
import { WidgetHandle } from "../sdk/widgetHandle";
import { CreateWidgetOptions } from "../types/widget";
/**
 * @internal
 */
export interface ScriptURLQueryParams {
    onload?: string;
    render?: "explicit" | "onload";
    hl?: string;
    /**
     * Only present in hcaptcha, if `"off"` then `window.grecaptcha` does not get set.
     */
    recaptchacompat?: "on" | "off";
}
/**
 * Options that can be passed to the `render` function in the ReCAPTCHA or hCaptcha compatibility mode.
 * @public
 */
export interface CompatRenderParams {
    /**
     * Required. Your public API site key.
     */
    sitekey?: string;
    theme?: "dark" | "light";
    size?: "compact" | "normal" | "invisible";
    tabindex?: number;
    callback?: string | ((response: string) => void);
    "expired-callback"?: string | (() => void);
    "chalexpired-callback"?: string | (() => void);
    "open-callback"?: string | (() => void);
    "close-callback"?: string | (() => void);
    "error-callback"?: string | (() => void);
}
/**
 * Common shared code for compatibility layers. Most captcha providers try to have the same clientside SDK interface, so we can reuse a lot of code here.
 *
 * @internal
 */
export declare class CommonCompatSDK {
    sdk: FriendlyCaptchaSDK;
    params: ScriptURLQueryParams;
    constructor(sdk: FriendlyCaptchaSDK);
    /**
     * @internal
     */
    private getURLParams;
    /**
     * @internal
     */
    performOnLoad(): void;
    /**
     * Renders a widget inside the container DOM element. Returns a unique widgetID for the widget.
     * @public
     */
    render(container: HTMLElement | string, params?: CompatRenderParams & Partial<CreateWidgetOptions>): string;
    /**
     *
     * @internal
     */
    protected getWidgetOrThrow(widgetId?: string): WidgetHandle;
    /**
     * Resets the hCaptcha widget with widgetID. Defaults to the first widget created if no `widgetID` is specified.
     * @public
     */
    reset(widgetId?: string): void;
    /**
     * Gets the response for the hCaptcha widget with widgetID. Defaults to the first widget created if no `widgetID` is specified.
     * @public
     */
    getResponse(widgetId?: string): string;
    /**
     * Triggers the widget programmatically. Defaults to the first widget created if no `widgetID` is specified.
     * @public
     */
    execute(widgetId?: string, opts?: {
        async: boolean;
    }): void | Promise<string>;
}
//# sourceMappingURL=common.d.ts.map