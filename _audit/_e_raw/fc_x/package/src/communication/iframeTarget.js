import { originOf } from "../util/url";
/**
 * @internal
 */
export class IFrameCommunicationTarget {
    constructor(opts) {
        /**
         * We have received a message from this target at any point
         */
        this.ready = false;
        /**
         * Messages that couldn't be delivered yet as the target isn't ready to receive messages.
         */
        this.buffer = [];
        this.id = opts.id;
        this.type = opts.type;
        this.element = opts.element;
        this.onReady = opts.onReady;
        this.origin = originOf(opts.element.src);
    }
    send(msg) {
        if (this.ready) {
            this.element.contentWindow.postMessage(msg, this.origin);
        }
        else {
            this.buffer.push(msg);
        }
    }
    setReady(ready) {
        this.onReady();
        this.ready = ready;
        if (this.ready) {
            this.flush();
        }
    }
    flush() {
        for (let i = 0; i < this.buffer.length; i++) {
            this.element.contentWindow.postMessage(this.buffer[i], this.origin);
        }
        this.buffer = [];
    }
}
//# sourceMappingURL=iframeTarget.js.map