import { parseQuery } from "../util/urlDecode";
/**
 * The ReCAPTCHA and hCaptcha SDKs allow you to pass either a string to a function on the window,
 * or a function itself.
 *
 * @internal
 */
function getWindowFunc(nameOrFunc) {
    if (typeof nameOrFunc === "function") {
        return nameOrFunc;
    }
    const fn = window[nameOrFunc];
    if (typeof fn === "function") {
        return fn;
    }
    // This error message matches the one found in the official reCAPTCHA SDK.
    console.error("Friendly Captcha couldn't find user-provided function: " + nameOrFunc);
}
/**
 * Common shared code for compatibility layers. Most captcha providers try to have the same clientside SDK interface, so we can reuse a lot of code here.
 *
 * @internal
 */
export class CommonCompatSDK {
    constructor(sdk) {
        this.sdk = sdk;
        this.params = this.getURLParams();
    }
    /**
     * @internal
     */
    getURLParams() {
        const script = document.currentScript;
        if (!script) {
            // I don't think this can ever happen in an ordinary browser, but better safe than sorry.
            console.error("[FRC Compat] current script undefined.");
            return {};
        }
        if (script.src.indexOf("?") !== -1) {
            return parseQuery("?" + script.src.split("?")[1]);
        }
        return {};
    }
    /**
     * @internal
     */
    performOnLoad() {
        // TODO: check ordering, does attaching to `frc-captcha` elements happen first or is `onload` called first?
        // In my opinion this should be the correct order, but I haven't verified this.
        if (this.params.render !== "explicit") {
            this.sdk.attach();
        }
        const ol = this.params.onload;
        if (ol) {
            const fn = getWindowFunc(ol);
            if (fn) {
                fn();
            }
        }
    }
    /**
     * Renders a widget inside the container DOM element. Returns a unique widgetID for the widget.
     * @public
     */
    render(container, params = {}) {
        let el = container;
        if (typeof container === "string") {
            el = document.getElementById(container);
        }
        if (!el) {
            throw new Error(`[FRC Compat] Could not find element ${container}`);
        }
        const widget = this.sdk.createWidget(Object.assign(Object.assign(Object.assign({}, el.dataset), params), { element: el, language: this.params.hl || undefined }));
        if (params.tabindex) {
            el.tabIndex = params.tabindex;
        }
        if (params.callback) {
            widget.addEventListener("frc:widget.complete", (ev) => {
                getWindowFunc(params.callback)(ev.detail.response);
            });
        }
        if (params["expired-callback"]) {
            widget.addEventListener("frc:widget.expire", (ev) => {
                getWindowFunc(params["expired-callback"])();
            });
        }
        if (params["error-callback"]) {
            widget.addEventListener("frc:widget.error", (ev) => {
                getWindowFunc(params["error-callback"])();
            });
        }
        if (params["open-callback"]) {
            widget.addEventListener("frc:widget.statechange", (ev) => {
                if (ev.detail.state === "requesting") {
                    getWindowFunc(params["open-callback"])();
                }
            });
        }
        return widget.id;
    }
    /**
     *
     * @internal
     */
    getWidgetOrThrow(widgetId) {
        if (!widgetId) {
            const widgets = this.sdk.getAllWidgets();
            if (!widgets) {
                throw new Error(`[FRC Compat] No widgets created yet.`);
            }
            return widgets[0];
        }
        const widget = this.sdk.getWidgetById(widgetId);
        // TODO: check if this actually errors in ReCAPTCHA or hCaptcha, only logs an error, or just fails silently. We should have the same behavior.
        if (!widget) {
            throw new Error(`[FRC Compat] Could not find widget ${widgetId}`);
        }
        return widget;
    }
    /**
     * Resets the hCaptcha widget with widgetID. Defaults to the first widget created if no `widgetID` is specified.
     * @public
     */
    reset(widgetId) {
        this.getWidgetOrThrow(widgetId).reset();
    }
    /**
     * Gets the response for the hCaptcha widget with widgetID. Defaults to the first widget created if no `widgetID` is specified.
     * @public
     */
    getResponse(widgetId) {
        return this.getWidgetOrThrow(widgetId).getResponse();
    }
    /**
     * Triggers the widget programmatically. Defaults to the first widget created if no `widgetID` is specified.
     * @public
     */
    execute(widgetId, opts = { async: false }) {
        const widget = this.getWidgetOrThrow(widgetId);
        if (!opts.async) {
            widget.start();
            return;
        }
        return new Promise((resolve, reject) => {
            widget.addEventListener("frc:widget.complete", (ev) => {
                resolve(ev.detail.response);
            });
            widget.addEventListener("frc:widget.error", (ev) => {
                reject(ev.detail.error);
            });
            widget.start();
        });
    }
}
//# sourceMappingURL=common.js.map