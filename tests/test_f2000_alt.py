"""Tests for the F2000Alt (767 PowerHouse alt-protocol) device.

Covers the control-command byte wiring (AC/DC output, power saving mode,
light bar mode), and regression tests for power_out/ac_output_power - both
were re-pointed after a live-hardware session found offset 17-18 (the
previous power_out location) doesn't track real output power, while offset
41-42 (AC + light bar) and offset 21-22 (AC only) do, confirmed against the
unit's own screen. Both were originally read as single bytes; a third-party
report (independently-built library plus direct hardware confirmation)
identified them as 16-bit LE fields, silently wrong above 255W. See
docs/source/f2000_hardware_variant.rst for the full writeup.
"""

from unittest import mock

import pytest

from SolixBLE import F2000Alt, LightStatus
from SolixBLE.devices.f2000_alt import CMD_POLL_TELEMETRY
from tests.const import MOCK_BLE_DEVICE
from tests.helpers import MockDevice

#: Minimum length required by F2000Alt._on_notify to treat a notification as
#: a real telemetry frame rather than a heartbeat/ack.
_TELEMETRY_LENGTH = 102


def _telemetry_frame(
    ac_power: int = 300, combined_power: int = 400, legacy_power_out: int = 12345
) -> bytes:
    """Build a base telemetry frame with recognizable, distinct probe values.

    :param ac_power: Value at offset 21-22 (LE16) - AC-only output power,
        read by :attr:`F2000Alt.ac_output_power`. Defaults above 255 to
        prove the field is genuinely read as 16-bit, not truncated to a
        single byte (a real bug this project shipped and a third-party
        library/report caught - see the offset 21/41 note in
        f2000_alt.py's power_out docstring).
    :param combined_power: Value at offset 41-42 (LE16) - AC + light bar
        combined output power, read by :attr:`F2000Alt.power_out`. Kept
        distinct from ``ac_power`` so the two properties can't accidentally
        pass by reading the same bytes, and also defaults above 255.
    :param legacy_power_out: Value at offset 17-18 (LE16) - the field
        power_out used to read before a live-hardware test found it doesn't
        track real output power. Kept large and distinct from the other two
        so a regression back to reading it would be caught.
    """
    frame = bytearray(_TELEMETRY_LENGTH)
    frame[17:19] = legacy_power_out.to_bytes(2, "little")
    frame[21:23] = ac_power.to_bytes(2, "little")
    frame[41:43] = combined_power.to_bytes(2, "little")
    return bytes(frame)


def _extended_frame(power_saving: int = 1, length: int = 122) -> bytes:
    """Build an extended (settings-block) frame with a probe value at offset 117.

    :param power_saving: Value to place at offset 117 - the power-saving-mode
        readback confirmed by a live two-cycle ON/OFF test, read by
        :attr:`F2000Alt.power_saving_mode_enabled`.
    :param length: Frame length; must be >= 120 to be treated as an extended
        frame by F2000Alt._on_notify.
    """
    frame = bytearray(length)
    frame[117] = power_saving
    return bytes(frame)


async def _connected_device(
    mock_bluetooth: MockDevice, telemetry: bytes | None = None
) -> F2000Alt:
    """Connect a fresh F2000Alt against the mock, consuming the poll handshake.

    F2000Alt.connect() is a full override (see its class docstring) that
    imports establish_connection directly into the f2000_alt module rather
    than going through SolixBLE.device, so MockDevice's own patch target
    doesn't intercept it. Patch that second import location too, reusing
    MockDevice's already-started client-creation side effect so both patches
    drive the same tracked mock client.
    """
    mock_bluetooth.expect_ordered(
        CMD_POLL_TELEMETRY, response=[telemetry if telemetry is not None else _telemetry_frame()]
    )
    device = F2000Alt(MOCK_BLE_DEVICE)
    with mock.patch(
        "SolixBLE.devices.f2000_alt.establish_connection",
        side_effect=mock_bluetooth._establish.side_effect,
    ):
        assert await device.connect(), "Expected connect to return True"
    mock_bluetooth.check_assertions()
    return device


@pytest.mark.asyncio
async def test_power_out_reads_offset_41_not_17_18():
    """power_out (AC + light bar combined) must read offset 41-42, not 17-18."""
    async with MockDevice() as mock_bluetooth:
        device = await _connected_device(
            mock_bluetooth,
            _telemetry_frame(ac_power=300, combined_power=400, legacy_power_out=12345),
        )
        assert device.power_out == 400


