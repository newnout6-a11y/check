import { CommunicationBus } from "../communication/bus.js";
import { randomId } from "../util/random.js";
import { originOf } from "../util/url.js";
import { createBanner, createAgentIFrame, createFallback, createWidgetIFrame, AGENT_FRAME_CLASSNAME, createWidgetPlaceholder, getLanguageFromOptionsOrParent, } from "./create.js";
import { getLocalizedWidgetTitle, getLocalizedText, isRTLLanguage } from "./localization.js";
import { findFRCElements, removeWidgetRootStyles, setWidgetRootStyles } from "./dom.js";
import { flatPromise } from "../util/flatPromise.js";
import { WidgetHandle } from "./widgetHandle.js";
import { Store } from "./persist.js";
import { getSignals } from "../signals/collect.js";
import { stringHasPrefix } from "../util/string.js";
import { mergeObject } from "../util/object.js";
import { resolveAPIOrigins, getSDKAPIEndpoint, getSDKDisableEvalPatching, getSDKGuardContext } from "./options.js";
import { tz } from "../util/tz.js";
import { encodeStringToBase64Url } from "../util/encode.js";
import { RiskIntelligenceHandle } from "./riskIntelligenceHandle.js";
import { getRetryOrigins as buildRetryOrigins, getRetryOriginIndex, getRetrySrc } from "./retry.js";
const agentEndpoint = "/api/v2/captcha/agent";
const widgetEndpoint = "/api/v2/captcha/widget";
const FRAME_ID_DATASET_FIELD = "FrcFrameId";
// Stable key for deduplicating agent iframes by their configured primary origin.
// We cannot rely on iframe src origin because retries may switch the iframe to fallback origins.
const AGENT_ORIGIN_KEY_DATASET_FIELD = "FrcAgentOriginKey";
/**
 * After a long interval we refresh the agent and widget iframes.
 * This is for users that leave their browser open for multiple days, it should prevent them from getting
 * into some weird state due to outdated versions of the page.
 */
const IFRAME_EXP_TIME = 1000 * 60 * 60 * 36; // 36 hours
// In ms, one per attempt. Short first try, then much longer waits so slow connections can finish.
// Total ~72 secs before giving up.
const IFRAME_LOAD_TIMEOUTS = [3000, 5000, 8000, 18000, 38000];
const MAX_IFRAME_LOAD_ATTEMPTS = IFRAME_LOAD_TIMEOUTS.length;
/**
 * Singleton communication bus.
 * Multiple SDKs may be running at the same time, but they should all use the same bus.
 * This is lazily initialized in the SDK constructor.
 * @internal
 * */
let cbus;
/**
 * Number of SDKs created.
 * Ideally one should only ever create one SDK, but it is an easy mistake to make.
 * This allows us to warn the user if they create multiple SDKs, and surpress some expected (non-fatal) errors.
 * */
let sdkC = 0;
/**
 * Main entry point for V2 of the Friendly Captcha SDK. This class keeps track of widgets and allows you to create widgets programmatically.
 *
 * Generally there should only be one instance of this SDK in your website.
 * @public
 */
