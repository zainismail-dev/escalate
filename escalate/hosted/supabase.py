"""Headers for Supabase's server-side APIs (Storage, Auth admin) with the service key."""


def service_headers(key: str) -> dict[str, str]:
    """A new secret key (sb_secret_...) goes in `apikey` only: the gateway derives the role.
    A legacy service_role key is a JWT and is also sent as the bearer token."""
    headers = {"apikey": key}
    if not key.startswith("sb_secret_"):
        headers["Authorization"] = f"Bearer {key}"
    return headers
