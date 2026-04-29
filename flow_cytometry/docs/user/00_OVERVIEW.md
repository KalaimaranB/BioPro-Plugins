# Flow Cytometry Module — Overview

Welcome to the **BioPro Flow Cytometry Module**, a high-performance analysis suite designed for the rigorous demands of modern immunology and cell biology. 

This module provides a seamless bridge between raw instrument data and publication-ready insights, combining the speed of hardware-accelerated rendering with the precision of validated scientific algorithms.

## 🔬 Core Capabilities

*   **Massive Scale**: Analyze datasets with millions of events without UI lag, thanks to our optimized hexbin density engine.
*   **Scientific Rigor**: Built-in support for the **Parks 2006 Logicle Transform**, ensuring proper visualization of compensated data and negative populations.
*   **Hierarchical Gating**: Create complex, nested gating strategies with Rectangle, Polygon, Ellipse, and Quadrant tools.
*   **Automated Compensation**: Calculate spillover matrices from single-stain controls or extract embedded matrices directly from FCS metadata.
*   **Publication Quality**: Export high-resolution (300 DPI) bitmaps or vector-based (PDF/SVG) figures with a single click.

## 👥 Targeted Audiences

### For Scientists & Researchers
If your goal is to analyze data, quantify populations, and generate figures for manuscripts, start with the **[User Documentation](file:///Users/kalaimaranbalasothy/.biopro/plugins/flow_cytometry/docs/user/01_GETTING_STARTED.md)**.
*   Learn how to load data and map markers.
*   Master the gating and compensation tools.
*   Understand the scientific logic behind our scaling and transforms.

### For Developers & Engineers
If you are looking to extend the module, integrate new algorithms, or understand the underlying state machine, head to the **[Developer Documentation](file:///Users/kalaimaranbalasothy/.biopro/plugins/flow_cytometry/docs/developer/00_ARCHITECTURE_OVERVIEW.md)**.
*   Explore the `FlowState` model and BioPro Core integration.
*   Understand the FSM-driven UI engine.
*   Reference the API for custom gating or transformation logic.

---

## 🚀 Quick Links
- **[Getting Started Guide](file:///Users/kalaimaranbalasothy/.biopro/plugins/flow_cytometry/docs/user/01_GETTING_STARTED.md)**
- **[Full Analysis Guide](file:///Users/kalaimaranbalasothy/.biopro/plugins/flow_cytometry/docs/user/02_ANALYSIS_GUIDE.md)**
- **[Technical Architecture](file:///Users/kalaimaranbalasothy/.biopro/plugins/flow_cytometry/docs/developer/00_ARCHITECTURE_OVERVIEW.md)**
