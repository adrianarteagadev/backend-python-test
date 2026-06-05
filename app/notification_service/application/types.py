from enum import StrEnum


class ProcessRequestOutcome(StrEnum):
    ENQUEUED = "enqueued"
    ALREADY_PROCESSING = "already_processing"
    ALREADY_SENT = "already_sent"
