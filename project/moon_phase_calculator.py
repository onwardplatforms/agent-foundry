import datetime

EPOCH = datetime.datetime(2000, 1, 6, 18, 14)
LUNAR_CYCLE = 29.53058867


def calculate_moon_phase(date: datetime.datetime = None) -> float:
    """
    Calculate the moon phase for a given date.

    Args:
        date (datetime, optional): The date for which to calculate the moon phase. Defaults to the current date.

    Returns:
        float: The lunar age in days.
    """
    if date is None:
        date = datetime.datetime.now()
    diff = date - EPOCH
    days_since_epoch = diff.total_seconds() / (24 * 3600)
    lunar_age = days_since_epoch % LUNAR_CYCLE
    return lunar_age


def get_moon_phase_name(lunar_age: float) -> str:
    """
    Determine the moon phase name based on the lunar age.

    Args:
        lunar_age (float): The age of the moon in days.

    Returns:
        str: The name of the moon phase.
    """
    if lunar_age < 1.84566:
        return "New Moon"
    elif lunar_age < 5.53699:
        return "Waxing Crescent"
    elif lunar_age < 9.22831:
        return "First Quarter"
    elif lunar_age < 12.91963:
        return "Waxing Gibbous"
    elif lunar_age < 16.61096:
        return "Full Moon"
    elif lunar_age < 20.30228:
        return "Waning Gibbous"
    elif lunar_age < 23.99361:
        return "Last Quarter"
    elif lunar_age < 27.68493:
        return "Waning Crescent"
    else:
        return "New Moon"


if __name__ == "__main__":
    today = datetime.datetime.now()
    lunar_age = calculate_moon_phase(today)
    phase_name = get_moon_phase_name(lunar_age)
    ascii_art = {
        "New Moon": "🌑",
        "Waxing Crescent": "🌒",
        "First Quarter": "🌓",
        "Waxing Gibbous": "🌔",
        "Full Moon": "🌕",
        "Waning Gibbous": "🌖",
        "Last Quarter": "🌗",
        "Waning Crescent": "🌘",
    }
    print(f"Today's moon phase: {phase_name} {ascii_art.get(phase_name, '')}")
