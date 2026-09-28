from enum import StrEnum


class RiskLevel(StrEnum):
    READ = "READ"
    WRITE = "WRITE"
    DESTRUCTIVE = "DESTRUCTIVE"


class Decision(StrEnum):
    ALLOW = "allow"
    CONFIRM = "confirm"
    DENY = "deny"


def classify(risk: RiskLevel) -> Decision:
    return {
        RiskLevel.READ: Decision.ALLOW,
        RiskLevel.WRITE: Decision.CONFIRM,
        RiskLevel.DESTRUCTIVE: Decision.DENY,
    }[risk]
