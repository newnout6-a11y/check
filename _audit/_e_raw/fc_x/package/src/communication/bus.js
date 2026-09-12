import { flatPromise } from "../util/flatPromise.js";
import { IFrameCommunicationTarget } from "./iframeTarget.js";
function isAllowedOrigin(origin, allowedOrigins) {
    return origin === "*" || allowedOrigins.has(origin);
}
/**
 * Cross-iframe communication bus that runs on the root website, it handles communication
 * between the root page, and the agent and widgets.
 * @internal
 */
export class CommunicationBus {
    constructor() {
        /**
         * Messages sent from this set of origins will be considered, all others are ignored.
         * Perhaps the website this code runs on has more cross-origin message passing happening, we don't want to interfere.
         */
        this.origins = new Set();
        // We use a Record here to prevent the need to add a Map polyfill in the widget.
        this.targets = {};
        /** Some messages that expect an answer may be handled twice if two SDKs are present. Here we keep track of those and deliver them only once. */
        this.answered = new Set();
        /**
         * Called upon receiving a message intended for consumption by the root itself, which is the host page
         * that contains the widgets and agent iframes.
         */
        this.onReceiveRootMessage = () => { };
        window.addEventListener("message", (ev) => {
            // console.debug("[FRC bus]", ev.data);
            this.onReceive(ev);
        });
    }
    /**
     * Adds a listener for root messages.
     * @internal
     */
    listen(onReceiveRootMessage) {
        let orig = this.onReceiveRootMessage;
        this.onReceiveRootMessage = (msg) => {
            orig(msg);
            onReceiveRootMessage(msg);
        };
    }
    /**
     * Add origins to allow messages from.
     * @internal
     */
    addOrigins(origins) {
        origins.forEach((origin) => this.origins.add(origin));
    }
    /**
     * Send from the local root
     * @param msg
     * @internal
     */
    send(msg) {
        if (msg.from_id) {
            const messageSender = this.targets[msg.from_id];
            if (!messageSender) {
                console.error(`[bus] Unexpected message from unknown sender ${msg.from_id}`, msg);
                return;
            }
            // The first message sent from the iframes are announcement messages.
            // When we first receive an announcement we can mark them as ready to receive messages.
            // In other words: the iframe source loaded fully and JS is executing.
            if (msg.type === "widget_announce" || msg.type === "agent_announce") {
                messageSender.setReady(true);
            }
        }
        // This message expects an answer, it has a "return id"
        // Some messages may be answered twice by different SDKs (such as "get root signals"), here we
        // make sure we drop any duplicate answers to the same target
        const rid = msg.rid;
        if (rid) {
            if (this.answered.has(rid + msg.to_id)) {
                // We already answered this message, ignore it.
                return;
            }
            this.answered.add(rid + msg.to_id);
        }
        if (msg.to_id === "") {
            this.onReceiveRootMessage(msg);
            return;
        }
        const messageTarget = this.targets[msg.to_id];
        if (!messageTarget) {
            console.error(`[bus] Unexpected message to unknown target ${msg.to_id}`, msg);
            return;
        }
        messageTarget.send(msg);
    }
    onReceive(ev) {
        if (!isAllowedOrigin(ev.origin, this.origins)) {
            // This may be an attempt at abuse or it's simply another iframe sending messages.
            // We silently ignore the message. For dev purposes we can print a debug message.
            // console.debug("Friendly Captcha communication bus ignored message from origin " + ev.origin, this.origins);
            return;
        }
        const msg = ev.data;
        if (!msg || !msg._frc)
            return; // Message unrelated to Friendly Captcha.
        this.send(msg);
    }
    /**
     * @param ct
     * @internal
     */
    registerTarget(ct) {
        this.targets[ct.id] = ct;
    }
    /**
     * @internal
     */
    registerTargetIFrame(type, id, iframe, timeout) {
        const fp = flatPromise();
        // Create a promise that resolves to `"timeout"` after some time.
        let timeoutHandle;
        let timeoutPromise = new Promise((resolve) => {
            timeoutHandle = setTimeout(() => resolve("timeout"), timeout);
        });
        const t = new IFrameCommunicationTarget({
            id: id,
            element: iframe,
            type: type,
            onReady: () => {
                // Without this the timer outlives a successful registration by up to its full duration.
                clearTimeout(timeoutHandle);
                fp.resolve("registered");
            },
        });
        this.registerTarget(t);
        return Promise.race([fp.promise, timeoutPromise]);
    }
    /**
     * @internal
     */
    removeTarget(id) {
        delete this.targets[id];
    }
}
//# sourceMappingURL=bus.js.map