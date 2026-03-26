"""Background workers and threading utilities for CytoMetrics."""

import logging
import urllib.request
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
        # Cellpose expects models to live in the user's home directory
        model_dir = Path.home() / ".cellpose" / "models"
        model_dir.mkdir(parents=True, exist_ok=True)
        model_path = model_dir / "cyto3"

        # The official direct-download URL for the Cyto3 model weights
        url = "https://www.cellpose.org/models/cyto3"

        def reporthook(block_num, block_size, total_size):
            if total_size > 0:
                downloaded = block_num * block_size
                percent = int((downloaded / total_size) * 100)
                # Cap at 100 just in case of weird byte math
                self.progress.emit(min(max(percent, 0), 100))

        try:
            urllib.request.urlretrieve(url, model_path, reporthook)
            self.finished.emit(True, "Model downloaded successfully.")
        except Exception as e:
            self.finished.emit(False, str(e))