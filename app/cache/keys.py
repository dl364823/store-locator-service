def geocoding_key(query: str) -> str:
    return f"geocode:{query.lower().strip()}"


def search_key(
    lat: float,
    lon: float,
    radius: float,
    services: list[str],
    store_types: list[str],
    open_now: bool,
) -> str:
    svcs = ",".join(sorted(services))
    types = ",".join(sorted(store_types))
    # Round to 4 decimal places (~11m precision) to improve cache hit rate
    return f"search:{lat:.4f}:{lon:.4f}:{radius}:{svcs}:{types}:{open_now}"


def store_key(store_id: str) -> str:
    return f"store:{store_id}"
