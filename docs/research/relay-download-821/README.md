# NetworkMonitor download accounting trial for #821

Signed NetworkMonitor 1.35.0 beta 5 (364.5), macOS 26.7.3 (25G342), Content Filter active. The five files touched by the diagnostic patch are unchanged between beta 5 and the beta 8 release base.

## Findings

- **UDP attribution still has a gap.** With `relayDownloadAccounting` and `flowBytesProbe` on, a short YouTube playback in a fresh Safari private window produced two closed WebKit UDP/443 flows with **9,015,817 B** and **5,391,644 B** received. A TCP/443 WebKit flow reported **6,189,883 B**. During the observation window, the interface received **23,838,617 B** including background traffic. The Safari history row grew **6,298,521 B**. Safari received **0 B** of new `filter_downloads` inputs and **0 B** of additional `download_credit` after the flush. One network visit and one hour covered the complete playback window. Private Relay was enabled. We did not establish the route of each individual UDP flow in this playback run.
- **Direct control adds no duplicate credit.** A 2 MB direct control left Safari's extra credit at zero. The longer direct run with accounting enabled added **200,363,761 B** to Safari's filter input and **200,380,042 B** to its ordinary usage. Extra credit remained **0 B**. The hour containing both 200 MB runs recorded **401,764,749 B** of Safari receive traffic in both the CSV and SQLite. This is a whole-hour figure including background traffic. The positive redistribution and whole-day total invariant during actual redistribution remain to be exercised on a Relay run that earns credit.
- **Matched CPU control on the direct path.** With `flowBytesProbe` off, the same destination, same egress and HTTP/1.1 over TCP, Safari fetched 50 × 4,000,000 B every two seconds in both modes. The filter used **0.06 s** with accounting on and **0.12 s** with it off, over **100.000 s** and **100.001 s** respectively. The same filter process was sampled in both windows. No increase was observed in this pair. A separate smaller pair yielded **0.05 s on** and **0.03 s off** at 64 MB in 64 s. These are direct TCP controls. They do not estimate the cost of a successful UDP Relay credit or the outbound callback experiment from #816.

## Earlier checks and why the comparisons changed

The earlier small relayed controls and repeat used TCP/443 and the ordinary Safari row already saw approximately the payload. In an earlier 200 MB comparison, the enabled run used TCP/443 and the disabled run used UDP/443. On the latter run the filter reported **200,298,299 B** but the Safari row increased by only **55,045 B**. The diagnostic probe was on in both runs and the transfers took **253.470 s** and **11.752 s** respectively. Those CPU observations (**0.13 s** and **0.01 s**) cannot isolate accounting overhead. The YouTube run above supplied the missing UDP observation with accounting enabled. Its diagnostic does not show which stage rejected the bytes.

## Reproduce

1. With the Content Filter on, enable `relayDownloadAccounting` and `flowBytesProbe`, then restart NetworkMonitor. Under Private Relay, play a short YouTube segment in a fresh Safari private window and close just that test window. Allow about one minute for the history flush. Compare WebKit's UDP close reports, Safari's Usage History/CSV delta, and the `filter_downloads` and `download_credit` deltas for that app and hour. Those diagnostic inputs isolate the symptom even if background traffic contributes to the interface total.
2. For CPU, turn **off** `flowBytesProbe` for both modes and restart after changing the accounting flag. Use the same direct route in separate Safari private windows on `https://speed.cloudflare.com/robots.txt`. For this test only, use the site's temporary **Reload and Show IP Address** exception. Run [the workload](safari-cpu.js) in Web Inspector using the same fresh local salt both times. Check identical response sizes, egress and protocol and no missed cadence. Each run transfers 200 MB. Close the test windows to clear the temporary exception.
3. Sample the same extension PID with `ps -o time= -p <filter-pid>` while recording local epoch milliseconds. Use the closest samples to the JavaScript start and end and subtract cumulative CPU time. The JSON preserves the sample alignment offsets. An external aggregation should omit the route fingerprints and raw timestamps.

## Artifacts

- [Receive and history deltas](receive-evidence.json)
- [Anonymized CSV aggregates](history-aggregate.csv). The UDP rows come from the export directly after that trial. The CPU rows are from the final export for the tested day. Only the named rows and aggregate totals are retained.
- [200 MB CPU pair](large-matched-cpu-results.json) and [64 MB CPU pair](matched-cpu-results.json)
- [Safari workload](safari-cpu.js)
- [Prior Relay and outbound investigation](../private-relay-799/evidence.md). Apple Feedback ID: **FB25755493**.
