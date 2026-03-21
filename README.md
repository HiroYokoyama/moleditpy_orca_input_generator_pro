# ORCA Input Generator Pro

[![Plugin for moleditpy](https://img.shields.io/badge/Plugin-moleditpy-blue.svg)](https://github.com/HiroYokoyama/moleditpy)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

An advanced **ORCA Input Generator** plugin for **moleditpy**, designed to streamline the creation of high-quality ORCA calculation files with a focus on usability, automation, and interactive 3D tools.

---

## Key Features

- **Intuitive Job Builder**: A tabbed interface for easy configuration of Methods, Basis Sets, Job Types, Solvation, and Properties.
- **Extensive Libraries**: Built-in support for a vast range of DFT (GGA, Hybrid, Meta, Range-Separated, Double Hybrid), Wavefunction (HF, MP2, Coupled Cluster, Multireference), and Semi-empirical methods.
- **Interactive Constraints & Scans**: Use the 3D viewer to pick 1-4 atoms and instantly define constraints (Position, Distance, Angle, Dihedral) or coordinate scans.
- **Real-time Preview**: Instantly see the generated job route and the full ORCA input file as you make changes.
- **Intelligent Automation**:
  - Automatically deduplicates keywords.
  - Handles specialized resource blocks like `%pal` and `%maxcore`.
  - Simplifies complex options like TD-DFT, Solvation (CPCM, SMD), and Dispersion corrections (D3BJ, D4).
- **Custom Syntax Highlighting**: Enhanced readability for `.inp` files with specialized coloring for keywords, blocks, and resource headers.

---

## Installation

1. Ensure you have MoleditPy installed.
2. Download [plugin](https://github.com/HiroYokoyama/moleditpy_orca_input_generator_pro) into your `moleditpy` plugins directory.
3. Restart `moleditpy`, and the **ORCA Input Generator Pro** will be available in the plugins menu.

---

## Usage

1. Open a molecule in `moleditpy`.
2. Launch the **ORCA Input Generator Pro** from the menu.
3. Use the **Keyword Builder** tabs to configure your calculation:
   - **Method/Basis**: Select your level of theory.
   - **Job Type**: Choose between Optimization, Frequency, NMR, etc.
   - **Constraints/Scan**: Select atoms in the 3D view to add constraints or scans.
4. Review the **Input Preview** to verify your setup.
5. Click **Apply to Job** and save your `.inp` file.

---

## Dependencies

- **Python 3.8+**
- **PyQt6**: For the modern graphical user interface.
- **RDKit**: For molecular geometry and property handling.
- **NumPy**: For coordinate calculations and analysis.

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## Author

**HiroYokoyama**
- Advanced Chem-Informatics and Computational Chemistry Tools.
