from pydantic import BaseModel


class AlertItem(BaseModel):
    fingerprint: str
    status: str
    labels: dict[str, str]


class AlertmanagerWebhook(BaseModel):
    alerts: list[AlertItem]
