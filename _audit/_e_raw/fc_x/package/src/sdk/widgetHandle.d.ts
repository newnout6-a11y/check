import { SentinelResponse } from "../types/sentinel.js";
import { StartMode, WidgetErrorData, _WidgetHandleOpts, WidgetResetOptions, WidgetResetTrigger, WidgetState, WidgetMode } from "../types/widget.js";
import { FRCEventMap } from "./events.js";
/**
 * This provides an API stub that provides the end-user JS API for a widget.
 *
 * This class is only instantiated by the SDK - do not create a handle yourself.
 *
 * @public
 */
export declare class WidgetHandle {
    /**
     * A random ID that uniquely identifies this widget in this session.
     */
    readonly id: string;
    /**
     *  The element the widget is mounted under.
     * */
    private readonly e;
    private hiddenFormEl?;
    /**
     * The field in the form that should be set, `null` if no form field should be set.
     * You usually don't want to change this.
     *
     * Defaults to `"frc-captcha-response"`.
     */
    private formFieldName;
    /**
     * The sitekey for this widget. It can not be changed after creation of the widget.
     * @public
     */
    readonly sitekey?: string;
    startMode: StartMode;
    private state;
    private response;
    private focusEventPending;
    private _reset;
    private _destroy;
    private _trigger;
    /**
     * @internal
     */
    readonly ready: Promise<undefined>;
    /**
     * When this is true the widget has been destroyed and can no longer be used.
     */
    isDestroyed: boolean;
    /**
     * You don't want to create this yourself, use `FriendlyCaptcha.createWidget` instead.
     * @internal
     */
    constructor(opts: _WidgetHandleOpts);
    private handleStartMode;
    /**
     * Reset the widget, removing any progress.
     *
     * Optional argument: an object with the name of the trigger that caused the reset.
     * You would usually keep this empty. This is the `trigger` field in the `frc:widget.reset` event, which defaults to `root`.
     */
    reset(opts?: WidgetResetOptions): void;
    /**
     * Destroy the widget.
     *
     * This removes the `element` that the widget was mounted to as well as the hidden `frc-captcha-response` form field.
     */
    destroy(): void;
    /**
     * @internal
     */
    private trigger;
    /**
     * Trigger the widget to start a challenge.
     * The widget will start a challenge solving in the background.
     *
     * * In `interactive` mode, the user will need to click the widget to complete the process.
     * * In `noninteractive` mode, the widget will complete the process automatically.
     *
     */
    start(): void;
    /**
     * Sets the state of the widget, this is for internal use.
     * It is unlikely this is useful to call yourself.
     * @internal
     */
    setState(s: {
        response: SentinelResponse | string;
        state: WidgetState;
        error?: WidgetErrorData;
        resetTrigger?: WidgetResetTrigger;
        mode?: WidgetMode;
    }): void;
    private dispatchWidgetEvent;
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
    /**
     * The current state of the widget.
     */
    getState(): WidgetState;
    /**
     * The current response of the widget. This is the value that should be sent to the server and is embedded in HTML forms.
     */
    getResponse(): string;
    /**
     * The HTML element that contains the widget.
     */
    getElement(): HTMLElement;
}
//# sourceMappingURL=widgetHandle.d.ts.map