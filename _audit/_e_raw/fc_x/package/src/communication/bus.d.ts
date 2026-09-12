/*!
 * Copyright (c) Friendly Captcha GmbH 2023.
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/.
 */
import { Message as ToRootMessage, EnvelopedMessage } from "../types/messages.js";
import { CommunicationTarget, CommunicationTargetType } from "./target.js";
/**
 * Cross-iframe communication bus that runs on the root website, it handles communication
 * between the root page, and the agent and widgets.
 * @internal
 */
export declare class CommunicationBus {
    /**
     * Messages sent from this set of origins will be considered, all others are ignored.
     * Perhaps the website this code runs on has more cross-origin message passing happening, we don't want to interfere.
     */
    origins: Set<string>;
    targets: Record<string, CommunicationTarget>;
    /** Some messages that expect an answer may be handled twice if two SDKs are present. Here we keep track of those and deliver them only once. */
    answered: Set<string>;
    /**
     * Called upon receiving a message intended for consumption by the root itself, which is the host page
     * that contains the widgets and agent iframes.
     */
    onReceiveRootMessage: (msg: EnvelopedMessage<ToRootMessage>) => void;
    constructor();
    /**
     * Adds a listener for root messages.
     * @internal
     */
    listen(onReceiveRootMessage: (msg: EnvelopedMessage<ToRootMessage>) => void): void;
    /**
     * Add origins to allow messages from.
     * @internal
     */
    addOrigins(origins: string[]): void;
    /**
     * Send from the local root
     * @param msg
     * @internal
     */
    send(msg: EnvelopedMessage<ToRootMessage>): void;
    private onReceive;
    /**
     * @param ct
     * @internal
     */
    registerTarget(ct: CommunicationTarget): void;
    /**
     * @internal
     */
    registerTargetIFrame(type: CommunicationTargetType, id: string, iframe: HTMLIFrameElement, timeout: number): Promise<"registered" | "timeout">;
    /**
     * @internal
     */
    removeTarget(id: string): void;
}
//# sourceMappingURL=bus.d.ts.map