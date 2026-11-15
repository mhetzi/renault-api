"""CLI function for a vehicle."""

import re
from typing import Any
from typing import cast

import aiohttp
import click
from tabulate import tabulate

from renault_api.cli import helpers
from renault_api.cli import renault_vehicle
from renault_api.kamereon.helpers import DAYS_OF_WEEK
from renault_api.kamereon.helpers import get_end_time
from renault_api.kamereon.models import ChargeDaySchedule
from renault_api.kamereon.models import ChargeSchedule
from renault_api.kamereon.models import KamereonVehicleChargingSettingsData
from renault_api.kamereon.models import KcmEvProgram
from renault_api.kamereon.schemas import KamereonVehicleChargingSettingsDataSchema
from renault_api.renault_vehicle import RenaultVehicle

_DAY_SCHEDULE_REGEX = re.compile(
    "(?P<prefix>T?)"
    "(?P<hours>[0-2][0-9])"
    ":"
    "(?P<minutes>[0-5][0-9])"
    "(?P<suffix>Z?)"
    ","
    "(?P<duration>[0-9]+)"
)
_HOURS_PER_DAY = 24


@click.group()
def schedule() -> None:
    """Display or update charge schedules."""
    pass


@schedule.command()
@click.pass_obj
@helpers.coro_with_websession
async def show(
    ctx_data: dict[str, Any],
    *,
    websession: aiohttp.ClientSession,
) -> None:
    """Display charge schedules."""
    vehicle = await renault_vehicle.get_vehicle(
        websession=websession, ctx_data=ctx_data
    )
    endpoint_definition = await vehicle.get_endpoint_definition("charge-schedule")
    response = await vehicle.get_charge_schedule()
    if endpoint_definition.mode == "kcm-settings":
        _show_kcm_settings(response)
    else:  # default
        _show_kca(response)


def _show_kca(response: dict[str, Any]) -> None:
    """Display charge schedules (basic)."""
    calendar = response["calendar"]
    schedule_table: list[list[str]] = []
    for day in DAYS_OF_WEEK:
        day_data = calendar[day][0]
        start_time = day_data["startTime"]
        end_time = get_end_time(
            f"T{start_time[0:2]}:{start_time[2:4]}Z", day_data["duration"]
        )
        schedule_table.append(
            [
                day.capitalize(),
                helpers.get_display_value(
                    f"T{start_time[0:2]}:{start_time[2:4]}Z", "tztime"
                ),
                helpers.get_display_value(end_time, "tztime"),
                day_data["duration"],
                day_data["activationState"],
            ]
        )

    headers = ["Day", "Start time", "End time", "Duration", "Active"]
    click.echo(tabulate(schedule_table, headers=headers))


def _show_kcm_settings(response: dict[str, Any]) -> None:
    """Display charge schedules (alternate)."""
    click.echo(f"Mode: {response['chargeModeRq'].capitalize()}")
    click.echo(f"Charge Time Start: {response['chargeTimeStart']}")
    click.echo(f"Charge Duration in minutes: {response['chargeDuration']}")
    click.echo(
        f"Preconditioning temperature in °C: {response['preconditioningTemperature']}"
    )
    click.echo(
        f"Preconditioning Steering Wheel? {response['preconditioningHeatedStrgWheel']}"
    )
    click.echo(
        f"Preconditioning Left Seat? {response['preconditioningHeatedLeftSeat']}"
    )
    click.echo(
        f"Preconditioning Right Seat? {response['preconditioningHeatedRightSeat']}"
    )
    if not response["programs"]:
        click.echo("\nNo schedules found.")
        return

    for idx, program in enumerate(response["programs"]):
        active = (
            " [Status=Active]"
            if program["programActivationStatus"]
            else " [Status=Inactive]"
        )
        type = " [Type=" + program["programType"] + "]"
        departure_time = (
            " [DepartureTime=" + program.get("programDepartureTime", "N/A") + "]"
        )

        click.echo(f"\nSchedule ID: {idx}{active}{type}{departure_time}")

        headers = ["Day", "Active"]
        click.echo(
            tabulate(
                [
                    [key.capitalize(), program[f"programActivation{key.capitalize()}"]]
                    for key in DAYS_OF_WEEK
                ],
                headers=headers,
            )
        )


