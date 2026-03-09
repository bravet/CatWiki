from dataclasses import dataclass

from app.core.integration.robot.base import BaseRobotConfig


@dataclass(frozen=True)
class WeComSmartLongConnConfig:
    site_id: int
    bot_id: str
    secret: str


class WeComSmartAdapterConfig(BaseRobotConfig):
    bot_id: str
    secret: str
