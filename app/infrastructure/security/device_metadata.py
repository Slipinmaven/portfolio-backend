from user_agents import parse


def parse_device_metadata(
    user_agent: str | None,
) -> tuple[str | None, str | None, str | None, str | None]:
    if not user_agent:
        return None, None, None, None

    parsed = parse(user_agent[:2048])
    operating_system = parsed.os.family
    browser = parsed.browser.family

    if parsed.is_bot:
        device_type = "bot"
    elif parsed.is_tablet:
        device_type = "tablet"
    elif parsed.is_mobile:
        device_type = "mobile"
    elif parsed.is_pc:
        device_type = "desktop"
    else:
        device_type = "unknown"

    device_name = parsed.device.family
    if device_name in {"Other", "Spider"}:
        device_name = f"{operating_system} device" if operating_system else None

    return (
        device_name[:150] if device_name else None,
        device_type[:50] if device_type else None,
        browser[:100] if browser and browser != "Other" else None,
        operating_system[:100]
        if operating_system and operating_system != "Other"
        else None,
    )
