"""Background workers and threading utilities for CytoMetrics."""

import logging
import requests
from pathlib import Path
from PyQt6.QtCore import QObject, QThread, pyqtSignal


class InterceptorSignals(QObject):
    """Helper class to hold PyQt signals for the standard logging handler."""
    progress_signal = pyqtSignal(int)
    status_signal = pyqtSignal(str)


import logging
from PyQt6.QtCore import QObject, pyqtSignal, QThread


import sys
from PyQt6.QtCore import QThread, pyqtSignal, QObject

class StreamCatcher(QObject):
    """Intercepts terminal output (stderr) so we can see what Cellpose is actually saying."""
    text_written = pyqtSignal(str)

    def __init__(self, original_stream):
        super().__init__()
        self.original_stream = original_stream

    def write(self, text):
        self.original_stream.write(text) # Still print to your Mac terminal
        if text.strip(): # Only send if it's not an empty newline
            self.text_written.emit(text.strip())

    def flush(self):
        self.original_stream.flush()


class CellposeLogInterceptor(logging.Handler):
    """Eavesdrops on Cellpose logs to provide real-time UI updates."""

    def __init__(self):
        super().__init__()
        self.signals = InterceptorSignals()

    def emit(self, record):
        msg = self.format(record).lower()
        self.signals.status_signal.emit(record.getMessage())

        if "downloading" in msg:
            self.signals.progress_signal.emit(5)
        elif "evaluating" in msg or "network" in msg:
            self.signals.progress_signal.emit(20)
        elif "computing flows" in msg:
            self.signals.progress_signal.emit(50)
        elif "computing masks" in msg:
            self.signals.progress_signal.emit(80)


class PipelineWorker(QThread):
    progress = pyqtSignal(int)
    status = pyqtSignal(str)
    finished = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, pipeline, image_stack, params, scale):
        super().__init__()
        self.pipeline = pipeline
        self.image_stack = image_stack
        self.params = params
        self.scale = scale

    def run(self):
        self.progress.emit(10)
        self.status.emit("Starting AI...")

        # 1. Hijack the terminal's standard error stream
        original_stderr = sys.stderr
        catcher = StreamCatcher(original_stderr)

        # Every time Cellpose prints to the terminal, show it on the Run Button!
        catcher.text_written.connect(lambda msg: self.status.emit(f"DEBUG: {msg[:30]}..."))
        sys.stderr = catcher

        try:
            # 2. Run the AI
            result_cells = self.pipeline.run(self.image_stack, self.params, self.scale)

            self.progress.emit(95)
            self.status.emit("Finishing up...")
            self.finished.emit(result_cells)

        except Exception as e:
            self.error.emit(str(e))

        finally:
            # 3. Put the terminal back to normal!
            sys.stderr = original_stderr
            self.progress.emit(100)


class ModelDownloadWorker(QThread):
    """Safely downloads the Cellpose model in the background without freezing the UI."""
    progress = pyqtSignal(int)
    finished = pyqtSignal(bool, str)

    def run(self):
        model_dir = Path.home() / ".cellpose" / "models"
        model_dir.mkdir(parents=True, exist_ok=True)
        model_path = model_dir / "cyto3"
        
        url = "https://www.cellpose.org/models/cyto3"

        try:
            # We add a "User-Agent" header to disguise the script as a standard web browser
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            response = requests.get(url, stream=True, headers=headers)
            response.raise_for_status() # Instantly catches 404 or 403 errors
            
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            
            # Write the file to disk in chunks so we don't blow up the RAM
            with open(model_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        
                        # Calculate and emit the percentage
                        if total_size > 0:
                            percent = int((downloaded / total_size) * 100)
                            self.progress.emit(min(max(percent, 0), 100))
                            
            self.finished.emit(True, "Model downloaded successfully.")
            
        except requests.exceptions.RequestException as e:
            # Grabs a clean error message if the server blocks it or the wifi drops
            self.finished.emit(False, f"Network Error: {str(e)}")
        except Exception as e:
            self.finished.emit(False, f"System Error: {str(e)}")

class LibraryLoaderWorker(QThread):
    """Safely imports heavy ML libraries on a background thread so the UI loads instantly."""
    finished = pyqtSignal(bool, object, str)

    def run(self):
        try:
            # --- Image libraries (cv2 / numpy / PIL are slow to import cold) ---
            import cv2          # noqa: F401  — registers in sys.modules so callers can use it
            import numpy        # noqa: F401
            from PIL import Image  # noqa: F401

            # --- Lightweight CV pipelines (they import cv2/numpy themselves) ---
            from biopro.plugins.cytometrics.analysis.pipelines.otsu import OtsuPipeline
            from biopro.plugins.cytometrics.analysis.pipelines.watershed import WatershedPipeline

            # --- Heavy AI stack ---
            import torch
            from cellpose import models  # noqa: F401
            from biopro.plugins.cytometrics.analysis.pipelines.cellpose_pipeline import CellposePipeline

            pipelines = {
                "otsu":      OtsuPipeline(),
                "watershed": WatershedPipeline(),
                "cellpose":  CellposePipeline(),
            }
            self.finished.emit(True, pipelines, "All libraries loaded")
        except Exception as e:
            self.finished.emit(False, None, str(e))