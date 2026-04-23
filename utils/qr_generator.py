import os
import qrcode
from qrcode.constants import ERROR_CORRECT_H


def generate_qr_png(url: str, save_path: str):
    try:
        # Ensure folder exists
        folder = os.path.dirname(save_path)
        if folder:
            os.makedirs(folder, exist_ok=True)

        # Create QR object (better control than qrcode.make)
        qr = qrcode.QRCode(
            version=None,  # auto size
            error_correction=ERROR_CORRECT_H,  # high error correction (important for logo)
            box_size=10,  # controls size
            border=4  # white margin
        )

        qr.add_data(url)
        qr.make(fit=True)

        # Create image
        img = qr.make_image(fill_color="black", back_color="white")

        # Save file
        img.save(save_path)

        return save_path

    except Exception as e:
        raise RuntimeError(f"QR generation failed: {str(e)}")