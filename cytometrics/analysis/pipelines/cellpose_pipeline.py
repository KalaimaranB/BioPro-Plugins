import cv2
import numpy as np
import math
import logging


from cellpose import models
import torch  # We need this to check for Mac GPU


class CellposePipeline:
    def __init__(self):
        self.name = "AI Smart Detect (Cellpose)"

        # --- ENTERPRISE HARDWARE CHECK ---
        if torch.cuda.is_available():
            self.device = torch.device('cuda')
            use_gpu = True
        elif torch.backends.mps.is_available():
            self.device = torch.device('mps')
            use_gpu = True
        else:
            self.device = torch.device('cpu')
            use_gpu = False

        self.model = models.CellposeModel(model_type='cyto3', gpu=use_gpu, device=self.device)

        self.model = models.CellposeModel(model_type='cyto3', gpu=use_gpu, device=self.device)

    def run(self, image_stack, params, scale=1.0):
        target_name = params.get("target_channel")
        use_dual = params.get("use_dual_channel", False)
        seed_name = params.get("seed_channel")
        min_area = params.get("min_area_px", 100)
        max_area = params.get("max_area_px", 100000)

        diameter = params.get("diameter", None)
        flow_threshold = params.get("flow_threshold", 0.4)

        # Grab the new parameter from the UI (defaulting to True)
        exclude_borders = params.get("exclude_borders", True)

        target_img = next((ch.data for ch in image_stack.channels if ch.name == target_name), None)
        if target_img is None:
            return []

        img_h, img_w = target_img.shape

        # --- FIX: CELLPOSE V4 DATA STRUCTURE ---
        # Cellpose v4 prefers the array shape to be (Channels, Height, Width)
        if use_dual and seed_name:
            seed_img = next((ch.data for ch in image_stack.channels if ch.name == seed_name), None)
            if seed_img is not None:
                stacked_img = np.array([target_img, seed_img])
            else:
                stacked_img = target_img
        else:
            stacked_img = target_img

        # Run the AI (Deprecated 'channels' argument removed to silence the warning)
        masks, flows, styles = self.model.eval(
            stacked_img,
            diameter=diameter,
            flow_threshold=flow_threshold
        )

        detected_cells = []
        unique_labels = np.unique(masks)

        for label in unique_labels:
            if label == 0:
                continue

            cell_mask = np.zeros_like(masks, dtype=np.uint8)
            cell_mask[masks == label] = 255

            contours, _ = cv2.findContours(cell_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if not contours:
                continue

            cnt = contours[0]

            # --- APPLY BORDER EXCLUSION IF CHECKED ---
            if exclude_borders:
                x, y, w, h = cv2.boundingRect(cnt)
                # If the bounding box is within 1 pixel of the image edge, skip it entirely
                if x <= 1 or y <= 1 or (x + w) >= (img_w - 1) or (y + h) >= (img_h - 1):
                    continue

            area_px = cv2.contourArea(cnt)
            if not (min_area <= area_px <= max_area):
                continue
            perim_px = cv2.arcLength(cnt, True)

            # FORCE STANDARD PYTHON TYPES HERE
            area_um2 = float(area_px * (scale ** 2))
            perim_um = float(perim_px * scale)
            circularity = float((4 * math.pi * area_um2) / (perim_um ** 2) if perim_um > 0 else 0.0)

            # FORCE STANDARD INT FOR COORDINATES
            points = [[int(pt[0][0]), int(pt[0][1])] for pt in cnt]

            detected_cells.append({
                "points": points,
                "area": area_um2,
                "perim": perim_um,
                "circ": circularity
            })

        return detected_cells