async def _get_schedule(
    ctx_data: dict[str, Any],
    websession: aiohttp.ClientSession,
    id: int,
    vehicle: RenaultVehicle | None = None,
) -> tuple[RenaultVehicle, list[ChargeSchedule], ChargeSchedule]:
    """Get the given schedules activated-flag to given state."""
    if vehicle is None:
        vehicle = await renault_vehicle.get_vehicle(
            websession=websession, ctx_data=ctx_data
        )
    response_data = await vehicle._get_vehicle_data("charging-settings")
    response = cast(
        KamereonVehicleChargingSettingsData,
        response_data.get_attributes(KamereonVehicleChargingSettingsDataSchema),
    )

    if not response.schedules:
        raise ValueError("No schedules found.")

    schedule = next(
        (schedule for schedule in response.schedules if id == schedule.id), None
    )
    if schedule:
        return (vehicle, response.schedules, schedule)

    raise IndexError(f"Schedule id {id} not found.")


@schedule.command()
@click.argument("id", type=int)
@helpers.days_of_week_option(
    helptext="{} schedule in format `hh:mm,duration` (for local timezone) "
    "or `Thh:mmZ,duration` (for utc) or `clear` to unset."
)
@click.option("--departure-time", help="KCM departure time in HH:MM format.")
@click.option(
    "--day",
    "kcm_days",
    multiple=True,
    type=click.Choice(DAYS_OF_WEEK),
    help="KCM weekday to activate (repeat for multiple days).",
)
@click.option("--clear-days", is_flag=True, help="Clear all KCM active weekdays.")
@click.option(
    "--program-type",
    type=click.Choice(["CHARGE", "PRECONDITIONING", "CHARGE_AND_PRECONDITIONING"]),
    help="KCM program type; defaults to the current type for the selected slot.",
)
@click.option("--active/--inactive", default=None, help="Set KCM program activation.")
@click.pass_obj
@helpers.coro_with_websession
async def set(
    ctx_data: dict[str, Any],
    *,
    id: int,
    websession: aiohttp.ClientSession,
    departure_time: str | None,
    kcm_days: tuple[str, ...],
    clear_days: bool,
    program_type: str | None,
    active: bool | None,
    **kwargs: Any,
) -> None:
    """Update charging schedule {ID}."""
    vehicle = await renault_vehicle.get_vehicle(
        websession=websession, ctx_data=ctx_data
    )
    endpoint_definition = (await vehicle.get_details()).get_endpoint("charge-schedule")
    if endpoint_definition is not None and endpoint_definition.mode == "kcm-settings":
        if any(value is not None for value in kwargs.values()):
            raise click.UsageError(
                "For KCM schedules use --departure-time, --day and --clear-days."
            )
        settings = await vehicle.get_ev_settings()
        programs = _parse_kcm_programs(settings)
        program = _get_kcm_program(programs, id)
        if departure_time is not None:
            program.departure_time = departure_time
        if kcm_days or clear_days:
            program.days = [] if clear_days else list(kcm_days)
        if program_type is not None:
            program.program_type = program_type
        if active is not None:
            program.active = active
        response = await vehicle.set_ev_programs(programs)
        click.echo(response.raw_data)
        return

    if (
        departure_time is not None
        or kcm_days
        or clear_days
        or program_type
        or active is not None
    ):
        raise click.UsageError(
            "KCM options are only available for KCM schedule vehicles."
        )

    vehicle, schedules, schedule = await _get_schedule(
        websession=websession, ctx_data=ctx_data, id=id, vehicle=vehicle
    )
    update_settings(schedule, **kwargs)

    write_response = await vehicle.set_charge_schedules(schedules)
    click.echo(write_response.raw_data)


