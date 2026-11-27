import Dispatch
import Foundation
import Network

let arguments = CommandLine.arguments
guard arguments.count == 5, let destination = IPv4Address(arguments[1]),
      let port = NWEndpoint.Port(arguments[2]), port.rawValue > 0, let size = Int(arguments[3]), [128, 1024].contains(size),
      arguments[4].count == 32 else {
    fputs("usage: udp-sender VPS_IPV4 PORT {128|1024} TOKEN_HEX\n", stderr)
    exit(2)
}

let hex = Array(arguments[4])
let parsed = stride(from: 0, to: hex.count, by: 2).compactMap { index in
    UInt8(String(hex[index...index + 1]), radix: 16)
}
guard parsed.count == 16 else {
    fputs("TOKEN_HEX must be 16 bytes in hex\n", stderr)
    exit(2)
}

let token = Data(parsed)
let payload = token + Data(repeating: 0, count: size - token.count)
let ack = Data("ok".utf8) + token
let connection = NWConnection(host: .ipv4(destination), port: port, using: .udp)
let queue = DispatchQueue(label: "udp-counter-control")

func sendRemaining(_ remaining: Int) {
    guard remaining > 0 else {
        print("32 datagrams, \(32 * size) bytes confirmed")
        connection.cancel()
        exit(0)
    }
    connection.send(content: payload, completion: .contentProcessed { error in
        guard error == nil else { exit(1) }
        connection.receiveMessage { data, _, _, error in
            guard error == nil, data == ack else { exit(1) }
            sendRemaining(remaining - 1)
        }
    })
}

connection.stateUpdateHandler = { state in
    switch state {
    case .ready:
        sendRemaining(32)
    case .failed(let error):
        fputs("\(error)\n", stderr)
        exit(1)
    default:
        break
    }
}
connection.start(queue: queue)
queue.asyncAfter(deadline: .now() + 20) {
    fputs("timed out while waiting for the receiver\n", stderr)
    exit(1)
}
dispatchMain()
