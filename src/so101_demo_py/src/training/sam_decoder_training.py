"""Decoder-only SAM adaptation primitives using lossless visible-mask truth."""

from __future__ import annotations

from typing import Any


def configure_decoder_training(model: Any) -> tuple[Any, ...]:
    """Freeze every parameter outside the uniquely owned mask decoder."""
    named = tuple(model.named_parameters(remove_duplicate=False))
    decoder = tuple(value for name, value in named if name.startswith("mask_decoder."))
    decoder_ids = {id(value) for value in decoder}
    other_ids = {id(value) for name, value in named if not name.startswith("mask_decoder.")}
    if not decoder or len(decoder_ids) != len(decoder) or decoder_ids & other_ids:
        raise ValueError("DECODER_PARAMETERS_INVALID")
    model.eval()
    for _, value in named:
        value.requires_grad_(id(value) in decoder_ids)
        value.grad = None
    model.mask_decoder.train()
    return decoder


def decoder_loss(logits: Any, quality: Any, truth: Any) -> Any:
    """Supervise all variants on the original grid and calibrate their IoU scores.

    Shapes are logits BxPxVxHxW, quality BxPxV and binary truth BxPxHxW.
    Quality targets use the same zero-logit mask threshold as production.
    """
    import torch
    from torch.nn import functional as functional

    values = (logits, quality, truth)
    if (
        any(not isinstance(value, torch.Tensor) for value in values)
        or logits.ndim != 5
        or quality.ndim != 3
        or truth.ndim != 4
        or tuple(logits.shape[:3]) != tuple(quality.shape)
        or tuple(logits.shape[:2]) != tuple(truth.shape[:2])
        or any(value.numel() == 0 for value in values)
        or any(value.device != logits.device for value in values)
        or any(not torch.isfinite(value).all().item() for value in values)
        or not ((truth == 0) | (truth == 1)).all().item()
    ):
        raise ValueError("TRAINING_TENSORS_INVALID")
    batch, prompts, variants = logits.shape[:3]
    height, width = truth.shape[-2:]
    resized = functional.interpolate(
        logits.float().reshape(batch * prompts, variants, *logits.shape[-2:]),
        size=(height, width),
        mode="bilinear",
        align_corners=False,
    ).reshape(batch, prompts, variants, height, width)
    target = truth.float().unsqueeze(2).expand_as(resized)
    bce = functional.binary_cross_entropy_with_logits(resized, target)
    probabilities = resized.sigmoid()
    intersection = (probabilities * target).sum(dim=(-2, -1))
    denominator = (probabilities + target).sum(dim=(-2, -1))
    dice = (1.0 - (2.0 * intersection + 1.0) / (denominator + 1.0)).mean()
    with torch.no_grad():
        predicted = resized > 0
        foreground = target.bool()
        overlap = (predicted & foreground).sum(dim=(-2, -1)).float()
        union = (predicted | foreground).sum(dim=(-2, -1)).float()
        measured_iou = torch.where(union > 0, overlap / union.clamp_min(1), 1.0)
    quality_loss = functional.mse_loss(quality.float(), measured_iou)
    return bce + dice + quality_loss