@pytest.mark.asyncio
async def test_ac_output_power_reads_offset_21():
    """ac_output_power (AC only) must read offset 21-22, distinct from power_out."""
    async with MockDevice() as mock_bluetooth:
        device = await _connected_device(
            mock_bluetooth,
            _telemetry_frame(ac_power=300, combined_power=400, legacy_power_out=12345),
        )
        assert device.ac_output_power == 300
        assert device.ac_output_power != device.power_out


@pytest.mark.asyncio
async def test_ac_output_power_and_power_out_are_16_bit_not_truncated():
    """Regression test: these fields must not silently wrap/truncate above 255W.

    Both were originally implemented as single-byte reads. A third-party
    owner's independently-built library documented offset 21-22 as a 16-bit
    field, and directly confirmed on their own hardware that values above
    255W were being misread - see the note on F2000Alt.power_out. A
    single-byte read of a value like 300 would either raise (bytearray
    assignment rejects values > 255) or silently produce a wrong, wrapped
    result depending on how it was truncated - this test locks in that a
    real value clearly above 255 round-trips exactly.
    """
    async with MockDevice() as mock_bluetooth:
        device = await _connected_device(
            mock_bluetooth,
            _telemetry_frame(ac_power=65535, combined_power=65534, legacy_power_out=1),
        )
        assert device.ac_output_power == 65535
        assert device.power_out == 65534


@pytest.mark.asyncio
async def test_port_and_misc_power_fields_are_16_bit_not_truncated():
    """Regression test: per-port and misc power fields must not truncate above 255W.

    usb_c1/c2/c3_power and usb_a1/a2_power were originally read as single
    bytes - the same bug class as ac_output_power/power_out (see module
    docstring), discovered this session by cross-referencing a third-party
    library's field map rather than a live report, and fixed alongside it.
    dc1/dc2_power, solar_power_in, and power_in are new fields added at the
    same time from the same source, not yet confirmed against live
    hardware. All are 16-bit LE at their respective offsets; the battery
    fields (external/total percentage, external temperature) are single
    bytes as documented.
    """
    frame = bytearray(_TELEMETRY_LENGTH)
    frame[23:25] = (1001).to_bytes(2, "little")  # usb_c1_power
    frame[25:27] = (1002).to_bytes(2, "little")  # usb_c2_power
    frame[27:29] = (1003).to_bytes(2, "little")  # usb_c3_power
    frame[29:31] = (1004).to_bytes(2, "little")  # usb_a1_power
    frame[31:33] = (1005).to_bytes(2, "little")  # usb_a2_power
    frame[33:35] = (1006).to_bytes(2, "little")  # dc1_power
    frame[35:37] = (1007).to_bytes(2, "little")  # dc2_power
    frame[37:39] = (1008).to_bytes(2, "little")  # solar_power_in
    frame[39:41] = (1009).to_bytes(2, "little")  # power_in
    frame[67] = 45  # external_battery_temperature
    frame[71] = 55  # external_battery_percentage
    frame[72] = 66  # total_battery_percentage

    async with MockDevice() as mock_bluetooth:
        device = await _connected_device(mock_bluetooth, bytes(frame))
        assert device.usb_c1_power == 1001
        assert device.usb_c2_power == 1002
        assert device.usb_c3_power == 1003
        assert device.usb_a1_power == 1004
        assert device.usb_a2_power == 1005
        assert device.dc1_power == 1006
        assert device.dc2_power == 1007
        assert device.solar_power_in == 1008
        assert device.power_in == 1009
        assert device.external_battery_temperature == 45
        assert device.external_battery_percentage == 55
        assert device.total_battery_percentage == 66


@pytest.mark.asyncio
async def test_time_remaining_reads_offset_17_and_18_as_separate_bytes():
    """Regression test: time_remaining must read two single bytes, not a 16-bit pair.

    Previously read offset 57-58 as a 16-bit LE value, which was found
    completely frozen across wildly different live conditions in one
    session, while the unit's own screen moved a lot. An independent
    third-party implementation (a separate open-source HA integration for
    this exact device) reads offset 17 as hours (value/10, single byte) and
    offset 18 as whole days (single byte) instead - not the same offsets as
    a combined LE16 pair, which is a different, still-unidentified field
    (see legacy_power_out in _telemetry_frame's docstring). The exact raw
    byte 0xa5 (165) below is taken directly from a live capture this
    session that paired with the unit's own screen reading 16.5 hours at
    that exact moment - an exact match, not an approximation.
    """
    frame = bytearray(_TELEMETRY_LENGTH)
    frame[17] = 0xA5  # 165 -> 16.5 hours, matches a live-captured screen reading
    frame[18] = 0  # 0 days

    async with MockDevice() as mock_bluetooth:
        device = await _connected_device(mock_bluetooth, bytes(frame))
        assert device.time_remaining == 16.5
        assert device.hours_remaining == 16.5
        assert device.days_remaining == 0


