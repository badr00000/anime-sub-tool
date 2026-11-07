"""
Animated Fluid Background Widget
Uses pure Qt drawing (QPainter and QRadialGradient) to create a premium, 
hardware-accelerated fluid background effect without large video files.
"""

import math
from PySide6.QtWidgets import QWidget
from PySide6.QtGui import QPainter, QRadialGradient, QColor, QBrush, QLinearGradient
from PySide6.QtCore import QTimer, Qt, QRectF

class FluidNode:
    def __init__(self, color: QColor, speed: float, radius: float, offset_x: float, offset_y: float):
        self.color = color
        self.speed = speed
        self.base_radius = radius
        self.offset_x = offset_x
        self.offset_y = offset_y

class AnimatedBackground(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        # Timer for 60FPS animation (1000/60 ~= 16ms)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update)
        self.timer.start(16)
        self.time_elapsed = 0.0

        # Define the colorful "fluid" nodes
        # Colors: Deep Purple, Indigo, Pink, Cyan
        self.nodes = [
            FluidNode(QColor(88, 28, 135, 120), speed=0.4, radius=0.8, offset_x=0.0, offset_y=0.0), # Deep Purple
            FluidNode(QColor(79, 70, 229, 140), speed=0.6, radius=0.7, offset_x=2.0, offset_y=1.5), # Indigo
            FluidNode(QColor(236, 72, 153, 90), speed=0.5, radius=0.9, offset_x=4.0, offset_y=3.0), # Pink
            FluidNode(QColor(14, 165, 233, 100), speed=0.3, radius=0.6, offset_x=1.0, offset_y=4.5), # Cyan
        ]

    def paintEvent(self, event):
        self.time_elapsed += 0.016
        
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        width = self.width()
        height = self.height()
        
        # 1. Base Background (Deep Navy/Black)
        base_grad = QLinearGradient(0, 0, width, height)
        base_grad.setColorAt(0.0, QColor(9, 9, 11))   # Very dark zinc
        base_grad.setColorAt(1.0, QColor(15, 23, 42)) # Deep slate
        painter.fillRect(self.rect(), QBrush(base_grad))
        
        # 2. Draw moving fluid nodes
        for node in self.nodes:
            # Calculate organic movement using sine waves
            t = self.time_elapsed * node.speed
            cx = (width / 2) + math.sin(t + node.offset_x) * (width * 0.4)
            cy = (height / 2) + math.cos(t * 0.8 + node.offset_y) * (height * 0.4)
            
            # Breathing radius
            r = (width + height) * 0.25 * node.base_radius
            r += math.sin(t * 1.5) * (r * 0.1)
            
            # Radial gradient for soft glowing edge (watercolor spread)
            grad = QRadialGradient(cx, cy, r)
            
            center_color = QColor(node.color)
            edge_color = QColor(node.color)
            edge_color.setAlpha(0) # Fade to transparent
            
            grad.setColorAt(0.0, center_color)
            grad.setColorAt(1.0, edge_color)
            
            painter.setBrush(QBrush(grad))
            painter.setPen(Qt.NoPen)
            # Draw a rect large enough to cover the radius
            painter.drawRect(QRectF(cx - r, cy - r, r * 2, r * 2))

        painter.end()
