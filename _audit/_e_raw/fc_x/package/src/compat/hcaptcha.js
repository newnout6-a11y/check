import { CommonCompatSDK } from "./common";
/**
 * FriendlyCaptchaHCaptchaCompatSDK wraps the FriendlyCaptchaSDK to provide a compatibility layer for hCaptcha.
 *
 * @public
 */
export class FriendlyCaptchaHCaptchaCompatSDK extends CommonCompatSDK {
    constructor(sdk) {
        super(sdk);
    }
    /**
     * Does not do anything in Friendly Captcha, always returns an empty string for compatibility.
     * @public
     */
    getRespKey(widgetId) {
        return "";
    }
}
//# sourceMappingURL=hcaptcha.js.map