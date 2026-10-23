"""Deterministic paragraph-aware segmentation with bounded, nonoverlapping output."""


def segments(text, maximum=1200):
    while text:
        if len(text) <= maximum:
            if text.strip():
                yield text
            return
        end = text.rfind("\n\n", maximum // 2, maximum)
        if end < 0:
            end = text.rfind(" ", maximum // 2, maximum)
        if end < 0:
            end = maximum
        else:
            end += 1
        part, text = text[:end], text[end:]
        if part.strip():
            yield part
