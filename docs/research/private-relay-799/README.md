# Reproduce Private Relay and outbound UDP measurements

This accompanies [NetworkMonitor #799](https://github.com/kevinabouhanna/NetworkMonitor/issues/799). The [signed Safari probe runs](https://github.com/kevinabouhanna/NetworkMonitor/issues/799#issuecomment-7203512579), [controlled downloads](https://github.com/kevinabouhanna/NetworkMonitor/issues/799#issuecomment-7219703646) and [external UDP and QUIC matrix](https://github.com/kevinabouhanna/NetworkMonitor/issues/799#issuecomment-7207173291) contain the measured results. The test scripts below accept your own endpoints and use generic receiver and sender roles.

Start with the [evidence and implementation map](evidence.md) for the investigation in order, the published captures and the one-command replay.

## Received bytes in Safari

1. Enable NetworkMonitor's Content Filter. Use a signed build with `flowBytesProbe` for measurement, or the [receive accounting branch](https://github.com/defragekb/NetworkMonitor/tree/relay-download-799) to try Usage History.
2. In Safari, open [the HTTPS test page](https://speed.cloudflare.com/robots.txt) and use the JavaScript Console to run `safari-download.js`. Set a fresh local salt in the script and reuse it for all four runs. The page retrieves two uncached 1,000,000-byte HTTPS responses. It keeps the payload in memory and reports the exact size.
3. Compare the server's egress fingerprints locally before and after the transfer. For the direct control, choose **View → Reload and Show IP Address** in the test window. Use a fresh connection for each run. Keep the payload and request count fixed.
4. Measure with the diagnostic or implementation switch off and on, with Relay active and on the direct control. Restart NetworkMonitor after changing a switch. Use `nettop` in both modes and compare the Content Filter process CPU time from `ps -o time= -p <pid>` over equal windows. Keep only the deltas and allow time for a periodic report after the download.

```sh
defaults write com.kevinabouhanna.NetworkMonitor flowBytesProbe -bool true
nettop -n -x -d -L 20 -s 1 -t external -J time,interface,bytes_in,bytes_out
nettop -n -x -d -L 20 -s 1 -J time,interface,bytes_in,bytes_out
/usr/bin/log show --last 10m --info --predicate 'subsystem == "com.kevinabouhanna.NetworkMonitor.Filter" AND category == "flow-bytes"'
```

Run the two `nettop` commands concurrently and discard their initial cumulative snapshots. For each target flow subtract the pre-download report from the final count. In the signed beta run the filter saw 2,008,998 incoming bytes via Relay while `nettop` saw zero during the download. On the direct control the filter and `nettop` both saw 2,008,809 bytes after the pre-download baseline.

For the receive implementation, use `relayDownloadAccounting` and compare the per-app Usage History and CSV with the switch off and on. During the direct control the app's totals should still count each byte once.

## Outbound counter on one IPv4 route

The smallest reproduction uses ordinary UDP in Apple's Network.framework. This exercises the same counter discrepancy observed with Network.framework QUIC. The original matrix also includes BSD UDP and OpenSSL QUIC as controls.

Compile the Network.framework sender on macOS. Run the receiver on a controlled endpoint with UDP/443 available. Address and token values below are placeholders. Pick a fresh token with `openssl rand -hex 16`. The receiver accepts 32 packets of the specified length from the specified source and replies only to matching packets. Start a new receiver for each size.

```sh
swiftc udp-sender.swift -o udp-sender
```

On the receiver, where `CLIENT_IPV4` is the sender's IPv4 address as seen by the receiver:

```sh
sudo python3 udp-receiver.py CLIENT_IPV4 443 128 TOKEN_HEX
```

On the sender, where `RECEIVER_IPV4` is the receiver's address:

```sh
./udp-sender RECEIVER_IPV4 443 128 TOKEN_HEX
```

Repeat both commands with 1,024 bytes per packet (pass `1024` on the command line). Both the sender and receiver should print totals of 4,096 and 32,768 bytes respectively. In the reproduced signed beta the old filter counter reported 64,640 bytes for each flow.

For the [outbound diagnostic patch](https://github.com/defragekb/NetworkMonitor/commit/dffe619bbdde9394bc172d77846f025e7e0ad80d), build and sign the app, enable `flowOutboundBytesProbe` and restart it. Then compare its `flow-outbound-bytes` totals and stop reasons with the receiver. Compare CPU time and throughput with the diagnostic off and on. Repeat on QUIC, including Safari with Relay, to verify end-to-end coverage there. Keep probes off outside the measurement window.
