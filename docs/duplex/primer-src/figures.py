"""SVG figures for the primer. Each function returns one <figure> as a string.

Orange always marks the user's stream and teal the model's. Everything else uses currentColor.
"""

import math


def _wave(x0: float, x1: float, mid: float, amp: float, n: int = 90) -> str:
    """A speech-like waveform: a fast wiggle shaped by a slow envelope."""
    pts = []
    for i in range(n + 1):
        t = i / n
        envelope = 0.25 + 0.75 * abs(math.sin(math.pi * (t * 3.1 + 0.2))) * (0.6 + 0.4 * math.sin(t * 7.0) ** 2)
        y = mid + amp * envelope * math.sin(t * 2 * math.pi * 26 + 0.8 * math.sin(t * 40))
        pts.append(f"{x0 + (x1 - x0) * t:.1f},{y:.1f}")
    return " ".join(pts)


def _grid(x: float, y: float, cols: int, rows: int, values, cls: str, cw: int = 22, ch: int = 16, gap: int = 3) -> str:
    """A token grid. `values[row][col]` is an opacity from 0 to 1."""
    out = []
    for r in range(rows):
        for c in range(cols):
            out.append(
                f'<rect class="{cls}" x="{x + c * (cw + gap)}" y="{y + r * (ch + gap)}" width="{cw}" height="{ch}" '
                f'rx="2" opacity="{values[r][c]:.2f}"/>'
            )
    return "".join(out)


def _levels(seed: int, cols: int, lo: float = 0.25, hi: float = 0.95) -> list[float]:
    """A fixed pseudo-random row of opacities, so the picture is the same on every build."""
    out, state = [], seed * 7919 + 13
    for _ in range(cols):
        state = (state * 1103515245 + 12345) % 2**31
        out.append(lo + (hi - lo) * ((state >> 8) % 1000) / 999)
    return out


ARROW = (
    '<defs><marker id="{id}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
    'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="currentColor"/></marker></defs>'
)


def figure(svg: str, caption: str, label: str, view: str) -> str:
    return (
        f'<figure><div class="scroll"><svg viewBox="{view}" role="img" aria-label="{label}">{svg}</svg></div>'
        f"<figcaption>{caption}</figcaption></figure>"
    )


def fig_codec() -> str:
    cols, rows = 12, 8
    values = [[0.9] * cols] + [[0.22] * cols for _ in range(rows - 1)]
    gx, gy = 268, 52
    grid_w = cols * 25 - 3
    svg = ARROW.format(id="a1")
    svg += f'<polyline points="{_wave(20, 200, 118, 42)}" fill="none" stroke="currentColor" stroke-width="1.3"/>'
    svg += '<text x="110" y="40" text-anchor="middle">1 second of speech</text>'
    svg += '<text x="110" y="196" text-anchor="middle" class="dim">24,000 numbers</text>'
    svg += '<line x1="208" y1="118" x2="258" y2="118" stroke="currentColor" stroke-width="1.3" marker-end="url(#a1)"/>'
    svg += '<text x="233" y="108" text-anchor="middle" class="dim">codec</text>'
    svg += _grid(gx, gy, cols, rows, values, "ink")
    svg += f'<text x="{gx + grid_w / 2}" y="40" text-anchor="middle">12.5 columns per second</text>'
    svg += f'<line x1="{gx}" y1="212" x2="{gx + 22}" y2="212" stroke="currentColor" stroke-width="1.3"/>'
    svg += f'<text x="{gx + 30}" y="216" class="dim">one column = one frame = 80 ms</text>'
    rx = gx + grid_w + 12
    svg += f'<text x="{rx}" y="{gy + 12}">token 1: what was said</text>'
    svg += f'<path d="M{rx},{gy + 22} h6 v{7 * 19 - 6} h-6" fill="none" stroke="currentColor" stroke-width="1"/>'
    svg += f'<text x="{rx + 14}" y="{gy + 19 * 4 + 12}">tokens 2 to 8:</text>'
    svg += f'<text x="{rx + 14}" y="{gy + 19 * 4 + 28}">how it sounded</text>'
    return figure(
        svg,
        "A codec turns one second of speech from 24,000 numbers into about 100 tokens: 12.5 frames, "
        "8 tokens each. A matching decoder turns the tokens back into sound.",
        "A waveform of one second of speech becomes a grid of tokens, twelve columns by eight rows.",
        "0 0 770 228",
    )


