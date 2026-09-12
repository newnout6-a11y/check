/*!
 * Copyright (c) Friendly Captcha GmbH 2023.
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/.
 */
import { EnvelopedMessage, Message } from "../types/messages";
import { CommunicationTarget, CommunicationTargetType } from "./target";
/**
 * @internal
 */
export declare class IFrameCommunicationTarget implements CommunicationTarget {
    id: string;
    type: CommunicationTargetType;
    /**
     * If null the element has not been created yet, perhaps it's time to do so?
     */
    element: HTMLIFrameElement | null;
    origin: string;
    /**
     * We have received a message from this target at any point
     */
    ready: boolean;
    /**
     * Messages that couldn't be delivered yet as the target isn't ready to receive messages.
     */
    buffer: EnvelopedMessage<Message>[];
    onReady: () => void;
    constructor(opts: {
        id: string;
        element: HTMLIFrameElement;
        type: CommunicationTargetType;
        onReady: () => void;
    });
    send(msg: EnvelopedMessage<Message>): void;
    setReady(ready: boolean): void;
    private flush;
}
//# sourceMappingURL=iframeTarget.d.ts.map