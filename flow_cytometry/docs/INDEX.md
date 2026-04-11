# Flow Cytometry Module Documentation

Welcome to the comprehensive documentation suite for the BioPro Flow Cytometry module. 

This directory contains resources tailored for both researchers using the application and developers maintaining the backend codebase.

## Documentation Index

### 1. [User Guide](01_USER_GUIDE.md)
The operational manual for scientists. Covers data loading, workflow templates, defining single-stain/FMO roles, managing compensation through the GUI, and exploring data dynamically with the visualization engine.

### 2. [Mathematics](02_MATHEMATICS.md)
The rigorous mathematical foundation of the module. Covers the definitions and usage of the Parks 2006 Logicle Transform (biexponential scaling) and the linear algebra derivations of Spillover Matrices and Inverse Compensation computation.

### 3. [Architecture](03_ARCHITECTURE.md)
Developer documentation on the architectural design points. Covers the Unidirectional State (`FlowState`), the strict MVC separation between `ui/` widgets and `analysis/` math, the BioPro Plugin integration contract, and the dependency on the C-extended `FlowKit`.

### 4. [Core Algorithms](04_CORE_ALGORITHMS.md)
Explicit, line-by-line breakdowns of the critical operations processing raw byte arrays into UI renders. Detailed explanations of Hexbin visual rendering offsets, `calculate_spillover_matrix` isolation logic, and the mechanics of applying N-dimensional subset matrices via NumPy.
