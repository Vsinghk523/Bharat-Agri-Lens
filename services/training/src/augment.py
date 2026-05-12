"""Albumentations train / val pipelines.

Modest augmentation set tuned for leaf and field photos:
- horizontal flip + small rotation (leaves are roughly symmetric)
- random crop with scale jitter (model learns position-invariance)
- colour jitter (camera variations across user phones)
- ImageNet normalization (the ViT backbone expects this)

Heavier augmentations (mixup, cutmix, CLAHE) are deliberately off by
default — they help when training from scratch but tend to hurt when
LoRA-fine-tuning a pre-trained backbone for our data scale.
"""

from __future__ import annotations

import albumentations as A
from albumentations.pytorch import ToTensorV2

IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)


def train_transform(image_size: int = 224) -> A.Compose:
    return A.Compose(
        [
            A.RandomResizedCrop(
                size=(image_size, image_size), scale=(0.7, 1.0), ratio=(0.85, 1.15)
            ),
            A.HorizontalFlip(p=0.5),
            A.Rotate(limit=15, border_mode=0, p=0.5),
            A.ColorJitter(brightness=0.2, contrast=0.2, saturation=0.2, hue=0.05, p=0.5),
            A.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD),
            ToTensorV2(),
        ]
    )


def val_transform(image_size: int = 224) -> A.Compose:
    return A.Compose(
        [
            A.Resize(image_size, image_size),
            A.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD),
            ToTensorV2(),
        ]
    )
