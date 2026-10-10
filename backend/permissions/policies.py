from enum import StrEnum


class RiskLevel(StrEnum):
    READ = "READ"
    INTERACTIVE = "INTERACTIVE"
    WRITE = "WRITE"
    DESTRUCTIVE = "DESTRUCTIVE"


class Decision(StrEnum):
    ALLOW = "allow"
    CONFIRM = "confirm"
    DENY = "deny"


def classify(risk: RiskLevel) -> Decision:
    return {
        RiskLevel.READ: Decision.ALLOW,
        RiskLevel.INTERACTIVE: Decision.CONFIRM,
        RiskLevel.WRITE: Decision.CONFIRM,
        RiskLevel.DESTRUCTIVE: Decision.DENY,
    }[risk]
