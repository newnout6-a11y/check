/**
 * resolveAPIOrigin resolves the value of the API origin to use for the SDK.
 * If no value is specified, it defaults to the "global" shorthand. The "eu" and "global" shorthands are expanded to multiple endpoints for redundancy. Custom URLs are used as-is.
 * @param optionValue The value of the API origin to use for the SDK.
 * @returns A list of API origins to use for the SDK, with shorthands expanded.
 */
export declare function resolveAPIOrigins(optionValue: string | undefined): string[];
export declare function getSDKDisableEvalPatching(): boolean;
export declare function getSDKGuardContext(): string | undefined;
export declare function getSDKAPIEndpoint(): string | undefined;
//# sourceMappingURL=options.d.ts.map