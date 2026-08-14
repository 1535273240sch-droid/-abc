import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ResolvedSecret:
    reference: str
    value: str
    provider: str


class SecretResolver:
    """Resolve references internally; never include resolved values in API output."""

    def resolve(self, reference: str | None) -> ResolvedSecret | None:
        if not reference:
            return None
        if reference.startswith("env://"):
            name = reference.removeprefix("env://")
            value = os.getenv(name)
            if value:
                return ResolvedSecret(reference=reference, value=value, provider="environment")
        return None

    def availability(self, reference: str | None) -> str:
        if not reference:
            return "not_configured"
        return "resolved" if self.resolve(reference) else "reference_configured"


secret_resolver = SecretResolver()
