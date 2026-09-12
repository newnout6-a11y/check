import { createManagedInputElement, executeOnceOnFocusInEvent, findParentFormElement, fireFRCEvent } from "./dom";
const DEFAULT_FORM_FIELD_NAME = "frc-risk-intelligence-token";
/**
 * This provides a handle for configuring and managing a Risk Intelligence request
 * via an HTML element.
 *
 * This class is only instantiated by the SDK - do not create a handle yourself.
 *
 * @public
 */
export class RiskIntelligenceHandle {
    /**
     * This class is only instantiated by the SDK by calling FriendlyCaptchaSDK.attach()
     * Do not create a handle manually.
     *
     * @internal
     */
    constructor(opts) {
        /**
         * A timeout ID used for firing an expiration event when this handle's
         * token expires.
         */
        this.timeout = null;
        this.data = null;
        this.e = opts.element;
        if (!this.e)
            throw new Error("No element provided for mounting Risk Intelligence handle.");
        this.e.frcRiskIntelligence = this;
        this.formFieldName = opts.formFieldName === undefined ? DEFAULT_FORM_FIELD_NAME : opts.formFieldName;
        if (this.formFieldName !== null) {
            this.hiddenFormEl = createManagedInputElement(this.e, this.formFieldName);
        }
        this.startMode = opts.startMode || "focus";
        this.requestRiskIntelligence = opts.riskIntelligence;
        this.handleStartMode();
    }
    handleStartMode() {
        if (this.startMode === "none") {
            console.warn('Risk Intelligence <div> found with data-start="none" (no-op), skipping...', this.e);
        }
        else if (this.startMode === "auto") {
            this.request();
        }
        else {
            const parentForm = findParentFormElement(this.e);
            if (!parentForm) {
                console.warn('Risk Intelligence <div> with startMode of "focus" found without a parent <form> element, skipping...', this.e);
            }
            else {
                executeOnceOnFocusInEvent(parentForm, () => {
                    this.request();
                });
            }
        }
    }
    request() {
        this.requestRiskIntelligence()
            .then((data) => {
            if (this.timeout !== null) {
                clearTimeout(this.timeout);
            }
            this.timeout = setTimeout(() => {
                fireFRCEvent(this.e, {
                    name: "frc:riskintelligence.expire",
                });
            }, data.expiresAt - Date.now());
            this.data = {
                token: data.token,
                expiresAt: data.expiresAt,
            };
            if (this.hiddenFormEl) {
                this.hiddenFormEl.value = data.token;
            }
            fireFRCEvent(this.e, {
                name: "frc:riskintelligence.complete",
                token: data.token,
                expiresAt: data.expiresAt,
            });
        })
            .catch((error) => {
            fireFRCEvent(this.e, {
                name: "frc:riskintelligence.error",
                error: {
                    code: error.code,
                    detail: error.detail,
                },
            });
        });
    }
    /**
     * @returns Risk Intelligence data if request is done and `null` if not.
     */
    getData() {
        return this.data;
    }
    /**
     * @returns The HTML element used to configure the Risk Intelligence request.
     */
    getElement() {
        return this.e;
    }
    /**
     * Shorthand for `this.getElement().addEventListener`  (that is strictly typed in Typescript)
     */
    addEventListener(type, listener, options) {
        this.e.addEventListener(type, listener, options);
    }
    /**
     * Shorthand for `this.getElement().removeEventListener` (that is strictly typed in Typescript)
     */
    removeEventListener(type, listener, options) {
        this.e.removeEventListener(type, listener, options);
    }
}
//# sourceMappingURL=riskIntelligenceHandle.js.map