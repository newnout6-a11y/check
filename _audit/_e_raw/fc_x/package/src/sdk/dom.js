export function findFRCElements() {
    const captchaElements = document.querySelectorAll(".frc-captcha");
    const riskIntelligenceElements = document.querySelectorAll(".frc-risk-intelligence");
    return [captchaElements, riskIntelligenceElements];
}
/**
 * Traverses parent nodes until a <form> is found, returns null if not found.
 */
export function findParentFormElement(element) {
    let current = element;
    while (current) {
        if (current.tagName === "FORM") {
            return current;
        }
        if (current.parentElement) {
            current = current.parentElement;
            continue;
        }
        const parentNode = current.parentNode;
        if (parentNode && parentNode.host) {
            current = parentNode.host;
            continue;
        }
        current = null;
    }
    return null;
}
/**
 * Add listener to specified element that will only fire once on focus.
 */
export function executeOnceOnFocusInEvent(element, listener) {
    element.addEventListener("focusin", listener, { once: true, passive: true });
}
export function createManagedInputElement(parentElement, formFieldName) {
    const iel = document.createElement("input");
    iel.type = "hidden";
    iel.style.display = "none";
    iel.name = formFieldName;
    // Note: we must use `appendChild` instead of `append` for IE11.
    parentElement.appendChild(iel);
    return iel;
}
/**
 * Sets the style of an element if it is not already set. This is useful for allowing users to override styles.
 * @internal
 */
export function styleIfNotAlreadySet(el, name, value) {
    if (el.style[name] === "") {
        el.style[name] = value;
    }
}
/**
 * @internal
 */
export function setWidgetRootStyles(el) {
    const sinas = styleIfNotAlreadySet;
    sinas(el, "position", "relative");
    sinas(el, "height", "70px");
    sinas(el, "padding", "0");
    sinas(el, "width", "316px");
    sinas(el, "maxWidth", "100%");
    sinas(el, "maxHeight", "100%");
    sinas(el, "overflow", "hidden");
    sinas(el, "borderRadius", "4px");
}
/**
 * @internal
 */
export function removeWidgetRootStyles(el) {
    el.removeAttribute("style");
}
export function runOnDocumentLoaded(func) {
    if (document.readyState !== "loading") {
        func();
    }
    else {
        document.addEventListener("DOMContentLoaded", func);
    }
}
/**
 * Creates a DOM event for given element with given data in a way that works for ancient browsers.
 * @param element Element that should emit the event.
 * @param eventData Payload for the event.
 * @internal
 */
export function fireFRCEvent(element, eventData) {
    let event;
    if (typeof window.CustomEvent === "function") {
        event = new CustomEvent(eventData.name, {
            bubbles: true,
            detail: eventData,
        });
    }
    else {
        // Fallback for IE11 and other very old browsers
        event = document.createEvent("CustomEvent");
        event.initCustomEvent(eventData.name, true, false, eventData);
    }
    element.dispatchEvent(event);
}
/**
 * Traverses parent nodes until an element with the `lang` attribute set is found and returns its value, returns null if not found.
 */
export function findFirstParentLangAttribute(element) {
    while (!element.lang || typeof element.lang !== "string") {
        element = element.parentElement;
        if (!element) {
            return null;
        }
    }
    return element.lang;
}
//# sourceMappingURL=dom.js.map