def fig_rvq() -> str:
    labels = ["one frame", "codebook 1", "what is left", "codebook 2", "... 3 to 7", "codebook 8"]
    tokens = {1: "token 1", 3: "token 2", 5: "token 8"}
    svg = ARROW.format(id="a2")
    w, h, gap, x0, y0 = 100, 40, 22, 30, 24
    for i, label in enumerate(labels):
        x = x0 + i * (w + gap)
        dashed = ' stroke-dasharray="4 3"' if i in (0, 2, 4) else ""
        svg += f'<rect x="{x}" y="{y0}" width="{w}" height="{h}" rx="6" fill="none" stroke="currentColor" stroke-width="1.2"{dashed}/>'
        svg += f'<text x="{x + w / 2}" y="{y0 + 25}" text-anchor="middle">{label}</text>'
        if i < len(labels) - 1:
            svg += f'<line x1="{x + w + 3}" y1="{y0 + h / 2}" x2="{x + w + gap - 3}" y2="{y0 + h / 2}" stroke="currentColor" stroke-width="1.2" marker-end="url(#a2)"/>'
        if i in tokens:
            svg += f'<line x1="{x + w / 2}" y1="{y0 + h + 3}" x2="{x + w / 2}" y2="{y0 + h + 24}" stroke="currentColor" stroke-width="1.2" marker-end="url(#a2)"/>'
            svg += f'<text x="{x + w / 2}" y="{y0 + h + 42}" text-anchor="middle">{tokens[i]}</text>'
    return figure(
        svg,
        "Residual vector quantization. Each codebook stores the closest match it has and passes on the "
        "error, so later tokens add finer detail.",
        "A frame goes to codebook 1, which gives token 1 and passes what is left to codebook 2, and so on to codebook 8.",
        "0 0 770 118",
    )


def fig_two_transformers() -> str:
    svg = ARROW.format(id="a3")
    # Past frames: user tokens (orange), model text (ink), model audio (teal).
    for i, name in enumerate(["t-4", "t-3", "t-2", "t-1", "now"]):
        x = 44 + i * 52
        svg += f'<rect class="u" x="{x}" y="150" width="34" height="30" rx="3"/>'
        svg += f'<rect class="ink" x="{x}" y="184" width="34" height="10" rx="2" opacity="0.8"/>'
        svg += f'<rect class="m" x="{x}" y="198" width="34" height="30" rx="3"/>'
        svg += f'<text x="{x + 17}" y="246" text-anchor="middle" class="dim">{name}</text>'
        svg += f'<line x1="{x + 17}" y1="146" x2="{x + 17}" y2="100" stroke="currentColor" stroke-width="1" marker-end="url(#a3)"/>'
    svg += '<rect x="30" y="44" width="270" height="52" rx="8" fill="none" stroke="currentColor" stroke-width="1.4"/>'
    svg += '<text x="165" y="66" text-anchor="middle">Temporal transformer (large)</text>'
    svg += '<text x="165" y="84" text-anchor="middle" class="dim">one step per frame</text>'
    svg += '<line x1="304" y1="70" x2="396" y2="70" stroke="currentColor" stroke-width="1.4" marker-end="url(#a3)"/>'
    svg += '<text x="350" y="60" text-anchor="middle" class="dim">summary</text>'
    svg += '<rect x="400" y="44" width="330" height="52" rx="8" fill="none" stroke="currentColor" stroke-width="1.4"/>'
    svg += '<text x="565" y="66" text-anchor="middle">Depth transformer (small)</text>'
    svg += '<text x="565" y="84" text-anchor="middle" class="dim">nine quick steps inside the frame</text>'
    names = ["text", "1", "2", "3", "4", "5", "6", "7", "8"]
    for i, name in enumerate(names):
        x = 404 + i * 36
        cls = "ink" if i == 0 else "m"
        opacity = ' opacity="0.8"' if i == 0 else ""
        svg += f'<rect class="{cls}" x="{x}" y="150" width="30" height="30" rx="3"{opacity}/>'
        svg += f'<text x="{x + 15}" y="198" text-anchor="middle" class="dim">{name}</text>'
        svg += f'<line x1="{x + 15}" y1="100" x2="{x + 15}" y2="146" stroke="currentColor" stroke-width="1" marker-end="url(#a3)"/>'
    svg += '<text x="565" y="222" text-anchor="middle">the model\'s next frame, written one token at a time</text>'
    svg += '<rect class="u" x="44" y="16" width="12" height="12" rx="2"/><text x="62" y="27" class="dim">user audio</text>'
    svg += '<rect class="ink" x="150" y="16" width="12" height="12" rx="2" opacity="0.8"/><text x="168" y="27" class="dim">model text</text>'
    svg += '<rect class="m" x="258" y="16" width="12" height="12" rx="2"/><text x="276" y="27" class="dim">model audio</text>'
    return figure(
        svg,
        "Two transformers share the work. The large one runs 12.5 times a second and reads everything so "
        "far. The small one writes the next frame: one text token, then eight audio tokens.",
        "A large temporal transformer reads past frames and passes a summary to a small depth transformer, "
        "which writes the next frame token by token.",
        "0 0 770 256",
    )


