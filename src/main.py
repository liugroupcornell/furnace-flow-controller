import sys
import datetime
import json
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas, NavigationToolbar2QT as NavigationToolbar
import matplotlib.pyplot as plt
from PyQt5.QtCore import QTimer, QThread, pyqtSignal
from PyQt5.QtWidgets import QMainWindow, QApplication, QVBoxLayout, QWidget, QFileDialog, QMessageBox
from PyQt5 import uic

from up150 import UP150 
from mks647b import MKS647B

# Constants
REFRESH_TIME = 40000  # Data refresh interval in milliseconds (40 seconds)
POST_ANNEAL_FLOW_RATE = 6  # Post-anneal flow rate setpoint (6 SCCM)
MAX_PLOT_LENGTH = 121000  # Max number of data points to retain for plotting

class StageWidget(QWidget):
    """
    Widget representing a single heating stage in the furnace profile.
    Each stage allows user input for temperature setpoint, ramp time, hold time,
    flow rate, and flow range.
    """

    def __init__(self):
        super().__init__()
        self.ui = uic.loadUi("StageWidget.ui", self)  # Load StageWidget UI file

        # Available MFC flow ranges based on MKS647B specification
        self.range_list = [
            "1 SCCM", "2 SCCM", "5 SCCM", "10 SCCM", "20 SCCM", "50 SCCM",
            "100 SCCM", "200 SCCM", "500 SCCM",
            "1 SLM", "2 SLM", "5 SLM", "10 SLM", "20 SLM", "50 SLM",
            "100 SLM", "200 SLM", "500 SLM",
            "1 SCFH", "2 SCFH", "5 SCFH", "10 SCFH", "20 SCFH",
            "50 SCFH", "100 SCFH", "200 SCFH", "500 SCFH",
            "1 SCFM", "2 SCFM", "5 SCFM", "10 SCFM", "20 SCFM", "50 SCFM",
            "100 SCFM", "200 SCFM", "500 SCFM"
        ]
        self.ui.rangeComboBox.addItems(self.range_list)  # Populate combo box
        self.ui.rangeComboBox.setCurrentText("500 SCCM")  # Default range

        self.ui.rangeComboBox.currentTextChanged.connect(self.update_flow_spinbox)
        self.update_flow_spinbox()  # Initialize spinbox limits and suffix
        self.ui.rangeComboBox.setEnabled(False)  # Range selection disabled (fixed)

    def update_flow_spinbox(self):
        """Adjust flow spinbox suffix and maximum based on selected range."""
        range_text = self.ui.rangeComboBox.currentText()
        parts = range_text.split()
        if len(parts) == 2:
            try:
                value = float(parts[0])
                units = parts[1]
                max_flow = value * 1.1  # Allow 10% margin above range
                self.ui.flowRateSpinBox.setSuffix(f" {units}")
                self.ui.flowRateSpinBox.setMaximum(max_flow)
            except ValueError:
                pass  # Ignore if parsing fails

    def set_stage_number(self, number):
        """Update the label to show the stage number."""
        self.ui.stageLabel.setText(f"Stage {number}")

    def get_selected_range(self):
        """Return selected flow range as string (e.g., '500 SCCM')."""
        return self.ui.rangeComboBox.currentText()

    def get_units(self):
        """Return the unit string extracted from the flow range."""
        range_text = self.get_selected_range()
        for unit in ["SCCM", "SLM", "SCFM", "SCFH", "SCMM"]:
            if unit in range_text:
                return unit
        return "Unknown"

    def get_flow_setpoint(self):
        """Return the user-specified flow rate setpoint."""
        return self.ui.flowRateSpinBox.value()


