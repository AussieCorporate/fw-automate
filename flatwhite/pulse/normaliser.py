def clamp(value: float, floor: float = 0.0, ceiling: float = 100.0) -> float:
    return max(floor, min(ceiling, value))
