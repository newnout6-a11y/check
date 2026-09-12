import { MouseMoveSignal, RootSignalsV1Raw, TouchMoveSignal } from "../types/signals";
export interface SignalsOptions {
    disableEvalPatching?: boolean;
}
/**
 * Signals collects browser and user behavior data from the page where the widget is embedded.
 * The code is deliberately rather minimal to save on payload size.
 *
 * An important design consideration is that the signals should not be able to be used to identify a user or what the user entered on the page.
 * @internal
 */
export declare class Signals {
    /**
     * Last mousemove event
     */
    private mm?;
    /** Last touch event */
    private tm?;
    /** Distinct touch event radius count */
    private rn;
    private bh;
    private dep;
    /** Counter */
    private i;
    private smel;
    private takeTraceRecords;
    constructor(opts: SignalsOptions);
    private setupMovementMetrics;
    /**
     * @internal
     */
    private setupMotionMetrics;
    /**
     * @internal
     */
    private setupOrientationMetrics;
    /**
     * @internal
     */
    gmm(): MouseMoveSignal | undefined;
    /**
     * @internal
     */
    gtm(): TouchMoveSignal | undefined;
    /**
     * @internal
     */
    get(widgetId: string): RootSignalsV1Raw;
}
/**
 * Returns the global signals object.
 * @internal
 */
export declare function getSignals(opts: SignalsOptions): Signals;
//# sourceMappingURL=collect.d.ts.map