class FurnaceWorker(QThread):
    """
    Background thread to poll furnace and MFC status periodically,
    avoiding blocking the GUI.
    Emits signal with updated data to MainWindow.
    """

    dataReady = pyqtSignal(int, int, int, float, int, int)  # segment, time_left, temp, flow, range_code, setpoint

    def __init__(self, furnace, mfc):
        super().__init__()
        self.furnace = furnace
        self.mfc = mfc
        self._running = True

    def run(self):
        """Periodically poll devices and emit data signal."""
        while self._running:
            try:
                segment = self.furnace.get_segment_number()
                time_left = self.furnace.get_segment_time_left()
                temp = self.furnace.get_current_temp()
                flow = self.mfc.get_actual_flow(1)
                range_code = self.mfc.get_range(1)
                setpoint = self.furnace.get_current_setpoint()
            except Exception as e:
                print("Error in worker:", e)
                continue
            self.dataReady.emit(segment, time_left, temp, flow, range_code, setpoint)
            self.msleep(REFRESH_TIME)  # Wait before next poll

    def stop(self):
        """Stop the polling thread safely."""
        self._running = False
        self.wait()

class MainWindow(QMainWindow):
    """
    Main application window managing UI, device communication,
    process control, and data logging.
    """

    def __init__(self):
        super().__init__()
        self.ui = uic.loadUi("MainWindow.ui", self)  # Load main window UI

        # Layout stretch setup for plot and controls
        self.ui.verticalLayoutMain.setStretch(0, 1)  # scrollArea
        self.ui.verticalLayoutMain.setStretch(1, 1)  # Add/Remove buttons
        self.ui.verticalLayoutMain.setStretch(2, 1)  # Recipe buttons
        self.ui.verticalLayoutMain.setStretch(3, 1)  # Start/Stop + labels
        self.ui.verticalLayoutMain.setStretch(4, 3)  # Plot gets triple

        # Initialize devices
        self.furnace = UP150()
        self.mfc = MKS647B()

        # MFC initial settings
        self.mfc.set_flow_setpoint(1, 0)
        self.mfc.set_gas_menu(0)
        #self.mfc.set_gas_setpoint(1, 1, 0)
        self.mfc.open_valve(1)
        self.mfc.open_valve(0)

        # Stage management
        self.stages = []
        self.stage_layout = self.ui.scrollAreaWidgetContents.layout()
        self.ui.addStageButton.clicked.connect(self.add_stage)
        self.ui.removeStageButton.clicked.connect(self.remove_stage)
        self.current_stage_index = -1  # Track current segment

        # Heating state
        self.heating_in_progress = False
        self.post_anneal_flow = False

        # Recipe file handling
        self.ui.loadRecipeButton.clicked.connect(self.load_recipe)
        self.ui.saveRecipeButton.clicked.connect(self.save_recipe)


        # Furnace start/stop buttons + Close gas flow valve button
        self.ui.startButton.clicked.connect(self.start_furnace)
        self.ui.stopButton.clicked.connect(self.stop_furnace)
        self.ui.closeValveButton.clicked.connect(lambda: self.mfc.close_valve(1))


        # Temperature plot setup
        self.temp_times = []
        self.temp_values = []
        self.init_plot()
        self.plot_paused = False
        self.ui.pausePlotButton.clicked.connect(self.toggle_plot_pause)
        self.ui.clearPlotButton.clicked.connect(self.clear_plot_data)
        self.ui.exportPlotButton.clicked.connect(self.export_plot_data)

        # Plot updating timer
        self.plot_timer = QTimer(self)
        self.plot_timer.timeout.connect(self.update_temperature_plot)
        self.plot_timer.start(2*REFRESH_TIME)

        # Data polling worker thread
        self.worker = FurnaceWorker(self.furnace, self.mfc)
        self.worker.dataReady.connect(self.handle_furnace_data)
        self.worker.start()

        # Elapsed time tracker
        self.start_time = None   # Time when furnace started
        self.elapsed_timer = QTimer(self)  # Timer to update elapsed time
        self.elapsed_timer.timeout.connect(self.update_elapsed_time)

        '''
        # DATA LOG FOR TESTING
        self.data_log_file = f"furnace_log_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        with open(self.data_log_file, 'w') as f:
            f.write("Timestamp,Segment,Stage,Mode,TimeLeft,Temp,Flow,FlowSetpoint,FlowUnits,SetpointTemp\n")
        '''
            
    def init_plot(self):
        """Set up matplotlib plot for real-time temperature display."""
        self.figure, self.ax = plt.subplots()
        self.canvas = FigureCanvas(self.figure)
        self.toolbar = NavigationToolbar(self.canvas, self)
        plot_layout = QVBoxLayout()
        plot_layout.addWidget(self.toolbar)
        plot_layout.addWidget(self.canvas)
        self.ui.plotWidget.setLayout(plot_layout)
        self.ax.set_title("Furnace Temperature Over Time")
        self.ax.set_xlabel("Time")
        self.ax.set_ylabel("Temperature (°C)")

    def update_temperature_plot(self):
        """Update temperature vs time plot."""
        if self.plot_paused:
            return  # Skip drawing plot, but data keeps collecting

        if len(self.temp_times) > MAX_PLOT_LENGTH:
            self.temp_times = self.temp_times[-MAX_PLOT_LENGTH:]
            self.temp_values = self.temp_values[-MAX_PLOT_LENGTH:]

        self.ax.clear()
        self.ax.plot(self.temp_times, self.temp_values, color='tab:red')
        self.ax.set_title("Furnace Temperature Over Time")
        self.ax.set_xlabel("Time")
        self.ax.set_ylabel("Temperature (°C)")
        self.figure.autofmt_xdate()
        self.canvas.draw()

    def toggle_plot_pause(self):
        """Pause or resume real-time plotting."""
        self.plot_paused = not self.plot_paused
        if self.plot_paused:
            self.ui.pausePlotButton.setText("Resume Plotting")
        else:
            self.ui.pausePlotButton.setText("Pause Plotting")

    def clear_plot_data(self):
        """Clear all temperature plot data."""
        self.temp_times.clear()
        self.temp_values.clear()
        self.update_temperature_plot()

    def export_plot_data(self):
        """Export temperature plot data to CSV file."""
        if not self.temp_times or not self.temp_values:
            QMessageBox.information(self, "No Data", "There is no temperature data to export.")
            return

        filename, _ = QFileDialog.getSaveFileName(self, "Export Temperature Data", "", "CSV Files (*.csv)")
        if filename:
            try:
                with open(filename, 'w') as file:
                    file.write("Time,Temperature\n")
                    for time_point, temp in zip(self.temp_times, self.temp_values):
                        file.write(f"{time_point.strftime('%Y-%m-%d %H:%M:%S')},{temp}\n")
                QMessageBox.information(self, "Success", f"Temperature data exported to:\n{filename}")
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to export data:\n{e}")


    def handle_furnace_data(self, segment, time_left, temp, flow, range_code, setpoint):
        """
        Slot to handle data emitted by FurnaceWorker.
        Updates GUI labels, logs data to CSV, and manages MFC setpoints dynamically.

        Parameters:
            segment (int): Current furnace segment number (0-16).
            time_left (int): Time remaining for the current segment in minutes.
            temp (float): Current furnace temperature in °C.
            flow (float): Measured flow rate from the MFC.
            range_code (int): MFC flow range code (to be decoded into readable range).
            setpoint (int): Current furnace temperature setpoint.
        """

        # Calculate which stage is active, based on the segment number
        # (each user stage maps to two furnace segments: ramp and hold)
        stage = 1 + (segment - 1) // 2  # stage 1 corresponds to segment 1 & 2, etc.
        if segment == 0:
            mode = "Resting"  # Idle mode
        elif segment % 2 == 1:
            mode = "Ramping"  # Currently in a ramp segment
            # Add the hold time of the next segment to the time_left for completeness
            next_len = self.furnace.get_tm_length(segment + 1)
            time_left += next_len
        else:
            mode = "Holding"  # Currently in a hold segment

        # Update GUI labels to reflect furnace state
        self.ui.modeLabel.setText(f"Mode: {mode}")
        self.ui.stageLabel.setText(f"Current Stage: {stage}")
        self.ui.timeLeftLabel.setText(f"Stage Time Left: {time_left} min")
        self.ui.setpointLabel.setText(f"Setpoint: {setpoint} °C")

        # Estimate and display finish time only if heating is active
        remaining_minutes = time_left
        if self.heating_in_progress:
            # Sum up the ramp and hold times for all future stages
            for s in self.stages[stage:]:  # remaining stages
                remaining_minutes += s.ui.rampTimeSpinBox.value()
                remaining_minutes += s.ui.holdTimeSpinBox.value()

            finish_time = datetime.datetime.now() + datetime.timedelta(minutes=remaining_minutes)
            self.ui.finishTimeLabel.setText(f"Estimated Finish: {finish_time.strftime('%Y-%m-%d %H:%M')}")
        else:
            self.ui.finishTimeLabel.setText("Estimated Finish: -")

        # Decode MFC range code into human-readable units (e.g., "1 SLM")
        try:
            range_text = self.mfc.REVERSE_RANGE_DICT[range_code]  # Look up range code
            units = range_text.split()[1]  # Extract units part (e.g., "SLM")
        except Exception as e:
            print("Error decoding MFC range code:", e)
            units = "?"  # Default if decoding fails

        # Update flow rate display in the GUI
        self.ui.flowLabel.setText(f"Flow Rate: {flow:.3f} {units}")

        # Store temperature and time for real-time plotting
        now = datetime.datetime.now()
        self.temp_times.append(now)
        self.temp_values.append(temp)

        '''
        # DATA LOG FOR TESTING
        flow_setpoint = self.mfc.get_flow_setpoint(1)
        with open(self.data_log_file, 'a') as f:
            f.write(f"{now.strftime('%Y-%m-%d %H:%M:%S')},{segment},{stage},{mode},{time_left},{temp},{flow},{flow_setpoint},{units},{setpoint}\n")
        '''
            
        # Determine stage index for internal tracking
        stage_index = (segment - 1) // 2

        # If the stage has changed since the last check, update MFC settings
        if self.current_stage_index != stage_index:
            if 0 <= stage_index < len(self.stages):
                stage_widget = self.stages[stage_index]
                range_text = stage_widget.get_selected_range()
                range_value, units = range_text.split()  # e.g., "1 SLM"
                setpoint = stage_widget.get_flow_setpoint()  # User-defined setpoint for this stage

                try:
                    self.mfc.set_range(1, int(range_value), units)  # Set new flow range
                    self.mfc.set_flow_setpoint(1, setpoint)  # Set new flow setpoint
                    # self.mfc.set_gas_setpoint(1, 1, setpoint)
                    print(f"Set MFC for Stage {stage_index+1}: Range {range_value} {units}, Flow {setpoint}")
                except Exception as e:
                    print(f"Error setting MFC for Stage {stage_index+1}: {e}")

                self.current_stage_index = stage_index  # Remember new stage index

        # -------- Furnace Completion Checks --------
        if self.heating_in_progress:
            if stage > len(self.stages):
                # Furnace reached an unused segment -- stop the process
                self.stop_furnace()
                print("Furnace stopped due to unused segment")
            elif self.current_stage_index != -1 and stage_index == -1:
                # Furnace completed all defined segments and wrapped back to 0 -- stop process
                self.stop_furnace()
                print("Furnace stopped due to stage_index wraparound")

        # -------- Post-Annealing Flow Logic --------
        if temp < 30 and self.post_anneal_flow:
            # When temperature drops below 30°C after process end:
            # Reset MFC flow and close valve
            self.mfc.set_range(1, 500, "SCCM")  # Reset to safe range
            self.mfc.set_flow_setpoint(1, 0)    # Set flow to zero
            #self.mfc.set_gas_setpoint(1, 1, 0)
            self.mfc.close_valve(1)             # Close the valve
            self.post_anneal_flow = False       # Reset post-anneal flag
            print("Post-anneal flow turned off due to temperature < 30C")

    def add_stage(self):
        """
        Add a new heating stage widget to the stage layout.
        Limits the total number of stages to 8.
        """
        if len(self.stages) >= 8:
            return
        stage = StageWidget()
        self.stages.append(stage)
        self.stage_layout.addWidget(stage)
        self.update_stage_labels()

    def remove_stage(self):
        """
        Remove the last added heating stage widget from the GUI.
        Prevents removal if there are no stages.
        """
        if self.stages:
            last_stage = self.stages.pop()
            self.stage_layout.removeWidget(last_stage)
            last_stage.deleteLater()
            self.update_stage_labels()

    def update_stage_labels(self):
        """Update all stage widget labels to reflect their current index."""
        for i, stage in enumerate(self.stages, start=1):
            stage.set_stage_number(i)

    def start_furnace(self):
        """
        Start the furnace process using the user-defined stages.
        Configures each segment of the furnace based on the parameters
        (temperature, ramp time, hold time) specified in the GUI.
        Disables UI controls to prevent changes during heating.
        """
        self.furnace.set_start_setpoint()  # Set initial furnace start setpoint (default 25°C)

        # Disable buttons to prevent user modification during operation
        self.ui.addStageButton.setEnabled(False)
        self.ui.removeStageButton.setEnabled(False)
        self.ui.loadRecipeButton.setEnabled(False)
        self.ui.saveRecipeButton.setEnabled(False)
        self.ui.startButton.setEnabled(False)
        self.ui.closeValveButton.setEnabled(False)

        try:
            # Configure furnace segments based on the defined stages
            for i, stage_widget in enumerate(self.stages):
                temp = stage_widget.ui.temperatureSpinBox.value()
                ramp_time = stage_widget.ui.rampTimeSpinBox.value()
                hold_time = stage_widget.ui.holdTimeSpinBox.value()

                ramp_segment = i * 2 + 1  # Ramp segments are odd-numbered
                hold_segment = i * 2 + 2  # Hold segments are even-numbered

                self.furnace.set_sp_setpoint(ramp_segment, temp)
                self.furnace.set_sp_setpoint(hold_segment, temp)
                self.furnace.set_tm_length(ramp_segment, ramp_time)
                self.furnace.set_tm_length(hold_segment, hold_time)

                # Disable stage inputs to prevent modification while running
                stage_widget.ui.temperatureSpinBox.setEnabled(False)
                stage_widget.ui.rampTimeSpinBox.setEnabled(False)
                stage_widget.ui.holdTimeSpinBox.setEnabled(False)
                stage_widget.ui.flowRateSpinBox.setEnabled(False)

            # Clear unused furnace segments to ensure they don't interfere
            total_used_segments = len(self.stages) * 2
            for seg in range(total_used_segments + 1, 17):  # Segments 1 to 16
                self.furnace.set_sp_setpoint(seg, 0)
                self.furnace.set_tm_length(seg, 0)
                print(f"Cleared unused segment {seg}: set to 0C, 0 min.")

            self.furnace.set_run()  # Start the furnace operation
            self.mfc.open_valve(1)  # Ensure valve 1 is open
            self.heating_in_progress = True

            self.start_time = datetime.datetime.now()  # Record start time
            self.elapsed_timer.start(1000)  # Update every second

            print("Furnace started with user-defined temperature profile.")

        except Exception as e:
            print("Failed to start furnace:", e)

    def stop_furnace(self):
        """
        Stop the furnace process safely.
        Resets the furnace controller, re-enables GUI controls,
        and sets the post-annealing flow to prevent pressure drop.
        """
        try:
            self.furnace.set_reset()  # Stop and reset furnace
            self.current_stage_index = -1
            self.heating_in_progress = False
            self.elapsed_timer.stop()  # Stop elapsed time update

            # Re-enable buttons after stopping
            self.ui.addStageButton.setEnabled(True)
            self.ui.removeStageButton.setEnabled(True)
            self.ui.loadRecipeButton.setEnabled(True)
            self.ui.saveRecipeButton.setEnabled(True)
            self.ui.startButton.setEnabled(True)
            self.ui.closeValveButton.setEnabled(True)

            # Re-enable all input fields in each stage
            for stage_widget in self.stages:
                stage_widget.ui.temperatureSpinBox.setEnabled(True)
                stage_widget.ui.rampTimeSpinBox.setEnabled(True)
                stage_widget.ui.holdTimeSpinBox.setEnabled(True)
                stage_widget.ui.flowRateSpinBox.setEnabled(True)

            # Set post-anneal flow to prevent pressure drop
            self.mfc.set_range(1, 500, "SCCM")
            self.mfc.set_flow_setpoint(1, POST_ANNEAL_FLOW_RATE)
            print(f'Post anneal flow set to {POST_ANNEAL_FLOW_RATE} SCCM')
            #self.mfc.set_gas_setpoint(1, 1, POST_ANNEAL_FLOW_RATE)
            self.post_anneal_flow = True

            print("Furnace stopped.")

        except Exception as e:
            print("Failed to stop furnace:", e)

    
    def save_recipe(self):
        """
        Save the current stage configuration to a JSON file.
        Allows the user to export a furnace 'recipe' for reuse.
        """
        data = {"stages": []}  # Container for stage data
        for stage_widget in self.stages:
            stage_data = {
                "temperature": stage_widget.ui.temperatureSpinBox.value(),
                "ramp_time": stage_widget.ui.rampTimeSpinBox.value(),
                "hold_time": stage_widget.ui.holdTimeSpinBox.value(),
                "flow_rate": stage_widget.ui.flowRateSpinBox.value(),
                "range": stage_widget.get_selected_range()
            }
            data["stages"].append(stage_data)

        filename, _ = QFileDialog.getSaveFileName(self, "Save Recipe", "", "JSON Files (*.json)")
        if filename:
            with open(filename, "w") as f:
                json.dump(data, f, indent=4)
            print(f"Recipe saved to {filename}")

    def load_recipe(self):
        """
        Load a furnace 'recipe' from a JSON file.
        Configures the stage widgets based on the loaded data.
        """
        filename, _ = QFileDialog.getOpenFileName(self, "Load Recipe", "", "JSON Files (*.json)")
        if filename:
            # Open the selected file
            with open(filename, "r") as f:
                # Load the data from the file
                data = json.load(f)

            # Remove existing stages
            while self.stages:
                self.remove_stage()

            # Create new stage widgets based on the loaded data
            for stage_data in data.get("stages", []):
                self.add_stage()
                stage_widget = self.stages[-1]
                stage_widget.ui.temperatureSpinBox.setValue(stage_data["temperature"])
                stage_widget.ui.rampTimeSpinBox.setValue(stage_data["ramp_time"])
                stage_widget.ui.holdTimeSpinBox.setValue(stage_data["hold_time"])
                stage_widget.ui.rangeComboBox.setCurrentText(stage_data["range"])
                stage_widget.update_flow_spinbox()  # Update flow spinbox max/suffix
                stage_widget.ui.flowRateSpinBox.setValue(stage_data["flow_rate"])
                
            print(f"Recipe loaded from {filename}")

    def update_elapsed_time(self):
        """
        Update the elapsed time display in the GUI.
        Shows the total duration since the furnace process started.
        """
        if self.start_time:
            elapsed = datetime.datetime.now() - self.start_time
            minutes, seconds = divmod(elapsed.seconds, 60)
            hours, minutes = divmod(minutes, 60)
            self.ui.elapsedTimeLabel.setText(f"Total Time Elapsed: {hours:02d}:{minutes:02d}:{seconds:02d}")

    def closeEvent(self, event):
        """
        Override the window close event to ensure safe shutdown.
        Prevents the user from closing the application while the furnace is hot (>30°C),
        unless they explicitly confirm to force-quit.
        """
        try:
            temp = self.furnace.get_current_temp()
            if temp > 30:
                # Warn user and ask for confirmation to force-close
                reply = QMessageBox.question(
                    self,
                    "Confirm Exit",
                    f"Furnace temperature is {temp} °C.\n"
                    "It is recommended to wait until the furnace cools below 30 °C before closing.\n\n"
                    "Do you still want to exit?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No
                )

                if reply == QMessageBox.Yes:
                    # User chose to force-close
                    self.worker.stop()
                    self.furnace.close()
                    self.mfc.close()
                    event.accept()
                else:
                    # User cancelled the close action
                    event.ignore()
                return
        except Exception as e:
            print("Error checking furnace temperature on close:", e)

        # Safe to close (temperature below threshold)
        self.worker.stop()
        self.furnace.close()
        self.mfc.close()
        event.accept()


# This block ensures the code only runs if this script is executed directly
# and not if it is imported as a module in another script.
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
