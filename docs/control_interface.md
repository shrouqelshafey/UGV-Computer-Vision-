# Vision → control ESP32: Wi-Fi integration draft

Status: proposed interface for a bench test. No messages have been sent and no motor firmware has been changed.

## 1. Connection

The user selected Wi-Fi for the laptop-to-control-ESP32 connection.

Proposed first implementation: the control ESP32 runs a TCP server; Python on the laptop connects as a TCP client. Both devices join the same local network. Internet access is not required, but the network must allow devices to communicate.

Use port **5000** as a proposed project setting; both programs must use the same port. Obtain the control ESP32's actual IP from its firmware/Serial Monitor. The camera's IP is a separate address and must not be used as the motor controller's address.

```text
ESP32-CAM → Wi-Fi video → laptop / Python
                              ↓ Wi-Fi / TCP / JSON
                       motor-control ESP32
                              ↑
                       ultrasonic sensor
```

## 2. Message format

Send one UTF-8 JSON object per line, ending with `\n`.

| Field | Meaning |
| --- | --- |
| `seq` | Integer that increases for each message within one connection. Resets are allowed on a new connection. |
| `confirmed` | `true` only when the detector has confirmed a target. |
| `color` | Confirmed color name, or `null` when there is no confirmed target. |
| `x_error` | Normalized horizontal image position between -1 and +1; `null` when there is no confirmed target. |

Confirmed target on the left:

```json
{"seq":1,"confirmed":true,"color":"red","x_error":-0.32}
```

No confirmed target, including searching, stabilizing or camera read failure:

```json
{"seq":2,"confirmed":false,"color":null,"x_error":null}
```

Each example must have a newline after its closing brace when transmitted. TCP is a byte stream: one read can contain part of a message or several messages. The receiver must collect bytes and process complete newline-terminated messages.

## 3. Responsibilities

Vision reports the flag's color and image position. Negative `x_error` means image-left, positive means image-right, and near zero means image-center. Verify that the installed camera orientation and motor directions agree during the bench test.

Control decides steering, speed, centering tolerance and lost-target behavior. It uses the ultrasonic sensor for approaching and holding **50 cm**. Flag area is not a distance measurement because the physical flag size is unknown.

The current Python code displays `x_error`; it does not transmit these messages yet.

The separate `communication/lcd_announcer.py` feature prints confirmed colors and optionally sends `FLAG_DETECTED,COLOR` lines over USB Serial. Serial output is disabled by default. Those event messages are not this proposed Wi-Fi JSON stream and must not be used as a continuous motor-control signal. No LCD receiver firmware is included.

## 4. Missing or invalid data

- On `confirmed: false`, clear the previous target immediately. `null` is not a centered target; do not convert it to zero.
- On a disconnected socket, malformed/invalid message or expired receive watchdog, invalidate the target. Do not keep steering from the last confirmed value.
- The control team implements an independent watchdog and a motor response for lost vision. A stopped state is proposed for the initial bench integration; agree the competition behavior with the team.
- Choose the watchdog duration after measuring the actual update interval. Camera opening/reading uses backend defaults with no application-configured timeout and can block, so the controller must detect silence independently without waiting for Python to report a camera failure.
- Reset target state and sequence tracking on a new connection. Reject repeated or decreasing sequence numbers within the same connection.
- Sequence numbers indicate message order, not camera exposure time. They do not prove that a frame is fresh; buffered/stale-frame detection still needs work.

## 5. First test, step by step

1. Review the control team's existing Arduino sketch before adding networking, so its current motor/sensor behavior is preserved.
2. Add a TCP receiver that prints incoming complete lines to Serial Monitor. Keep motors disabled for this test.
3. Connect Python to the control ESP32's IP and agreed port. First send fixed left, center, right and invalid examples, without using the camera.
4. Check that Serial Monitor receives each message and that closing the sender invalidates the target through the watchdog.
5. Connect the real detector to the sender. Check real flag positions, target removal, camera failure and Wi-Fi loss.
6. Integrate steering and ultrasonic distance control only after the message and loss-handling tests pass.

Still needed: the control team's current ESP32 sketch, actual controller IP, agreement on port and watchdog, and organizer confirmation that external laptop processing is allowed during the competition. Wi-Fi connectivity alone does not establish that permission.
