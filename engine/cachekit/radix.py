"""Compact token radix tree. Edges store shared runs rather than one node per token."""

from dataclasses import dataclass, field


@dataclass
class _Edge:
    tokens: tuple[int, ...]
    count: int
    children: dict[int, "_Edge"] = field(default_factory=dict)


class TokenRadix:
    def __init__(self) -> None:
        self.children: dict[int, _Edge] = {}
        self.count = 0

    def insert(self, tokens: list[int]) -> None:
        self.count += 1
        rest = tuple(tokens)
        children = self.children
        while rest:
            edge = children.get(rest[0])
            if edge is None:
                children[rest[0]] = _Edge(rest, 1)
                return
            shared = 0
            while shared < min(len(rest), len(edge.tokens)) and rest[shared] == edge.tokens[shared]:
                shared += 1
            if shared < len(edge.tokens):
                suffix = _Edge(edge.tokens[shared:], edge.count, edge.children)
                edge.tokens = edge.tokens[:shared]
                edge.children = {suffix.tokens[0]: suffix}
            edge.count += 1
            rest = rest[shared:]
            children = edge.children

    def prefix_stability(self, reference: list[int]) -> list[float]:
        """Fraction sharing each complete prefix, including variable-length shifts."""
        result: list[float] = []
        remaining = tuple(reference)
        children = self.children
        while remaining:
            edge = children.get(remaining[0])
            if edge is None:
                result.extend([0.0] * len(remaining))
                break
            for index, token in enumerate(edge.tokens):
                if index >= len(remaining) or remaining[index] != token:
                    result.extend([0.0] * (len(remaining) - index))
                    return result
                result.append(edge.count / self.count if self.count else 0)
            remaining = remaining[len(edge.tokens) :]
            children = edge.children
        return result


def downsample(values: list[float], limit: int) -> list[float]:
    if len(values) <= limit:
        return values
    return [
        sum(values[i * len(values) // limit : (i + 1) * len(values) // limit])
        / ((i + 1) * len(values) // limit - i * len(values) // limit)
        for i in range(limit)
    ]
