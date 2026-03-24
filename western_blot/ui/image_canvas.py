"""Zoomable, pannable image canvas based on QGraphicsView.

This widget provides a high-quality image viewer with:
    - Mouse wheel zoom (centered on cursor).
    - Middle-click or Ctrl+click pan.
    - Overlay support for drawing lane boundaries and band detections.
    - Draggable lane border lines (enabled only on the lanes step).
    - Fit-to-view on initial load.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
from numpy.typing import NDArray
from PyQt6.QtCore import Qt, QRectF, QPointF, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap, QColor, QPen, QBrush, QCursor, QWheelEvent
from PyQt6.QtWidgets import (
    QGraphicsView,
    QGraphicsScene,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsLineItem,
    QGraphicsTextItem,
)

from biopro.ui.theme import Colors


from biopro.plugins.western_blot.ui.canvas_items import (
    BandOverlayItem,
    LaneBorderItem,
    ResizableCropItem,
)

# ── Image canvas ──────────────────────────────────────────────────────────────

class ImageCanvas(QGraphicsView):
    """Zoomable, pannable image viewer with overlay support."""

    image_loaded = pyqtSignal()
    zoom_changed = pyqtSignal(float)
    band_clicked = pyqtSignal(object)
    crop_requested = pyqtSignal(QRectF)
    lane_border_changed = pyqtSignal(int, float)  # border_idx, new_x
    band_right_clicked = pyqtSignal(int, float)

    peak_pick_requested = pyqtSignal(float, float, bool)
    canvas_range_selected = pyqtSignal(int, float, float, bool)

    _MIN_ZOOM = 0.1
    _MAX_ZOOM = 20.0
    _ZOOM_STEP = 1.15

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)

        self._pixmap_item: Optional[QGraphicsPixmapItem] = None
        self._zoom_factor = 1.0
        self._lane_overlays: list = []
        self._lane_border_items: list[LaneBorderItem] = []
        self._band_overlays: list = []
        self._hover_overlay: Optional[QGraphicsRectItem] = None
        self._peak_picking_enabled = False
        self._lane_edit_mode = False

        self._current_lanes = []  # <--- NEW: Remember lanes for hit detection

        # --- NEW: Band Drag State ---
        self._band_drag_mode = False
        self._band_drag_start = None
        self._active_drag_lane = None
        self._band_drag_rect_item = None

        # Crop state
        self._crop_mode = False
        self._crop_start_pos: Optional[QPointF] = None
        self._crop_rect_item: Optional[QGraphicsRectItem] = None

        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setStyleSheet(
            f"QGraphicsView {{ border: 1px solid {Colors.BORDER};"
            f" background-color: {Colors.BG_DARKEST}; }}"
        )

    # ── Image ─────────────────────────────────────────────────────────

    def set_image(self, image: NDArray[np.float64]) -> None:
        self.clear_overlays()
        if self._crop_rect_item:
            self._scene.removeItem(self._crop_rect_item)
            self._crop_rect_item = None
        self._scene.clear()
        self._pixmap_item = None
        self._lane_border_items.clear()

        img_uint8 = (np.clip(image, 0, 1) * 255).astype(np.uint8)
        h, w = img_uint8.shape[:2]

        if img_uint8.ndim == 2:
            qimage = QImage(
                img_uint8.tobytes(), w, h, w,
                QImage.Format.Format_Grayscale8,
            )
        else:
            qimage = QImage(
                img_uint8.tobytes(), w, h, 3 * w,
                QImage.Format.Format_RGB888,
            )

        pixmap = QPixmap.fromImage(qimage)
        self._pixmap_item = self._scene.addPixmap(pixmap)
        self._scene.setSceneRect(QRectF(pixmap.rect().toRectF()))

        self._zoom_factor = 1.0
        self.fitInView(self._scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
        self.image_loaded.emit()

    # ── Lane overlays ─────────────────────────────────────────────────

    def set_lane_edit_mode(self, enabled: bool) -> None:
        """Enable/disable draggable lane borders.

        Should be True only on the lane detection step.
        """
        self._lane_edit_mode = bool(enabled)
        # Rebuild overlays to add/remove border items
        if self._lane_overlays or self._lane_border_items:
            # Redraw with current mode — caller must re-call add_lane_overlays
            pass

    def add_lane_overlays(self, lanes: list) -> None:
        """Draw lane boundary overlays, with draggable borders in edit mode."""
        self.clear_lane_overlays()
        self._current_lanes = lanes
        if not lanes:
            return

        img_h = (
            self._pixmap_item.boundingRect().height()
            if self._pixmap_item else 1000.0
        )
        img_w = (
            self._pixmap_item.boundingRect().width()
            if self._pixmap_item else 1000.0
        )

        colors = Colors.CHART_COLORS

        # Draw lane fill rectangles and labels
        for i, lane in enumerate(lanes):
            color = QColor(colors[i % len(colors)])
            color.setAlpha(30)

            rect = self._scene.addRect(
                lane.x_start, lane.y_start,
                lane.width, lane.height,
                QPen(Qt.PenStyle.NoPen),
                QBrush(color),
            )
            self._lane_overlays.append(rect)

            label = self._scene.addText(str(i + 1))
            label.setDefaultTextColor(QColor(colors[i % len(colors)]))
            label.setPos(lane.center_x - 5, lane.y_start + 5)
            font = label.font()
            font.setPointSize(max(8, min(20, lane.width // 4)))
            font.setBold(True)
            label.setFont(font)
            self._lane_overlays.append(label)

        if self._lane_edit_mode:
            # Collect all internal boundaries (skip leftmost 0 and rightmost w)
            # boundary i splits lane i-1 and lane i
            for i in range(1, len(lanes)):
                x = float(lanes[i].x_start)
                border = LaneBorderItem(
                    border_index=i,
                    x=x,
                    y_top=0.0,
                    y_bottom=float(img_h),
                    canvas=self,
                )
                border._img_width = img_w
                self._scene.addItem(border)
                self._lane_border_items.append(border)

            # Add a hint label at the top
            hint = self._scene.addText("↔ Drag borders to adjust lanes")
            hint.setDefaultTextColor(QColor(Colors.FG_SECONDARY))
            hint.setPos(4, 2)
            font = hint.font()
            font.setPointSize(8)
            hint.setFont(font)
            hint.setZValue(25)
            self._lane_overlays.append(hint)
        else:
            # Static mode — draw solid border lines
            for i, lane in enumerate(lanes):
                border_color = QColor(colors[i % len(colors)])
                pen = QPen(border_color, 2)
                line = self._scene.addLine(
                    lane.x_start, lane.y_start,
                    lane.x_start, lane.y_end,
                    pen,
                )
                self._lane_overlays.append(line)
            # Right edge of last lane
            if lanes:
                last = lanes[-1]
                border_color = QColor(colors[(len(lanes) - 1) % len(colors)])
                pen = QPen(border_color, 2)
                line = self._scene.addLine(
                    last.x_end, last.y_start,
                    last.x_end, last.y_end,
                    pen,
                )
                self._lane_overlays.append(line)

    def get_current_lane_boundaries(self) -> list[float]:
        """Return current x positions of all draggable borders, sorted."""
        return sorted(b.line().x1() for b in self._lane_border_items)

    def clear_lane_overlays(self) -> None:
        for item in self._lane_overlays:
            self._scene.removeItem(item)
        self._lane_overlays.clear()
        for item in self._lane_border_items:
            self._scene.removeItem(item)
        self._lane_border_items.clear()

    # ── Band overlays ─────────────────────────────────────────────────

    def add_band_overlays(self, lanes: list, bands: list) -> None:
        self.clear_band_overlays()
        for band in bands:
            if band.lane_index >= len(lanes):
                continue
            lane = lanes[band.lane_index]
            color = QColor(Colors.ACCENT_WARNING)
            color.setAlpha(180)
            band_height = max(3, int(band.width))
            rect_geom = QRectF(
                lane.x_start + 2,
                band.position - band_height // 2,
                lane.width - 4,
                band_height,
            )
            item = BandOverlayItem(
                rect_geom, band, color,
                self._on_band_toggled,
                self._on_band_removed
            )
            self._scene.addItem(item)
            self._band_overlays.append(item)

    def _on_band_removed(self, band: object) -> None:
        self.band_right_clicked.emit(band.lane_index, float(band.position))


    def _on_band_toggled(self, band: object) -> None:
        self.band_clicked.emit(band)

    def set_band_comparison_slots(self, band_a, band_b) -> None:
        """Update visual slot markers (A/B) — back-compat for 2-slot usage."""
        slot_map = {}
        if band_a is not None:
            slot_map[(band_a.lane_index, band_a.band_index)] = "A"
        if band_b is not None:
            slot_map[(band_b.lane_index, band_b.band_index)] = "B"
        self.set_all_comparison_slots(slot_map)

    def set_all_comparison_slots(self, slot_map: dict) -> None:
        """Update visual markers for all comparison slots.

        Args:
            slot_map: {(lane_index, band_index): color_hex_or_label}
                      Any band not in the map gets its marker cleared.
        """
        for item in self._band_overlays:
            if not isinstance(item, BandOverlayItem):
                continue
            b = item.band
            key = (b.lane_index, b.band_index)
            val = slot_map.get(key)
            if val is not None:
                item.set_comparison_slot(val)
            else:
                item.set_comparison_slot(None)

    def clear_band_overlays(self) -> None:
        for item in self._band_overlays:
            self._scene.removeItem(item)
        self._band_overlays.clear()

    # ── Hover indicator ───────────────────────────────────────────────

    def show_hover_indicator(self, lane: object, y_position: float) -> None:
        if y_position < 0:
            self.hide_hover_indicator()
            return
        color = QColor(Colors.ACCENT_PRIMARY)
        color.setAlpha(150)
        rect_geom = QRectF(lane.x_start + 2, y_position - 1.5, lane.width - 4, 3)
        if self._hover_overlay is None:
            self._hover_overlay = self._scene.addRect(
                rect_geom, QPen(Qt.PenStyle.NoPen), QBrush(color)
            )
            self._hover_overlay.setZValue(10)
        else:
            self._hover_overlay.setRect(rect_geom)

    def hide_hover_indicator(self) -> None:
        if self._hover_overlay:
            self._scene.removeItem(self._hover_overlay)
            self._hover_overlay = None

    # ── Crop preview ──────────────────────────────────────────────────

    def show_crop_preview(self, rect: QRectF) -> None:
        """Show a resizable crop preview using ResizableCropItem."""
        self.clear_crop_preview()
        img_rect = (
            self._pixmap_item.boundingRect()
            if self._pixmap_item else QRectF(0, 0, 9999, 9999)
        )
        self._crop_rect_item = ResizableCropItem(rect, img_rect)
        self._scene.addItem(self._crop_rect_item)

    def clear_crop_preview(self) -> None:
        if self._crop_rect_item:
            self._scene.removeItem(self._crop_rect_item)
            self._crop_rect_item = None

    def get_current_crop_preview_bounds(self):
        if self._crop_rect_item:
            r = self._crop_rect_item.rect()
            return (int(r.top()), int(r.bottom()), int(r.left()), int(r.right()))
        return None

    # ── Clear all ─────────────────────────────────────────────────────

    def clear_overlays(self) -> None:
        self.clear_lane_overlays()
        self.clear_band_overlays()
        self.hide_hover_indicator()

    # ── Fit to view ───────────────────────────────────────────────────

    def fit_to_view(self) -> None:
        if self._pixmap_item:
            self._zoom_factor = 1.0
            self.resetTransform()
            self.fitInView(
                self._scene.sceneRect(),
                Qt.AspectRatioMode.KeepAspectRatio,
            )

    # ── Modes ─────────────────────────────────────────────────────────

    def set_peak_picking_enabled(self, enabled: bool) -> None:
        self._peak_picking_enabled = bool(enabled)

    def set_crop_mode(self, enabled: bool) -> None:
        self._crop_mode = enabled
        if not enabled and self._crop_rect_item:
            self._scene.removeItem(self._crop_rect_item)
            self._crop_rect_item = None
            self._crop_start_pos = None

    # ── Events ────────────────────────────────────────────────────────

    def wheelEvent(self, event: QWheelEvent) -> None:
        delta = event.angleDelta().y()
        if delta > 0:
            factor = self._ZOOM_STEP
        elif delta < 0:
            factor = 1.0 / self._ZOOM_STEP
        else:
            return
        new_zoom = self._zoom_factor * factor
        if self._MIN_ZOOM <= new_zoom <= self._MAX_ZOOM:
            self._zoom_factor = new_zoom
            self.scale(factor, factor)
            self.zoom_changed.emit(self._zoom_factor)

    def mousePressEvent(self, event) -> None:
        # Crop mode
        if self._crop_mode and event.button() == Qt.MouseButton.LeftButton:
            self._crop_start_pos = self.mapToScene(event.position().toPoint())
            color = QColor(Colors.ACCENT_PRIMARY)
            pen = QPen(color, 2, Qt.PenStyle.DashLine)
            brush = QColor(color)
            brush.setAlpha(30)
            if self._crop_rect_item is None:
                self._crop_rect_item = self._scene.addRect(
                    QRectF(self._crop_start_pos, self._crop_start_pos), pen, brush
                )
            else:
                self._crop_rect_item.setRect(
                    QRectF(self._crop_start_pos, self._crop_start_pos)
                )
            event.accept()
            return

        # --- NEW: Shift+Drag Band Selection ---
        if event.button() == Qt.MouseButton.LeftButton and (event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            pos = self.mapToScene(event.position().toPoint())
            # Check which lane we clicked inside
            lane = next((ln for ln in self._current_lanes if ln.x_start <= pos.x() <= ln.x_end), None)
            if lane:
                self._band_drag_mode = True
                self._band_drag_start = pos
                self._active_drag_lane = lane

                color = QColor(Colors.ACCENT_WARNING)
                pen = QPen(color, 1, Qt.PenStyle.SolidLine)
                brush = QColor(color);
                brush.setAlpha(60)
                self._band_drag_rect_item = self._scene.addRect(QRectF(pos, pos), pen, brush)
                event.accept()
                return

        # Peak picking
        if (
                self._peak_picking_enabled
                and event.button() == Qt.MouseButton.LeftButton
                and not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier)  # Removed Ctrl check from here
        ):
            pos = self.mapToScene(event.position().toPoint())

            # --- NEW: Check if Ctrl/Cmd is held for manual override ---
            modifiers = event.modifiers()
            is_ctrl = bool(modifiers & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier))
            auto_snap = not is_ctrl  # If Ctrl is held, do NOT auto-snap

            self.peak_pick_requested.emit(float(pos.x()), float(pos.y()), auto_snap)
            event.accept()
            return

        # Pan
        if (
            event.button() == Qt.MouseButton.MiddleButton
            or (
                event.button() == Qt.MouseButton.LeftButton
                and event.modifiers() & Qt.KeyboardModifier.ControlModifier
            )
        ):
            self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
            super().mousePressEvent(event)
            return

        # Default — pass to scene items (LaneBorderItem, BandOverlayItem)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._crop_mode and self._crop_start_pos is not None:
            current_pos = self.mapToScene(event.position().toPoint())
            rect = QRectF(self._crop_start_pos, current_pos).normalized()
            if self._pixmap_item:
                rect = rect.intersected(self._pixmap_item.boundingRect())
            if self._crop_rect_item:
                self._crop_rect_item.setRect(rect)
            event.accept()
            return
        # --- NEW: Band Drag Move ---
        if self._band_drag_mode and self._band_drag_start is not None and self._active_drag_lane:
            current_pos = self.mapToScene(event.position().toPoint())
            lane = self._active_drag_lane

            # Constrain the box width strictly to the lane boundaries!
            top = min(self._band_drag_start.y(), current_pos.y())
            bottom = max(self._band_drag_start.y(), current_pos.y())

            rect = QRectF(lane.x_start + 2, top, lane.width - 4, bottom - top)
            if self._band_drag_rect_item:
                self._band_drag_rect_item.setRect(rect)
            event.accept()
            return
        # ---------------------------

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self._crop_mode and event.button() == Qt.MouseButton.LeftButton:
            if self._crop_rect_item and self._crop_start_pos is not None:
                rect = self._crop_rect_item.rect()
                if rect.width() > 4 and rect.height() > 4:
                    self.crop_requested.emit(rect)
            self._crop_start_pos = None
            event.accept()
            return

        # --- NEW: Band Drag Release ---
        if self._band_drag_mode and event.button() == Qt.MouseButton.LeftButton:
            if self._band_drag_rect_item and self._active_drag_lane:
                rect = self._band_drag_rect_item.rect()
                if rect.height() > 3:  # Ignore tiny accidental drags

                    # --- NEW: Check if Ctrl/Cmd was also held during the drag ---
                    modifiers = event.modifiers()
                    is_ctrl = bool(
                        modifiers & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier))
                    auto_snap = not is_ctrl

                    # Convert to lane-relative Y coordinates
                    y_start = rect.top() - self._active_drag_lane.y_start
                    y_end = rect.bottom() - self._active_drag_lane.y_start

                    # Emit with the auto_snap boolean
                    self.canvas_range_selected.emit(self._active_drag_lane.index, float(y_start), float(y_end),
                                                    auto_snap)

                # Cleanup the temporary drag box
                if self._band_drag_rect_item.scene():
                    self._scene.removeItem(self._band_drag_rect_item)

            self._band_drag_mode = False
            self._band_drag_start = None
            self._active_drag_lane = None
            self._band_drag_rect_item = None
            event.accept()
            return

        if self.dragMode() == QGraphicsView.DragMode.ScrollHandDrag:
            self.setDragMode(QGraphicsView.DragMode.NoDrag)

        super().mouseReleaseEvent(event)