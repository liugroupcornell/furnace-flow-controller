# Furnace and Mass Flow Controller GUI

A custom Python-based GUI application for controlling a Yokogawa UP150 furnace and an MKS 647B mass flow controller. This tool allows dynamic stage-based temperature control, gas flow regulation, real-time temperature plotting, and recipe saving/loading to support advanced thermal processing experiments.

## Features

- **Dynamic Heating Stage Control**: Configure multiple heating stages with customizable temperature, ramp time, hold time, and flow rate.
- **Real-Time Monitoring**: Live temperature and flow rate display with real-time plotting.
- **Recipe Management**: Save and load multi-stage heating profiles (JSON format).
- **Safety Features**:
  - Prevents program exit if the furnace is too hot.
  - Automatic cooling and post-annealing flow control.
- **Mass Flow Control**: Full integration with MKS 647B for range, flow rate, and valve control.
- **Export Capabilities**: Export plot data to CSV.
- **Pause/Clear Plotting**: User-controlled real-time plotting operations.
- **Open/Close Valve Controls**: Direct manual valve operation.

## System Requirements

- Python 3.8+
- PyQt5
- PyVISA
- Matplotlib
- Compatible with RS-232 and RS-485 interfaces.

## Installation

1. **Clone this repository:**

```bash
git clone https://github.com/liugroupcornell/furnace-flow-controller.git
cd furnace-flow-controller
```

2. **Install required Python packages:**

```bash
pip install -r requirements.txt
```

3. **Connect Devices:**

   - Yokogawa UP150 (via RS-485, PC-link)
   - MKS 647B (via RS-232)

4. **Run the GUI:**

```bash
python src/main.py
```

## File Overview

| File              | Description                                      |
| ----------------- | ------------------------------------------------ |
| `src/main.py`         | Main GUI logic and application entry point       |
| `src/MainWindow.ui`   | PyQt5 UI for the main control window             |
| `src/StageWidget.ui`  | PyQt5 UI for individual heating stage widgets    |
| `src/up150.py`        | Driver for the Yokogawa UP150 furnace controller |
| `src/mks647b.py`      | Driver for the MKS 647B mass flow controller     |
| `manual/` | Documentation for Yokogawa UP150 and MKS 647B hardware, with communication protocols |
| `requirements.txt`| Python package dependencies for easy installation|
| `README.md`       | Project description and setup instructions       |
| `flowchart.mmd`   | Mermaid flowchart of GUI thread/timer structure      |
| `LICENSE`   | MIT License      |

## Usage Notes

- Recipes are saved/loaded in JSON format.
- Real-time temperature data can be exported as CSV.
- Safety checks prevent accidental shutdown during high-temperature operations.
- Maximum 8 custom heating stages supported per recipe.
- Current GUI interface only supports one flow controller in one gas supply pipe as the our real lab setting, but it is expandable to more pipes in codes.

## Development and Contributions

Developed by the **Xiaomeng Liu Lab** at **Cornell University** for internal research purposes. We welcome collaborations and improvements via pull requests.

## License

[MIT License](LICENSE)

## Acknowledgments

- **Xiaomeng Liu Lab**, Cornell University
- Developed by **Aareeb Jamil**, undergraduate research assistant, as part of the lab's research initiatives
- Based on Yokogawa UP150 and MKS 647B hardware manuals.

---

## Contact

- Aareeb Jamil: aj632 [at] cornell [dot] edu
- Yiming Sun: ys2289 [at] cornell [dot] edu