export class FriendlyCaptchaSDK {
    getRetryOrigins(origins) {
        return buildRetryOrigins(origins);
    }
    constructor(opts = {}) {
        /**
         * Multiple agents may be running at the same time, this is the case if someone uses widgets with different endpoints on a single page.
         * This is a mapping from the origin to the IFrame.
         */
        this.agents = new Map();
        /**
         * A mapping from the agent ID to its local state.
         */
        this.agentState = new Map();
        /**
         * Mapping of widget ID to the widget handle.
         */
        this.widgets = new Map();
        this._attached = flatPromise();
        /**
         * A promise that resolves to all the widgets that are currently attached.
         * @public
         */
        this.attached = this._attached.promise;
        /**
         * A mapping of random IDs to promises that resolve to a risk intelligence
         * token generation response. Each call to `riskIntelligence()` will return
         * a promise that gets a unique ID. The mapping is used for tying the agent
         * message to its reply.
         */
        this.riskIntelligencePromises = new Map();
        /**
         * A mapping of random IDs to promises that resolve when a risk intelligence
         * clear request completes. Each call to `clearRiskIntelligence()`  will return
         * a promise that gets a unique ID. The mapping is used for tying the agent message
         * to its reply.
         */
        this.clearRiskIntelligencePromises = new Map();
        /**
         * A list of handles (objects that manage a Risk Intelligence DOM element)
         * associated with the SDK instance.
         */
        this.riskIntelligenceHandles = [];
        this.apiEndpoint = opts.apiEndpoint;
        this.guardContext = opts.guardContext || getSDKGuardContext();
        cbus = cbus || new CommunicationBus();
        cbus.listen((msg) => this.onReceiveMessage(msg));
        this.bus = cbus;
        sdkC++;
        if (sdkC > 1) {
            console.warn("Multiple Friendly Captcha SDKs created, this is not recommended. Please use a single SDK instance.");
        }
        this.signals = getSignals({
            disableEvalPatching: opts.disableEvalPatching || getSDKDisableEvalPatching(),
        });
        if (opts.startAgent) {
            const origins = resolveAPIOrigins(this.apiEndpoint || getSDKAPIEndpoint());
            const retryOrigins = this.getRetryOrigins(origins);
            this.ensureAgentIFrame(retryOrigins);
        }
        this.setupPeriodicRefresh();
    }
    onReceiveMessage(msg) {
        if (msg.type === "root_set_response") {
            const w = this.widgets.get(msg.widget_id);
            if (!w) {
                if (sdkC === 1) {
                    console.warn(`Received set response message for widget ${msg.widget_id} that doesn't exist`);
                }
                return;
            }
            w.setState(msg);
        }
        else if (stringHasPrefix(msg.type, "root_store")) {
            this.handleStoreMessage(msg);
        }
        else if (msg.type === "root_signals_get") {
            this.handleSignalsGetMessage(msg);
        }
        else if (msg.type === "widget_language_change") {
            this.handleWidgetLanguageChange(msg);
        }
        else if (msg.type === "widget_reset") {
            // The user clicked the reset button within the widget.
            const w = this.widgets.get(msg.from_id);
            if (!w) {
                if (sdkC === 1) {
                    console.warn(`Received reset message for widget ${msg.from_id} that doesn't exist`);
                }
                return;
            }
            w.reset({ trigger: "widget" });
        }
        else if (stringHasPrefix(msg.type, "root_risk_intelligence")) {
            this.handleRiskIntelligenceMessage(msg);
        }
    }
    handleRiskIntelligenceMessage(msg) {
        if (msg.type === "root_risk_intelligence_generate_reply") {
            const promise = this.riskIntelligencePromises.get(msg.uid);
            if (promise) {
                if (msg.data) {
                    promise.resolve(msg.data);
                }
                else if (msg.error) {
                    promise.reject(msg.error);
                }
                else {
                    console.warn("Received risk intelligence generate reply message with no data");
                }
                this.riskIntelligencePromises.delete(msg.uid);
            }
            else {
                console.warn("Received risk intelligence generate reply message with no promise to resolve");
            }
        }
        else if (msg.type === "root_risk_intelligence_clear_reply") {
            const promise = this.clearRiskIntelligencePromises.get(msg.uid);
            if (promise) {
                if (msg.error) {
                    promise.reject(msg.error);
                }
                else {
                    promise.resolve();
                }
            }
            else {
                console.warn("Received risk intelligence clear reply message with no promise to resolve");
            }
            this.clearRiskIntelligencePromises.delete(msg.uid);
        }
    }
    handleWidgetLanguageChange(msg) {
        const w = this.widgets.get(msg.from_id);
        if (!w) {
            if (sdkC === 1) {
                console.warn(`Received language change message for widget ${msg.from_id} that doesn't exist`);
            }
            return;
        }
        const element = w.getElement();
        const iframe = element.querySelector("iframe");
        if (iframe) {
            iframe.title = getLocalizedWidgetTitle(msg.language);
        }
        const banner = element.querySelector(".frc-banner");
        if (banner) {
            const bs = banner.style;
            if (isRTLLanguage(msg.language)) {
                bs.left = "6px";
                bs.right = "auto";
            }
            else {
                bs.left = "auto";
                bs.right = "6px";
            }
        }
    }
    handleSignalsGetMessage(msg) {
        const sigs = this.signals.get(msg.widget_id);
        this.bus.send({
            type: "root_signals_get_reply",
            from_id: "",
            to_id: msg.from_id,
            _frc: 1,
            rid: msg.rid,
            value: sigs,
        });
    }
    handleStoreMessage(msg) {
        const from = msg.from_id;
        const s = this.agentState.get(from);
        if (!s) {
            // Should never happen
            console.error(`Store not found ${from}`);
            return;
        }
        if (msg.type === "root_store_get") {
            this.bus.send({
                type: "root_store_get_reply",
                from_id: "",
                to_id: from,
                _frc: 1,
                rid: msg.rid,
                value: s.store.get(msg.key),
                sa: true, // Backwards compatibility: we always say that storage access is possible.
            });
        }
        else if (msg.type === "root_store_set") {
            s.store.set(msg.key, msg.value);
            this.bus.send({
                type: "root_store_set_reply",
                from_id: "",
                to_id: from,
                _frc: 1,
                rid: msg.rid,
                sa: true, // Backwards compatibility: we always say that storage access is possible.
            });
        }
    }
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
    ensureAgentIFrame(retryOrigins) {
        let attempt = 1;
        const originIndex = getRetryOriginIndex(attempt, retryOrigins);
        const origin = retryOrigins[originIndex];
        const src = origin + agentEndpoint;
        const maxAttempts = MAX_IFRAME_LOAD_ATTEMPTS;
        // Fast-path: if this SDK instance already tracks an agent for this configured origin, reuse it.
        const existing = this.agents.get(origin);
        if (existing && existing.dataset[FRAME_ID_DATASET_FIELD]) {
            return existing.dataset[FRAME_ID_DATASET_FIELD];
        }
        // Cross-instance idempotency: if another SDK instance already created an agent for this origin,
        // find and reuse it using the stable configured-origin key.
        let agentIFrames = document.getElementsByClassName(AGENT_FRAME_CLASSNAME);
        for (let index = 0; index < agentIFrames.length; index++) {
            const i = agentIFrames[index];
            if (i.dataset[AGENT_ORIGIN_KEY_DATASET_FIELD] === origin && i.dataset[FRAME_ID_DATASET_FIELD]) {
                this.agents.set(origin, i);
                return i.dataset[FRAME_ID_DATASET_FIELD];
            }
        }
        const agentId = "a_" + randomId(12);
        const el = createAgentIFrame(this, agentId, src, this.guardContext);
        el.dataset[AGENT_ORIGIN_KEY_DATASET_FIELD] = origin;
        const initialSrc = el.src;
        let currentOrigin = origin;
        this.agents.set(origin, el);
        this.agentState.set(agentId, { store: new Store(origin), origin: origin });
        document.body.appendChild(el);
        const registerWithRetry = () => {
            this.bus.registerTargetIFrame("agent", agentId, el, this.getRetryTimeout(attempt)).then((status) => {
                // The agent is no longer tracked once `clear()` runs, at which point retrying it is pointless.
                if (this.agents.get(origin) !== el)
                    return;
                if (status === "timeout") {
                    if (attempt >= maxAttempts) {
                        console.error(`[Friendly Captcha] Failed to load agent iframe after ${attempt - 1} retries.`);
                        el.remove();
                        this.agents.delete(origin);
                        // We can consider reloading all widgets that use this agent ID.
                        return;
                    }
                    const nextAttempt = attempt + 1;
                    const nextIndex = getRetryOriginIndex(nextAttempt, retryOrigins);
                    currentOrigin = retryOrigins[nextIndex] || currentOrigin;
                    console.warn("[Friendly Captcha] Retrying agent iframe load.");
                    el.src = getRetrySrc(initialSrc, currentOrigin, nextAttempt - 1);
                    attempt = nextAttempt;
                    registerWithRetry();
                }
            });
        };
        registerWithRetry();
        return agentId;
    }
    /**
     * @internal
     */
    setupPeriodicRefresh() {
        let count = 1;
        setInterval(() => {
            const e = "&expire=" + count++;
            this.agents.forEach((el, origin) => {
                el.src += e;
            });
            this.widgets.forEach((w, id) => {
                const iframe = w.getElement().querySelector("iframe");
                iframe.src += e;
            });
        }, IFRAME_EXP_TIME);
    }
    /**
     * @internal
     */
    getRetryTimeout(retryLoadCounter) {
        // Clamped so an out-of-range attempt reuses the nearest timeout instead of undefined.
        return IFRAME_LOAD_TIMEOUTS[Math.min(Math.max(retryLoadCounter, 1), MAX_IFRAME_LOAD_ATTEMPTS) - 1];
    }
    /**
     * Attaches a widget to given element or elements if they are not attached to yet.
     *
     * You can pass one or more HTML elements to attach to, or undefined. If `undefined` is passed, the HTML page is scanned
     * for unattached widget elements (= elements with the `frc-captcha` class).
     *
     * Returns handles to the newly-attached elements.
     * @public
     */
    attach(elements) {
        const [captchaElements, riskIntelligenceElements] = findFRCElements();
        for (let index = 0; index < riskIntelligenceElements.length; index++) {
            const hElement = riskIntelligenceElements[index];
            if (hElement && !hElement.frcRiskIntelligence) {
                const ds = hElement.dataset;
                const sitekey = ds.sitekey;
                if (!sitekey) {
                    console.warn("Risk Intelligence <div> found with no sitekey, skipping...", hElement);
                    continue;
                }
                this.riskIntelligenceHandles.push(new RiskIntelligenceHandle({
                    element: hElement,
                    formFieldName: ds.formFieldName,
                    startMode: ds.start,
                    riskIntelligence: () => {
                        return this.riskIntelligence({
                            sitekey,
                            apiEndpoint: ds.apiEndpoint,
                        });
                    },
                }));
            }
        }
        if (elements === undefined) {
            elements = captchaElements;
        }
        if (!(Array.isArray(elements) || elements instanceof NodeList)) {
            elements = [elements];
        }
        const newWidgets = [];
        for (let index = 0; index < elements.length; index++) {
            const hElement = elements[index];
            if (hElement && !hElement.frcWidget) {
                const ds = hElement.dataset;
                const opts = {
                    element: hElement,
                    sitekey: ds.sitekey,
                    formFieldName: ds.formFieldName,
                    apiEndpoint: ds.apiEndpoint,
                    language: ds.lang,
                    theme: ds.theme, // Perhaps we should we check for valid values?
                    startMode: ds.start, // Perhaps we should we check for valid values?
                };
                newWidgets.push(this.createWidget(opts));
            }
        }
        const allWidgets = this.getAllWidgets();
        this._attached.resolve(allWidgets);
        this.attached = Promise.resolve(allWidgets);
        return newWidgets;
    }
    /**
     * Creates a Friendly Captcha widget with given options under given HTML element.
     * @public
     */
    createWidget(opts) {
        const origins = resolveAPIOrigins(opts.apiEndpoint || this.apiEndpoint || getSDKAPIEndpoint());
        const retryOrigins = this.getRetryOrigins(origins);
        let attempt = 1;
        this.bus.addOrigins(origins);
        const origin = retryOrigins[getRetryOriginIndex(attempt, retryOrigins)] || origins[0];
        const agentId = this.ensureAgentIFrame(retryOrigins);
        const widgetId = "w_" + randomId(12);
        const send = (msg) => {
            const msgToSend = { from_id: widgetId, to_id: agentId, _frc: 1 };
            this.bus.send(mergeObject(msgToSend, msg));
        };
        const callbacks = {
            onDestroy: () => {
                send({ type: "root_destroy_widget" });
                this.bus.removeTarget(widgetId);
                this.widgets.delete(widgetId);
                opts.element.innerHTML = "";
                removeWidgetRootStyles(opts.element);
            },
            onReset: () => {
                send({ type: "root_reset_widget" });
            },
            onTrigger: (data) => {
                send({ type: "root_trigger_widget", trigger: data.trigger });
            },
        };
        const registered = flatPromise();
        const widgetHandle = new WidgetHandle({
            id: widgetId,
            createOpts: opts,
            callbacks,
            registered: registered.promise,
        });
        this.widgets.set(widgetId, widgetHandle);
        const widgetUrl = origin + widgetEndpoint;
        const wel = createWidgetIFrame(agentId, widgetId, widgetUrl, opts, this.guardContext);
        const maxAttempts = MAX_IFRAME_LOAD_ATTEMPTS;
        const initialSrc = wel.src;
        let currentOrigin = origin;
        const widgetPlaceholder = createWidgetPlaceholder(opts);
        setWidgetRootStyles(opts.element);
        createBanner(opts);
        let language = getLanguageFromOptionsOrParent(opts);
        if (isRTLLanguage(language)) {
            opts.element.dir = "rtl";
        }
        const widgetPlaceholderStyle = widgetPlaceholder.style;
        widgetPlaceholder.textContent = getLocalizedText(language, "connecting");
        function setUnreachableState(detail) {
            const debugString = encodeStringToBase64Url(JSON.stringify({
                sdk_v: SDK_VERSION,
                sitekey: opts.sitekey || "",
                retry: attempt + "",
                endpoint: currentOrigin,
                ua: navigator.userAgent,
                tz: tz() || "",
            }));
            let resp = ".ERROR.UNREACHABLE";
            if (debugString) {
                resp += "~" + debugString;
            }
            widgetHandle.setState({
                state: "error",
                response: resp,
                error: { code: "network_error", detail },
            });
        }
        const registerWithRetry = () => {
            this.bus.registerTargetIFrame("widget", widgetId, wel, this.getRetryTimeout(attempt)).then((status) => {
                // Retrying a widget that was destroyed while its iframe was still loading is pointless.
                if (widgetHandle.isDestroyed)
                    return;
                if (status === "timeout") {
                    if (attempt >= maxAttempts) {
                        console.error(`[Friendly Captcha] Failed to load widget iframe after ${attempt - 1} retries.`);
                        setUnreachableState("Widget load timeout, stopped retrying");
                        widgetPlaceholderStyle.borderColor = "#f00";
                        widgetPlaceholderStyle.fontSize = "12px";
                        createFallback(widgetPlaceholder, originOf(wel.src), language);
                        return;
                    }
                    const nextAttempt = attempt + 1;
                    const nextIndex = getRetryOriginIndex(nextAttempt, retryOrigins);
                    currentOrigin = retryOrigins[nextIndex] || currentOrigin;
                    widgetPlaceholderStyle.backgroundColor = "#fee";
                    widgetPlaceholderStyle.color = "#222";
                    widgetPlaceholder.textContent = getLocalizedText(language, "retrying") + ` (${attempt})`;
                    console.warn(`[Friendly Captcha] Retrying widget ${widgetId} iframe load.`);
                    setUnreachableState("Widget load timeout, will retry");
                    wel.src = getRetrySrc(initialSrc, currentOrigin, nextAttempt - 1);
                    attempt = nextAttempt;
                    registerWithRetry();
                }
                else if (status === "registered") {
                    // After successful registration, we remove the placeholder and show the widget.
                    opts.element.removeChild(widgetPlaceholder);
                    wel.style.display = "";
                }
            });
        };
        registerWithRetry();
        registered.resolve();
        return widgetHandle;
    }
    /**
     * Creates a Risk Intelligence token generation request, returning a Promise that resolves
     * to the generated token.
     *
     * @public
     */
    riskIntelligence(opts) {
        const origins = resolveAPIOrigins(opts.apiEndpoint || this.apiEndpoint || getSDKAPIEndpoint());
        const retryOrigins = this.getRetryOrigins(origins);
        this.bus.addOrigins(origins);
        const agentId = this.ensureAgentIFrame(retryOrigins);
        const uid = randomId(8);
        this.bus.send({
            type: "root_risk_intelligence_generate",
            to_id: agentId,
            from_id: "",
            _frc: 1,
            sitekey: opts.sitekey,
            bypassCache: opts.bypassCache || false,
            uid,
        });
        const riskIntelligencePromise = flatPromise();
        this.riskIntelligencePromises.set(uid, riskIntelligencePromise);
        return riskIntelligencePromise.promise;
    }
    /**
     * Clears cached Risk Intelligence tokens. Cached tokens for a given sitekey can be cleared
     * by specifying it; if a sitekey is not specified, all tokens will be cleared from the cache.
     *
     * @public
     */
    clearRiskIntelligence(opts) {
        const origins = resolveAPIOrigins((opts === null || opts === void 0 ? void 0 : opts.apiEndpoint) || this.apiEndpoint || getSDKAPIEndpoint());
        const retryOrigins = this.getRetryOrigins(origins);
        this.bus.addOrigins(origins);
        const agentId = this.ensureAgentIFrame(retryOrigins);
        const uid = randomId(8);
        this.bus.send({
            type: "root_risk_intelligence_clear",
            to_id: agentId,
            from_id: "",
            _frc: 1,
            sitekey: opts === null || opts === void 0 ? void 0 : opts.sitekey,
            uid,
        });
        const clearRiskIntelligencePromise = flatPromise();
        this.clearRiskIntelligencePromises.set(uid, clearRiskIntelligencePromise);
        return clearRiskIntelligencePromise.promise;
    }
    /**
     * Returns all current widgets known about (in an unspecified order).
     * @public
     */
    getAllWidgets() {
        // We use a workaround for old browser support. We can not count on spread operator or `Array.from` support.
        const out = [];
        this.widgets.forEach((w) => {
            out.push(w);
        });
        return out;
    }
    /**
     * Retrieves a widget by its widget ID.
     * @public
     */
    getWidgetById(id) {
        return this.widgets.get(id);
    }
    /**
     * Returns all current Risk Intelligence handles known about (in an unspecified order).
     * @public
     */
    getAllRiskIntelligenceHandles() {
        const out = [];
        this.riskIntelligenceHandles.forEach((rih) => {
            out.push(rih);
        });
        return out;
    }
    /**
     * Completely remove all widgets and background agents related to the SDK on this page.
     * @public
     */
    clear() {
        this.widgets.forEach((w) => {
            w.destroy();
        });
        this.agents.forEach((el) => {
            el.remove();
        });
        this.agents.clear();
    }
}
//# sourceMappingURL=sdk.js.map