@pytest.mark.asyncio
async def test_time_remaining_includes_days():
    """time_remaining must fold whole days (offset 18) into the total hours."""
    frame = bytearray(_TELEMETRY_LENGTH)
    frame[17] = 100  # 10.0 hours
    frame[18] = 3  # 3 days

    async with MockDevice() as mock_bluetooth:
        device = await _connected_device(mock_bluetooth, bytes(frame))
        assert device.time_remaining == 82.0  # 3 * 24 + 10.0
        assert device.hours_remaining == 10.0
        assert device.days_remaining == 3


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "raw_value,expected",
    [
        pytest.param(0, False, id="off"),
        pytest.param(1, True, id="on"),
    ],
)
async def test_power_saving_mode_enabled_reads_offset_117(raw_value: int, expected: bool):
    """power_saving_mode_enabled must read offset 117 in the extended frame."""
    async with MockDevice() as mock_bluetooth:
        device = await _connected_device(mock_bluetooth)

        mock_bluetooth.expect_ordered(
            CMD_POLL_TELEMETRY, response=[_extended_frame(power_saving=raw_value)]
        )
        await device.get_status_update()
        mock_bluetooth.check_assertions()

        assert device.power_saving_mode_enabled is expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method_name,expected_hex",
    [
        # Command format: 08ee000000 02 <field_id> 0b00 <value> <checksum>,
        # checksum = sum(preceding bytes) mod 256. Field IDs/values below
        # match those confirmed against real hardware (F2000ALT_ROADMAP.md).
        pytest.param("turn_ac_on", "08ee00000002860b00018a", id="ac_on"),
        pytest.param("turn_ac_off", "08ee00000002860b000089", id="ac_off"),
        pytest.param("turn_dc_on", "08ee00000002870b00018b", id="dc_on"),
        pytest.param("turn_dc_off", "08ee00000002870b00008a", id="dc_off"),
        pytest.param(
            "turn_power_saving_mode_on", "08ee000000028a0b00018e", id="power_saving_on"
        ),
        pytest.param(
            "turn_power_saving_mode_off", "08ee000000028a0b00008d", id="power_saving_off"
        ),
    ],
)
async def test_control_command_bytes(method_name: str, expected_hex: str):
    """Each no-arg control method must send the exact documented command bytes."""
    async with MockDevice() as mock_bluetooth:
        device = await _connected_device(mock_bluetooth)

        mock_bluetooth.expect_ordered(bytes.fromhex(expected_hex), response=[])
        await getattr(device, method_name)()
        mock_bluetooth.check_assertions()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mode,expected_hex",
    [
        pytest.param(LightStatus.OFF, "08ee000000028b0b00008e", id="off"),
        pytest.param(LightStatus.LOW, "08ee000000028b0b00018f", id="low"),
        pytest.param(LightStatus.MEDIUM, "08ee000000028b0b000290", id="medium"),
        pytest.param(LightStatus.HIGH, "08ee000000028b0b000391", id="high"),
        pytest.param(LightStatus.SOS, "08ee000000028b0b000492", id="sos"),
    ],
)
async def test_set_light_mode_command_bytes(mode: LightStatus, expected_hex: str):
    """set_light_mode must send the exact command bytes for each mode."""
    async with MockDevice() as mock_bluetooth:
        device = await _connected_device(mock_bluetooth)

        mock_bluetooth.expect_ordered(bytes.fromhex(expected_hex), response=[])
        await device.set_light_mode(mode)
        mock_bluetooth.check_assertions()


@pytest.mark.asyncio
async def test_set_light_mode_rejects_unknown():
    """set_light_mode must reject LightStatus.UNKNOWN without sending a command."""
    async with MockDevice() as mock_bluetooth:
        device = await _connected_device(mock_bluetooth)

        with pytest.raises(ValueError):
            await device.set_light_mode(LightStatus.UNKNOWN)

        # No control command should have been sent - only the connect
        # handshake write is expected/consumed.
        mock_bluetooth.check_assertions()


@pytest.mark.asyncio
async def test_control_method_requires_connection():
    """Control methods must raise ConnectionError if not connected."""
    device = F2000Alt(MOCK_BLE_DEVICE)
    with pytest.raises(ConnectionError):
        await device.turn_ac_on()
