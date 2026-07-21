"""Parse an Android Bluetooth HCI snoop log into a readable ATT event timeline.

GATT writes/notifications with their handle and value bytes, in order, with
relative timestamps. Useful for reverse-engineering a device's real
protocol from a capture of the vendor's own app talking to it (the same
technique used to originally discover F2000Alt's protocol - see the
"Capture methodology" section of docs/source/f2000_hardware_variant.rst),
or for verifying this library's own command bytes against a fresh
real-app capture.

Getting a capture (on the phone controlling the device):
    1. Turn Bluetooth off.
    2. Settings -> Developer options -> Bluetooth HCI snoop log -> Full
       (not "Filtered"/default "Enabled" - those redact most of the
       payload data this script needs, keeping only headers and a few
       leading bytes).
    3. Turn Bluetooth back on (the new logging mode only takes effect on
       the next Bluetooth stack start).
    4. Open the vendor app, connect, and perform the actions you want to
       capture.
    5. Settings -> Developer options -> Bug report -> Full report. Do this
       soon after step 4 - the snoop log is a rolling buffer and other
       Bluetooth activity (or too much delay) can push your capture out.
    6. Unzip the bug report and find
       FS/data/misc/bluetooth/logs/btsnooz_hci.log (despite the "z" in the
       filename, this is a standard binary btsnoop-format file, not the
       separate base64/zlib "btsnooz" compact format - it opens directly
       with this script or with Wireshark).

Usage:
    python examples/parse_hci_snoop.py path/to/btsnooz_hci.log
"""

import argparse
import struct
from collections import Counter

BTSNOOP_MAGIC = b"btsnoop\x00"
# Microseconds between the btsnoop epoch (0000-01-01) and the Unix epoch
# (1970-01-01), per the btsnoop file format spec.
BTSNOOP_EPOCH_OFFSET = 0x00E03AB44A676000

ATT_OPCODES = {
    0x0A: "Read Request",
    0x0B: "Read Response",
    0x12: "Write Request",
    0x13: "Write Response",
    0x52: "Write Command",
    0x1B: "Handle Value Notification",
    0x1D: "Handle Value Indication",
}
# Opcodes that carry a 2-byte attribute handle immediately after the opcode.
ATT_OPCODES_WITH_HANDLE = {0x0A, 0x0B, 0x12, 0x13, 0x52, 0x1B, 0x1D}

ATT_CID = 0x0004


def parse_btsnoop(path: str) -> list[tuple[int, int, bytes]]:
    """Parse a btsnoop file into (unix_micros, flags, h4_payload) tuples."""
    with open(path, "rb") as f:
        data = f.read()

    if data[0:8] != BTSNOOP_MAGIC:
        raise ValueError(
            f"Not a btsnoop file (magic was {data[0:8]!r}, expected "
            f"{BTSNOOP_MAGIC!r}). If this came from an Android bug report, "
            "note the file may be named 'btsnooz_hci.log' but still contain "
            "plain btsnoop-format data.",
        )
    version, datalink = struct.unpack(">II", data[8:16])
    if datalink != 1002:
        print(f"warning: unexpected datalink type {datalink} (expected 1002, H4 UART)")

    offset = 16
    packets = []
    truncated = 0
    while offset + 24 <= len(data):
        orig_len, incl_len, flags, drops, ts = struct.unpack(
            ">IIIIq", data[offset : offset + 24]
        )
        offset += 24
        payload = data[offset : offset + incl_len]
        offset += incl_len
        if orig_len != incl_len:
            truncated += 1
        packets.append((ts - BTSNOOP_EPOCH_OFFSET, flags, payload))

    if truncated:
        pct = 100 * truncated / len(packets) if packets else 0
        print(
            f"warning: {truncated}/{len(packets)} packets ({pct:.0f}%) are truncated "
            "(captured length < original length). If ATT/GATT values below look cut "
            "short, the phone's HCI snoop log was likely set to 'Filtered' rather than "
            "'Full' - see this script's docstring for how to fix that and recapture.",
        )
    return packets


def extract_att_events(
    packets: list[tuple[int, int, bytes]],
) -> list[tuple[int, str, str, int, bytes]]:
    """Reassemble ACL/L2CAP fragments and extract ATT write/notify events.

    Returns a list of (unix_micros, direction_label, opcode_name, att_handle,
    value_bytes) tuples, in capture order.
    """
    # Reassembly state per (connection_handle, direction):
    # [expected_len, cid, buffer, start_ts]
    buffers: dict[tuple[int, int], list] = {}
    events = []

    for unix_micros, flags, payload in packets:
        if not payload or payload[0] != 0x02:  # H4 ACL Data
            continue
        if len(payload) < 5:
            continue
        handle_flags, data_len = struct.unpack("<HH", payload[1:5])
        conn_handle = handle_flags & 0x0FFF
        pb_flag = (handle_flags >> 12) & 0x3
        # direction: 0 = host->controller (sent), 1 = controller->host (recv)
        direction = flags & 0x01
        acl_data = payload[5 : 5 + data_len]
        key = (conn_handle, direction)

        if pb_flag in (0b10, 0b00):  # start of a new L2CAP message
            if len(acl_data) < 4:
                continue
            l2cap_len, cid = struct.unpack("<HH", acl_data[0:4])
            buffers[key] = [l2cap_len, cid, bytearray(acl_data[4:]), unix_micros]
        elif pb_flag == 0b01:  # continuation fragment
            if key not in buffers:
                continue
            buffers[key][2].extend(acl_data)
        else:
            continue

        entry = buffers.get(key)
        if entry is None:
            continue
        expected_len, cid, buf, start_ts = entry
        if len(buf) < expected_len:
            continue  # still waiting on more fragments

        l2cap_payload = bytes(buf[:expected_len])
        del buffers[key]
        if cid != ATT_CID or not l2cap_payload:
            continue

        opcode = l2cap_payload[0]
        if opcode not in ATT_OPCODES or opcode not in ATT_OPCODES_WITH_HANDLE:
            continue
        if len(l2cap_payload) < 3:
            continue
        att_handle = struct.unpack("<H", l2cap_payload[1:3])[0]
        value = l2cap_payload[3:]
        dir_label = "host->ctrl (sent)" if direction == 0 else "ctrl->host (recv)"
        events.append((start_ts, dir_label, ATT_OPCODES[opcode], att_handle, value))

    return events


def main() -> None:
    """Parse the log given on the command line and print the ATT timeline."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("log_path", help="Path to a btsnoop/btsnooz_hci.log file")
    args = parser.parse_args()

    packets = parse_btsnoop(args.log_path)
    print(f"total HCI packets: {len(packets)}")
    types = Counter(p[2][0] if p[2] else None for p in packets)
    print(f"H4 type counts (1=Command, 2=ACL Data, 3=SCO, 4=Event): {dict(types)}")

    events = extract_att_events(packets)
    print(f"\ntotal ATT write/notify events: {len(events)}")
    if not events:
        return

    t0 = events[0][0]
    header = (
        f"\n{'t':>9}  {'direction':<20} {'opcode':<26} {'handle':<8} {'len':>4}  value"
    )
    print(header)
    for unix_micros, direction, opname, handle, value in events:
        t = (unix_micros - t0) / 1_000_000
        row = (
            f"{t:>8.3f}s  {direction:<20} {opname:<26} 0x{handle:04x}   "
            f"{len(value):>4}  {value.hex()}"
        )
        print(row)


if __name__ == "__main__":
    main()
