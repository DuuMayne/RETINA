"""Generic sub-resource filtering: matches a ProductScope's filter against a
single synced user dict. Deliberately simple — one field/match/value per
scope, no boolean composition. See the architecture plan for why."""


def user_matches_filter(user: dict, filter_field: str, filter_match: str, filter_value: str) -> bool:
    if not filter_field:
        return True

    field_value = user.get(filter_field)
    if field_value is None:
        return False

    value = filter_value.lower().strip()

    if isinstance(field_value, list):
        if filter_match == "equals":
            return any(str(item).lower() == value for item in field_value)
        return any(value in str(item).lower() for item in field_value)  # "contains"

    field_str = str(field_value).lower()
    if filter_match == "equals":
        return field_str == value
    return value in field_str  # "contains"


def filter_snapshot_users(users: list[dict], filter_field: str, filter_match: str, filter_value: str) -> list[dict]:
    if not filter_field:
        return list(users)
    return [u for u in users if user_matches_filter(u, filter_field, filter_match, filter_value)]
