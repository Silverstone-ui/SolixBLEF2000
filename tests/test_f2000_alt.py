"""Tests for the F2000Alt (767 PowerHouse alt-protocol) device.

Covers the control-command byte wiring (AC/DC output, power saving mode,
light bar mode), and regression tests for power_out/ac_output_power - both
were re-pointed after a live-hardware session found offset 17-18 (the
previous power_out location) doesn't track real output power, while offset
41 (AC + light bar) and offset 21 (AC only) do, confirmed against the
unit's own screen. See docs/source/f2000_hardware_variant.rst for the full
writeup.
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
    ac_power: int = 65, combined_power: int = 68, legacy_power_out: int = 12345
) -> bytes:
    """Build a base telemetry frame with recognizable, distinct probe values.

    :param ac_power: Value at offset 21 (single byte) - AC-only output
        power, read by :attr:`F2000Alt.ac_output_power`.
    :param combined_power: Value at offset 41 (single byte) - AC + light bar
        combined output power, read by :attr:`F2000Alt.power_out`. Kept
        distinct from ``ac_power`` so the two properties can't accidentally
        pass by reading the same byte.
    :param legacy_power_out: Value at offset 17-18 (LE16) - the field
        power_out used to read before a live-hardware test found it doesn't
        track real output power. Kept large and outside single-byte range
        so a regression back to reading it would be caught.
    """
    frame = bytearray(_TELEMETRY_LENGTH)
    frame[17:19] = legacy_power_out.to_bytes(2, "little")
    frame[21] = ac_power
    frame[41] = combined_power
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
    """power_out (AC + light bar combined) must read offset 41, not 17-18."""
    async with MockDevice() as mock_bluetooth:
        device = await _connected_device(
            mock_bluetooth,
            _telemetry_frame(ac_power=65, combined_power=68, legacy_power_out=12345),
        )
        assert device.power_out == 68


@pytest.mark.asyncio
async def test_ac_output_power_reads_offset_21():
    """ac_output_power (AC only) must read offset 21, distinct from power_out."""
    async with MockDevice() as mock_bluetooth:
        device = await _connected_device(
            mock_bluetooth,
            _telemetry_frame(ac_power=65, combined_power=68, legacy_power_out=12345),
        )
        assert device.ac_output_power == 65
        assert device.ac_output_power != device.power_out


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
