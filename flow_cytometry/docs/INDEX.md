# Flow Cytometry Module Documentation

Welcome to the documentation suite for the BioPro Flow Cytometry module. This directory is organized into two primary silos to serve both researchers and software engineers.

## 📚 Documentation Map

### 📖 User Documentation (For Scientists)
Targeted at researchers performing data analysis and generating publication-quality figures.
1.  **[Overview](file:///Users/kalaimaranbalasothy/.biopro/plugins/flow_cytometry/docs/user/00_OVERVIEW.md)**
    *   Module capabilities and value proposition.
2.  **[Getting Started Guide](file:///Users/kalaimaranbalasothy/.biopro/plugins/flow_cytometry/docs/user/01_GETTING_STARTED.md)**
    *   Tutorial for loading FCS data, basic navigation, and creating your first gate.
3.  **[Advanced Analysis Guide](file:///Users/kalaimaranbalasothy/.biopro/plugins/flow_cytometry/docs/user/02_ANALYSIS_GUIDE.md)**
    *   In-depth workflows for compensation, hierarchical gating, and high-fidelity rendering.
4.  **[Scientific Principles](file:///Users/kalaimaranbalasothy/.biopro/plugins/flow_cytometry/docs/user/03_SCIENTIFIC_LOGIC.md)**
    *   Educational guide to the "Cell to Software" pipeline and the math behind Logicle transforms.

### 🛠️ Developer Documentation (For Engineers)
Targeted at software engineers maintaining, testing, or extending the plugin.
1.  **[Architecture Overview](file:///Users/kalaimaranbalasothy/.biopro/plugins/flow_cytometry/docs/developer/00_ARCHITECTURE_OVERVIEW.md)**
    *   Software design, FlowState model, and BioPro core integration.
2.  **[API Reference](file:///Users/kalaimaranbalasothy/.biopro/plugins/flow_cytometry/docs/developer/01_API_REFERENCE.md)**
    *   Technical specification of the Gating, Transforms, and Scaling modules.
3.  **[UI Engine & FSM](file:///Users/kalaimaranbalasothy/.biopro/plugins/flow_cytometry/docs/developer/02_UI_ENGINE.md)**
    *   Details on the FlowCanvas state machine and asynchronous rendering pipeline.
4.  **[Testing & QA Guide](file:///Users/kalaimaranbalasothy/.biopro/plugins/flow_cytometry/docs/developer/03_TESTING_AND_QA.md)**
    *   Verification steps and automated test suite details.

---

## 🔬 Core References
- **Parks, D.R., et al. (2006)**. A new "Logicle" display method. *Cytometry Part A*.
- **FlowKit Documentation**: https://github.com/whitews/FlowKit
