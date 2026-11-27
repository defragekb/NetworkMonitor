(async () => {
    if (location.origin !== "https://speed.cloudflare.com") {
        throw new Error("Run this in the console of https://speed.cloudflare.com/robots.txt");
    }
    const localSalt = "replace-with-a-fresh-local-salt-for-the-four-runs";
    const request = async (path) => {
        const url = new URL(path, location.origin);
        url.searchParams.set("nm", crypto.randomUUID());
        const response = await fetch(url);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response;
    };
    const egress = async () => {
        const trace = await (await request("/cdn-cgi/trace")).text();
        const ip = /^ip=(.+)$/m.exec(trace)?.[1];
        if (!ip) throw new Error("Trace did not report an egress address");
        const material = new TextEncoder().encode(localSalt + ip);
        const hash = await crypto.subtle.digest("SHA-256", material);
        return Array.from(new Uint8Array(hash), n => n.toString(16).padStart(2, "0")).join("").slice(0, 16);
    };
    const started = Date.now();
    const before = await egress();
    const bytes = [];
    for (let i = 0; i < 2; i++) {
        const response = await request("/__down?bytes=1000000");
        bytes.push((await response.arrayBuffer()).byteLength);
    }
    const after = await egress();
    console.log({bytes, started, finished: Date.now(), egressBefore: before, egressAfter: after});
})();
