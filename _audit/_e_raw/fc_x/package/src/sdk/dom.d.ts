/*!
 * Copyright (c) Friendly Captcha GmbH 2023.
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/.
 */
import type { FRCEventData } from "./events";
export declare function findFRCElements(): NodeListOf<Element>[];
/**
 * Traverses parent nodes until a <form> is found, returns null if not found.
 */
export declare function findParentFormElement(element: HTMLElement): HTMLFormElement | null;
/**
 * Add listener to specified element that will only fire once on focus.
 */
export declare function executeOnceOnFocusInEvent(element: HTMLElement, listener: (this: HTMLElement, fe: FocusEvent) => any): void;
export declare function createManagedInputElement(parentElement: HTMLElement, formFieldName: string): HTMLInputElement;
/**
 * Sets the style of an element if it is not already set. This is useful for allowing users to override styles.
 * @internal
 */
export declare function styleIfNotAlreadySet(el: HTMLElement, name: Exclude<keyof CSSStyleDeclaration, "length" | "parentRule">, value: string): void;
/**
 * @internal
 */
export declare function setWidgetRootStyles(el: HTMLElement): void;
/**
 * @internal
 */
export declare function removeWidgetRootStyles(el: HTMLElement): void;
export declare function runOnDocumentLoaded(func: () => any): void;
/**
 * Creates a DOM event for given element with given data in a way that works for ancient browsers.
 * @param element Element that should emit the event.
 * @param eventData Payload for the event.
 * @internal
 */
export declare function fireFRCEvent(element: HTMLElement, eventData: FRCEventData): void;
/**
 * Traverses parent nodes until an element with the `lang` attribute set is found and returns its value, returns null if not found.
 */
export declare function findFirstParentLangAttribute(element: HTMLElement): string | null;
//# sourceMappingURL=dom.d.ts.map