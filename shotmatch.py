"""Locate a module's panel inside a window screenshot by template matching.

The reliability core of the screenshot tool. Rather than computing a module's
on-screen pixel rectangle from Rack's view state (scroll, zoom, Retina backing
scale) — the arithmetic that historically drifted — we take the module's known
default-state render as a template and find where it sits inside a full-window
capture, then crop exactly the matched box.

Matching is normalized cross-correlation (Lewis, "Fast Normalized Cross-
Correlation", 1995), computed via FFT so a full-window search is O(N log N)
rather than a pixel-by-pixel slide. NCC is invariant to brightness/contrast
offset, which absorbs the small tonal differences between Rack's offscreen
screenshot render and a live window capture (antialiasing, a lit LED, a cable
end clipping a corner).

The on-screen module is the template scaled by ``viewZoom * backingScale``; the
caller passes candidate scales (a hint plus fallbacks) and we return the best
match across them. A match below ``min_score`` is reported as a failure by the
caller — a low score must surface as a loud error, never a silently-wrong crop.

Pure and Rack-free: everything here operates on numpy arrays / PIL images, so it
is unit-tested without launching Rack or capturing a window.
"""
from dataclasses import dataclass

import numpy as np
from PIL import Image


@dataclass
class Match:
    """Where the template was found in the window, in window pixels."""
    x: int
    y: int
    w: int
    h: int
    scale: float
    score: float  # peak normalized cross-correlation in [-1, 1]


def to_gray(image):
    """A PIL image or path -> float32 grayscale array in [0, 1], shape (H, W)."""
    if isinstance(image, (str, bytes)):
        image = Image.open(image)
    if image.mode != "L":
        image = image.convert("L")
    return np.asarray(image, dtype=np.float32) / 255.0


def _resize_gray(arr, scale):
    """Resize a grayscale float array by ``scale`` (Lanczos, via PIL)."""
    if scale == 1.0:
        return arr
    h, w = arr.shape
    nw = max(1, int(round(w * scale)))
    nh = max(1, int(round(h * scale)))
    img = Image.fromarray((np.clip(arr, 0, 1) * 255).astype(np.uint8), mode="L")
    img = img.resize((nw, nh), Image.LANCZOS)
    return np.asarray(img, dtype=np.float32) / 255.0


def _valid_xcorr(image, kernel):
    """Linear cross-correlation over every valid (fully-overlapping) window.

    Returns an array of shape (H-kh+1, W-kw+1) whose [y, x] entry is
    ``sum_{i,j} image[y+i, x+j] * kernel[i, j]``. Computed as a circular
    correlation via rFFT; because the kernel is padded to the image size and we
    keep only the valid region, no wraparound contaminates the result.
    """
    ih, iw = image.shape
    kh, kw = kernel.shape
    fh, fw = ih, iw
    F = np.fft.rfft2(image, s=(fh, fw))
    K = np.fft.rfft2(kernel, s=(fh, fw))
    corr = np.fft.irfft2(F * np.conj(K), s=(fh, fw))
    return corr[: ih - kh + 1, : iw - kw + 1]


def _window_sums(image, kh, kw):
    """Sum of ``image`` over every kh x kw window, via an integral image.

    Shape matches ``_valid_xcorr``: (H-kh+1, W-kw+1).
    """
    ii = np.zeros((image.shape[0] + 1, image.shape[1] + 1), dtype=np.float64)
    ii[1:, 1:] = np.cumsum(np.cumsum(image, axis=0, dtype=np.float64), axis=1)
    return (ii[kh:, kw:] - ii[:-kh, kw:] - ii[kh:, :-kw] + ii[:-kh, :-kw])


def ncc_map(window, template):
    """Normalized-cross-correlation map of ``template`` over ``window``.

    Both are float grayscale arrays; ``template`` must fit inside ``window``.
    Entry [y, x] is the NCC of the template against the window patch anchored at
    (y, x), in roughly [-1, 1]. Higher is a better match.
    """
    th, tw = template.shape
    n = th * tw
    t0 = template.astype(np.float64) - float(template.mean())
    t_norm = float(np.sqrt((t0 * t0).sum()))
    if t_norm == 0.0:
        raise ValueError("template is a flat image; nothing to match")

    img = window.astype(np.float64)
    num = _valid_xcorr(img, t0)  # sum over window of (patch * zero-mean template)
    s = _window_sums(img, th, tw)
    s2 = _window_sums(img * img, th, tw)
    # local patch energy about its own mean: sum(patch^2) - sum(patch)^2 / n
    energy = np.clip(s2 - (s * s) / n, 1e-9, None)
    denom = np.sqrt(energy) * t_norm
    return num / denom


def match_at_scale(window, template, scale):
    """Best NCC match of ``template`` resized by ``scale``. None if it can't fit."""
    tpl = _resize_gray(template, scale)
    th, tw = tpl.shape
    wh, ww = window.shape
    if th > wh or tw > ww:
        return None
    m = ncc_map(window, tpl)
    idx = int(np.argmax(m))
    y, x = np.unravel_index(idx, m.shape)
    return Match(x=int(x), y=int(y), w=int(tw), h=int(th),
                 scale=float(scale), score=float(m[y, x]))


def locate(window, template, scales):
    """Find ``template`` in ``window`` across candidate ``scales``.

    ``window`` and ``template`` are grayscale float arrays (see ``to_gray``);
    ``scales`` is an iterable of positive floats (the on-screen size of the
    module is the template times ``viewZoom * backingScale``). Returns the best
    ``Match`` across all scales, or None if the template fits at no scale.
    """
    best = None
    seen = set()
    for scale in scales:
        key = round(float(scale), 4)
        if key <= 0 or key in seen:
            continue
        seen.add(key)
        m = match_at_scale(window, template, key)
        if m is not None and (best is None or m.score > best.score):
            best = m
    return best
