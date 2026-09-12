import { CreateWidgetOptions } from "../types/widget";
import { FriendlyCaptchaSDK } from "./sdk";
export declare const AGENT_FRAME_CLASSNAME = "frc-i-agent";
/**
 * @internal
 */
export declare function createAgentIFrame(frcSDK: FriendlyCaptchaSDK, agentId: string, src: string, guardContext: string | undefined): HTMLIFrameElement;
export declare function createWidgetIFrame(agentId: string, widgetId: string, widgetUrl: string, opts: CreateWidgetOptions, guardContext: string | undefined): HTMLIFrameElement;
/**
 * Creates a placeholder box that is shown while the widget is loading.
 * This is useful if the widget takes a while to load, or never ends up loading: the user will see a box with some text
 * explaining what is going on instead of a blank error page.
 * @internal
 */
export declare function createWidgetPlaceholder(opts: CreateWidgetOptions): HTMLDivElement;
export declare function createBanner(opts: CreateWidgetOptions): void;
export declare function getLanguageFromOptionsOrParent(opts: CreateWidgetOptions): string;
/**
 * Replaces element with a fallback message (ie, after all retries failed).
 */
export declare function createFallback(el: HTMLElement, apiOrigin: string, language: string): void;
//# sourceMappingURL=create.d.ts.map