@schedule.command()
@click.argument("id", type=int)
@click.pass_obj
@helpers.coro_with_websession
async def activate(
    ctx_data: dict[str, Any],
    *,
    id: int,
    websession: aiohttp.ClientSession,
) -> None:
    """Activate charging schedule {ID}."""
    vehicle = await renault_vehicle.get_vehicle(
        websession=websession, ctx_data=ctx_data
    )
    endpoint_definition = (await vehicle.get_details()).get_endpoint("charge-schedule")
    if endpoint_definition is not None and endpoint_definition.mode == "kcm-settings":
        programs = _parse_kcm_programs(await vehicle.get_ev_settings())
        _get_kcm_program(programs, id).active = True
        response = await vehicle.set_ev_programs(programs)
        click.echo(response.raw_data)
        return

    vehicle, schedules, schedule = await _get_schedule(
        ctx_data, websession, id, vehicle=vehicle
    )

    schedule.activated = True

    write_response = await vehicle.set_charge_schedules(schedules)
    click.echo(write_response.raw_data)


@schedule.command()
@click.argument("id", type=int)
@click.pass_obj
@helpers.coro_with_websession
async def deactivate(
    ctx_data: dict[str, Any],
    *,
    id: int,
    websession: aiohttp.ClientSession,
) -> None:
    """Deactivate charging schedule {ID}."""
    vehicle = await renault_vehicle.get_vehicle(
        websession=websession, ctx_data=ctx_data
    )
    endpoint_definition = (await vehicle.get_details()).get_endpoint("charge-schedule")
    if endpoint_definition is not None and endpoint_definition.mode == "kcm-settings":
        programs = _parse_kcm_programs(await vehicle.get_ev_settings())
        _get_kcm_program(programs, id).active = False
        response = await vehicle.set_ev_programs(programs)
        click.echo(response.raw_data)
        return

    vehicle, schedules, schedule = await _get_schedule(
        ctx_data, websession, id, vehicle=vehicle
    )

    schedule.activated = False

    write_response = await vehicle.set_charge_schedules(schedules)
    click.echo(write_response.raw_data)


def _parse_kcm_programs(settings: dict[str, Any]) -> list[KcmEvProgram]:
    programs = settings.get("programs")
    if not isinstance(programs, list) or not all(
        isinstance(program, dict) for program in programs
    ):
        raise ValueError("KCM EV settings did not contain a valid programs list.")
    return [KcmEvProgram.from_json(program) for program in programs]


def _get_kcm_program(programs: list[KcmEvProgram], id: int) -> KcmEvProgram:
    """Return a KCM program by the zero-based slot number shown by schedule show."""
    if id < 0 or id >= len(programs):
        raise IndexError(f"KCM program slot {id} not found.")
    return programs[id]


def update_settings(
    schedule: ChargeSchedule,
    **kwargs: Any,
) -> None:
    """Update charging settings."""
    for day in DAYS_OF_WEEK:
        if day in kwargs:
            day_value = kwargs.pop(day)

            if day_value == "clear":
                setattr(schedule, day, None)
            elif day_value:
                start_time, duration = _parse_day_schedule(str(day_value))
                setattr(
                    schedule,
                    day,
                    ChargeDaySchedule(
                        raw_data={}, startTime=start_time, duration=duration
                    ),
                )


def _parse_day_schedule(raw: str) -> tuple[str, int]:
    match = _DAY_SCHEDULE_REGEX.match(raw)
    if not match:
        raise ValueError(
            f"Invalid specification for charge schedule: `{raw}`. "
            "Should be of the form HH:MM,DURATION or THH:MMZ,DURATION"
        )

    hours = int(match.group("hours"))
    if hours >= _HOURS_PER_DAY:
        raise ValueError(
            f"Invalid specification for charge schedule: `{raw}`. "
            "Hours should be less than 24."
        )
    minutes = int(match.group("minutes"))
    if (minutes % 15) != 0:
        raise ValueError(
            f"Invalid specification for charge schedule: `{raw}`. "
            "Minutes should be a multiple of 15."
        )
    duration = int(match.group("duration"))
    if (duration % 15) != 0:
        raise ValueError(
            f"Invalid specification for charge schedule: `{raw}`. "
            "Duration should be a multiple of 15."
        )
    if match.group("prefix") and match.group("suffix"):
        formatted_start_time = f"T{hours:02g}:{minutes:02g}Z"
    elif not (match.group("prefix") or match.group("suffix")):
        formatted_start_time = helpers.convert_minutes_to_tztime(hours * 60 + minutes)
    else:
        raise ValueError(
            f"Invalid specification for charge schedule: `{raw}`. "
            "If provided, both T and Z must be set."
        )
    return (formatted_start_time, duration)