def fig_duplex() -> str:
    x0, per_s = 124, 78.0

    def x(sec: float) -> float:
        return x0 + sec * per_s

    svg = ""
    for label, y in (("User audio", 64), ("Model text", 128), ("Model audio", 192)):
        svg += f'<text x="10" y="{y + 4}">{label}</text>'
        svg += f'<line x1="{x0}" y1="{y}" x2="{x(8)}" y2="{y}" stroke="currentColor" stroke-width="0.6" opacity="0.35"/>'
    # User speech, then an interruption.
    svg += f'<rect class="u" x="{x(0.3)}" y="50" width="{x(3.6) - x(0.3)}" height="28" rx="4"/>'
    svg += f'<text x="{x(0.42)}" y="68" class="on">I got my results and it is not good</text>'
    svg += f'<rect class="u" x="{x(6.4)}" y="50" width="{x(7.5) - x(6.4)}" height="28" rx="4"/>'
    svg += f'<text x="{x(6.5)}" y="68" class="on">Wait, no</text>'
    # Model audio: a backchannel, then a reply that starts early and is cut off.
    svg += f'<rect class="m" x="{x(1.9)}" y="178" width="{x(2.35) - x(1.9)}" height="28" rx="4"/>'
    svg += f'<rect class="m" x="{x(3.4)}" y="178" width="{x(6.6) - x(3.4)}" height="28" rx="4"/>'
    # Model text: each word is written just before it is spoken.
    for sec, word in ((1.84, "mm-hm"), (3.34, "Oh no."), (4.1, "I'm sorry."), (5.15, "What did they say?")):
        svg += f'<line x1="{x(sec)}" y1="120" x2="{x(sec)}" y2="136" stroke="currentColor" stroke-width="1"/>'
        svg += f'<text x="{x(sec) + 4}" y="132">{word}</text>'
    for n, sec, y in ((1, 2.12, 160), (2, 3.5, 160), (3, 6.5, 160)):
        svg += f'<circle cx="{x(sec)}" cy="{y}" r="9" fill="none" stroke="currentColor" stroke-width="1.2"/>'
        svg += f'<text x="{x(sec)}" y="{y + 4}" text-anchor="middle">{n}</text>'
    for sec in range(0, 9):
        svg += f'<line x1="{x(sec)}" y1="222" x2="{x(sec)}" y2="228" stroke="currentColor" stroke-width="1"/>'
        svg += f'<text x="{x(sec)}" y="244" text-anchor="middle" class="dim">{sec} s</text>'
    svg += f'<line x1="{x0}" y1="222" x2="{x(8)}" y2="222" stroke="currentColor" stroke-width="1"/>'
    svg += f'<line x1="{x(0)}" y1="28" x2="{x(0.08)}" y2="28" stroke="currentColor" stroke-width="3"/>'
    svg += f'<text x="{x(0.08) + 8}" y="32" class="dim">one frame, 80 ms, drawn to scale</text>'
    return figure(
        svg,
        "Eight seconds of a full-duplex conversation. Both audio streams run the whole time. "
        "(1) The model says \"mm-hm\" while the user is still talking. (2) It starts its reply just before "
        "the user finishes. (3) It stops when the user cuts in.",
        "A timeline with three lanes: user audio, model text and model audio. The model's speech overlaps the user's.",
        "0 0 770 254",
    )


def fig_same_words() -> str:
    rows = 8
    left_cols, right_cols = 9, 12
    top = _levels(3, left_cols, 0.45, 0.95)
    # The slow delivery keeps the same first-row pattern, stretched over more frames.
    stretch = [0, 0, 1, 2, 2, 3, 4, 5, 5, 6, 7, 8]
    left = [top] + [_levels(10 + r, left_cols) for r in range(1, rows)]
    right = [[top[i] for i in stretch]] + [_levels(40 + r, right_cols) for r in range(1, rows)]
    lx, rx, gy = 30, 400, 62
    svg = _grid(lx, gy, left_cols, rows, left, "u")
    svg += _grid(rx, gy, right_cols, rows, right, "u")
    svg += f'<text x="{lx}" y="30">Plain voice</text><text x="{lx}" y="48" class="dim">"I got my results back."</text>'
    svg += f'<text x="{rx}" y="30">Low, slow voice</text><text x="{rx}" y="48" class="dim">"I got my results back."</text>'
    mid = 322
    svg += f'<text x="{mid}" y="{gy + 12}" text-anchor="middle">same</text>'
    svg += f'<line x1="{lx + left_cols * 25}" y1="{gy + 8}" x2="{mid - 22}" y2="{gy + 8}" stroke="currentColor" stroke-width="1"/>'
    svg += f'<line x1="{mid + 22}" y1="{gy + 8}" x2="{rx - 5}" y2="{gy + 8}" stroke="currentColor" stroke-width="1"/>'
    svg += f'<text x="{mid}" y="{gy + 19 * 4 + 14}" text-anchor="middle">different</text>'
    svg += f'<path d="M{lx + left_cols * 25 + 2},{gy + 21} h8 v{7 * 19 - 8} h-8" fill="none" stroke="currentColor" stroke-width="1"/>'
    svg += f'<path d="M{rx - 5},{gy + 21} h-8 v{7 * 19 - 8} h8" fill="none" stroke="currentColor" stroke-width="1"/>'
    return figure(
        svg,
        "The same sentence said two ways. The first row, which mostly carries the words, keeps its "
        "pattern. The other seven rows change, and the slow version takes more frames. A model that reads "
        "only the first row hears no difference.",
        "Two token grids for the same sentence. The first rows match and the other rows differ.",
        "0 0 770 224",
    )
