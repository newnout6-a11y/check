import { windowPerformanceNow } from "../util/performance";
/**
 * @internal
 */
export function getTrigger(type, startMode, el, ev) {
    const t = windowPerformanceNow();
    const bcr = el.getBoundingClientRect();
    const trigger = {
        v: 1,
        tt: type,
        pnow: t,
        sm: startMode,
        el: {
            bcr: [bcr.left, bcr.top, bcr.width, bcr.height],
            con: document.body.contains(el),
        },
        stack: new Error().stack || "",
        we: !!window.event,
        weit: !!window.event && !!window.event.isTrusted,
    };
    if (ev) {
        trigger.ev = {
            ts: ev.timeStamp,
            rt: !!ev.relatedTarget,
            // @ts-ignore: not present in every browser
            eot: !!ev.explicitOriginalTarget,
            it: ev.isTrusted,
        };
    }
    // We save some code with this type conversion instead of constructing the different types independently.
    return trigger;
}
//# sourceMappingURL=trigger.js.map