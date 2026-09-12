/**
 * @internal
 */
export function buildOnlineMetric() {
    const s = [0, 0, 0, 0, 0, 0, 0];
    return {
        s,
        add(x) {
            const n = ++s[0];
            const d = x - s[1];
            const dN = d / n;
            const dN2 = dN * dN;
            const t1 = d * dN * (n - 1);
            s[1] += dN;
            s[4] += t1 * dN2 * (n * n - 3 * n + 3) + 6 * dN2 * s[2] - 4 * dN * s[3];
            s[3] += t1 * dN * (n - 2) - 3 * dN * s[2];
            s[2] += t1;
            if (n == 1) {
                s[5] = s[6] = x;
            }
            else {
                if (x < s[5])
                    s[5] = x;
                if (x > s[6])
                    s[6] = x;
            }
        },
    };
}
//# sourceMappingURL=online.js.map