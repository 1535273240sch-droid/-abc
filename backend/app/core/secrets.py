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
        # env:// prefix: read from environment variable
        if reference.startswith("env://"):
            name = reference.removeprefix("env://")
            value = os.getenv(name)
            if value:
                return ResolvedSecret(reference=reference, value=value, provider="environment")
            return None
        # plain:// prefix: the value follows the prefix directly
        if reference.startswith("plain://"):
            value = reference.removeprefix("plain://")
            if value:
                return ResolvedSecret(reference=reference, value=value, provider="plain")
            return None
        # Fallback: treat any non-empty string as a direct API key value.
        # This enables users who paste raw keys into the UI to work immediately.
        if len(reference) >= 8:
            return ResolvedSecret(reference="<direct>", value=reference, provider="direct")
        return None

    def availability(self, reference: str | None) -> str:
        if not reference:
            return "not_configured"
        return "resolved" if self.resolve(reference) else "reference_configured"


secret_resolver = SecretResolver()
