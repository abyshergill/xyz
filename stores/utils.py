"""
Utilities for secure image handling (Pillow) and QR code generation.
"""

import io
import os
import uuid

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.conf import settings
from PIL import Image, UnidentifiedImageError
import qrcode


def validate_and_process_image(uploaded_file, max_dimension: int) -> ContentFile:
    """
    Re-encodes any uploaded image through Pillow before it ever touches disk.
    This:
      * Rejects files that aren't genuinely images (defends against a
        malicious file with a .jpg extension but arbitrary/executable
        content -- "polyglot" upload attacks).
      * Strips EXIF/metadata (privacy) and any embedded scripts some formats
        allow.
      * Downscales oversized images for fast mobile loading.
      * Normalizes output to JPEG to keep storage predictable.
    """
    ext = os.path.splitext(uploaded_file.name)[1].lower()
    if ext not in settings.ALLOWED_IMAGE_EXTENSIONS:
        raise ValidationError(f"Unsupported file extension '{ext}'.")

    if uploaded_file.size > settings.MAX_UPLOAD_IMAGE_MB * 1024 * 1024:
        raise ValidationError(f"Image exceeds the {settings.MAX_UPLOAD_IMAGE_MB}MB limit.")

    try:
        img = Image.open(uploaded_file)
        img.verify()  # verifies it's a real, non-truncated image
        uploaded_file.seek(0)
        img = Image.open(uploaded_file)  # re-open after verify() (which invalidates the handle)
        img = img.convert("RGB")
    except (UnidentifiedImageError, OSError):
        raise ValidationError("The uploaded file is not a valid image.")

    # Downscale, preserving aspect ratio, only if larger than the target.
    img.thumbnail((max_dimension, max_dimension), Image.LANCZOS)

    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=85, optimize=True)
    buffer.seek(0)

    new_name = f"{uuid.uuid4().hex}.jpg"
    return ContentFile(buffer.read(), name=new_name)


def generate_store_qr_code(store) -> ContentFile:
    """
    Generates a QR code image that encodes the absolute URL to a store's
    public menu page, so a scan takes a customer straight to checkout.
    """
    menu_url = f"{settings.SITE_BASE_URL}/store/{store.slug}/"

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(menu_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)

    return ContentFile(buffer.read(), name=f"qr_{store.slug}.png")
