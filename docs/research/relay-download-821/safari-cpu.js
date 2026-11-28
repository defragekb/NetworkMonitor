// Safari Web Inspector console on https://speed.cloudflare.com/robots.txt.
// Reuse the salt between runs. For the second run, paste the first run's
// route fingerprint locally so a route change aborts before the payload.
(async () => {
    const label = 'accounting-on';
    const salt = 'replace-with-a-local-random-salt';
    const expectedRoute = '';
    const requests = 50;
    const size = 4_000_000;
    const intervalMs = 2_000;
    if (location.origin !== 'https://speed.cloudflare.com' || salt.startsWith('replace-')) {
        throw new Error('Use the test origin and set a fresh local salt');
    }

    const fingerprint = async (value) => {
        const material = new TextEncoder().encode(salt + value);
        const hash = await crypto.subtle.digest('SHA-256', material);
        return Array.from(new Uint8Array(hash).slice(0, 8), n => n.toString(16).padStart(2, '0')).join('');
    };
    const request = async (path) => {
        const url = new URL(path, location.origin);
        url.searchParams.set('nm', crypto.randomUUID());
        const response = await fetch(url, {cache: 'no-store', credentials: 'omit'});
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return {url, response};
    };
    const route = async () => {
        const {response} = await request('/cdn-cgi/trace');
        const address = /^ip=(.+)$/m.exec(await response.text())?.[1];
        if (!address) throw new Error('Missing route fingerprint');
        return fingerprint(address);
    };
    const waitUntil = deadline => new Promise(resolve => setTimeout(resolve, Math.max(0, deadline - Date.now())));

    const before = await route();
    if (expectedRoute && before !== expectedRoute) throw new Error('Route differs from the first run');
    const start = Date.now();
    const durations = [];
    const paths = new Set();
    const protocols = new Set();
    let bytes = 0;
    for (let index = 0; index < requests; index++) {
        await waitUntil(start + index * intervalMs);
        const requestStart = Date.now();
        const {url, response} = await request(`/__down?bytes=${size}`);
        const received = (await response.arrayBuffer()).byteLength;
        if (received !== size) throw new Error(`Unexpected response size ${received}`);
        bytes += received;
        durations.push(Date.now() - requestStart);
        const protocol = performance.getEntriesByName(url.href).at(-1)?.nextHopProtocol;
        if (protocol) protocols.add(protocol);
        const address = response.headers.get('cf-meta-ip');
        if (address) paths.add(await fingerprint(address));
    }
    await waitUntil(start + requests * intervalMs);
    const end = Date.now();
    const after = await route();
    durations.sort((a, b) => a - b);
    // Fingerprints and timestamps are local checks. Publish only the derived comparisons and deltas.
    console.log({label, bytes, start, end, before, after, paths: [...paths], protocols: [...protocols],
        medianMs: durations[Math.floor(durations.length / 2)], maxMs: Math.max(...durations),
        late: durations.filter(n => n >= intervalMs).length});
})().catch(error => console.error(error.message));
