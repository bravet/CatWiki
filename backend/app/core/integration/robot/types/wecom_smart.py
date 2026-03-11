from dataclasses import dataclass


@dataclass(frozen=True)
class WeComSmartLongConnConfig:
    site_id: int
    bot_id: str
    secret: str
