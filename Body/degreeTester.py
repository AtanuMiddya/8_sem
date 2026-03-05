"""
Motor test GUI for your 6-axis arm + PCA9685 Arduino sketch.

- Provides a long, slow slider 0..360 degrees.
- Smoothly steps from current angle to target angle (so movement is slow and observable).
- Sends full 6-angle command "P<ang0>,<ang1>,...,<ang5>\n" to Arduino (your sketch expects this).
- Uses COM3 by default (change SERIAL_PORT if you use a different path).
- 'Home' button sends 'H' to move to home preset in your sketch.
- Avoids sending commands when no change is needed.

Author: ChatGPT (GPT-5 Thinking mini)
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading
import time
import serial

# ====== CONFIG ======
# Use port 3 as requested (Windows COM3). Change if you need a different path (e.g., '/dev/ttyUSB3').
SERIAL_PORT = "COM3"             # <-- change if necessary
BAUDRATE = 115200

# Initial known/home angles (these mirror values from your Arduino's homePositionArm())
INITIAL_ANGLES = [90, 85, 140, 150, 35, 90]

# Which servo channel we will control by default from the slider (0..5)
DEFAULT_CHANNEL = 0

# Movement smoothing parameters (adjust to make movement slower/faster)
STEP_DEGREES = 1         # degrees per micro-step (1 = fine)
STEP_DELAY = 0.05        # seconds between micro-steps (0.05 = slow). Increase to slow further.
DEADBAND = 0.3           # if difference less than this, treat as reached

# Slider visual length (longer makes easier to move slowly)
SLIDER_LENGTH = 900

# =====================

class ArmControllerApp:
    def __init__(self, root):
        self.root = root
        root.title("Arm Motor Tester — PCA9685 / Arduino (port 3)")

        # Serial setup
        self.ser = None
        self._connect_serial()

        # State
        self.angles = list(INITIAL_ANGLES)   # local copy of 6 servo angles
        self.target_angles = list(self.angles)
        self.channel = tk.IntVar(value=DEFAULT_CHANNEL)
        self.is_moving = threading.Event()
        self.stop_thread = False

        # Build UI
        self._build_ui()

        # Start background thread to move smoothly
        self.move_thread = threading.Thread(target=self._movement_loop, daemon=True)
        self.move_thread.start()

        self._log("Ready. Connected to: {}".format(SERIAL_PORT if self.ser else "NO SERIAL"))

    def _connect_serial(self):
        try:
            # Try COM3 first (user said port 3)
            self.ser = serial.Serial(SERIAL_PORT, BAUDRATE, timeout=0.5)
            time.sleep(0.1)
            # flush any initial data
            self.ser.reset_input_buffer()
            self.ser.reset_output_buffer()
        except Exception as e:
            self.ser = None
            print("Serial connection failed:", e)

    def _build_ui(self):
        frm = ttk.Frame(self.root, padding=12)
        frm.grid(sticky="nsew")

        # Channel selector
        ch_label = ttk.Label(frm, text="Servo channel (0..5):")
        ch_label.grid(row=0, column=0, sticky="w")
        ch_menu = ttk.Combobox(frm, textvariable=self.channel, values=[0,1,2,3,4,5], width=3, state="readonly")
        ch_menu.grid(row=0, column=1, sticky="w")
        ch_menu.bind("<<ComboboxSelected>>", self._on_channel_change)

        # Slider
        self.slider = ttk.Scale(frm, from_=0, to=360, orient="horizontal", length=SLIDER_LENGTH,
                                command=self._on_slider_move)
        self.slider.set(self.angles[self.channel.get()])  # reflect current angle
        self.slider.grid(row=1, column=0, columnspan=4, pady=(10,0))

        # Current value label
        self.val_label = ttk.Label(frm, text=f"Angle: {self.slider.get():.1f}°")
        self.val_label.grid(row=2, column=0, sticky="w", pady=(4,10))

        # Speed controls
        ttk.Label(frm, text="Step deg:").grid(row=3, column=0, sticky="w")
        self.step_spin = tk.Spinbox(frm, from_=1, to=10, width=4, command=self._update_step)
        self.step_spin.delete(0, "end"); self.step_spin.insert(0, str(STEP_DEGREES))
        self.step_spin.grid(row=3, column=1, sticky="w")

        ttk.Label(frm, text="Step delay (s):").grid(row=3, column=2, sticky="w")
        self.delay_spin = tk.Spinbox(frm, from_=0.01, to=1.0, increment=0.01, width=6, command=self._update_delay)
        self.delay_spin.delete(0, "end"); self.delay_spin.insert(0, f"{STEP_DELAY:.2f}")
        self.delay_spin.grid(row=3, column=3, sticky="w")

        # Buttons
        btn_frame = ttk.Frame(frm)
        btn_frame.grid(row=4, column=0, columnspan=4, pady=(10,0), sticky="w")
        home_btn = ttk.Button(btn_frame, text="Home (H)", command=self._send_home)
        home_btn.grid(row=0, column=0, padx=(0,8))
        send_btn = ttk.Button(btn_frame, text="Send current (P...)", command=self._send_current_angles)
        send_btn.grid(row=0, column=1, padx=(0,8))
        reconnect_btn = ttk.Button(btn_frame, text="Reconnect Serial", command=self._reconnect)
        reconnect_btn.grid(row=0, column=2, padx=(0,8))

        # Log output
        self.log = scrolledtext.ScrolledText(frm, width=110, height=12, state="disabled")
        self.log.grid(row=5, column=0, columnspan=4, pady=(12,0))

        # Clean up on close
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _log(self, text):
        ts = time.strftime("%H:%M:%S")
        self.log.configure(state="normal")
        self.log.insert("end", f"[{ts}] {text}\n")
        self.log.configure(state="disabled")
        self.log.see("end")
        print(text)

    def _on_channel_change(self, _ev=None):
        ch = self.channel.get()
        # update slider to show current angle for that channel
        cur = self.angles[ch]
        self.slider.set(cur)
        self._log(f"Selected channel {ch}. Slider set to {cur}°")

    def _on_slider_move(self, val):
        valf = float(val)
        self.val_label.config(text=f"Angle: {valf:.1f}°")
        ch = self.channel.get()
        # update target for that channel only
        self.target_angles[ch] = valf
        # signal movement thread
        self.is_moving.set()

    def _update_step(self):
        try:
            val = float(self.step_spin.get())
            global STEP_DEGREES
            STEP_DEGREES = max(0.1, val)
            self._log(f"STEP_DEGREES set to {STEP_DEGREES}")
        except Exception:
            pass

    def _update_delay(self):
        try:
            val = float(self.delay_spin.get())
            global STEP_DELAY
            STEP_DELAY = max(0.001, val)
            self._log(f"STEP_DELAY set to {STEP_DELAY}")
        except Exception:
            pass

    def _movement_loop(self):
        """
        Background thread that progressively moves each controlled channel from current to target angle
        in small micro-steps. Only sends serial commands when an actual micro-step occurs.
        """
        while not self.stop_thread:
            # Wait until there's something to do
            self.is_moving.wait(timeout=0.2)
            if self.stop_thread:
                break

            moved_any = False
            for ch in range(6):
                cur = float(self.angles[ch])
                tgt = float(self.target_angles[ch])
                diff = tgt - cur
                if abs(diff) > DEADBAND:
                    # move a small step toward target
                    step = STEP_DEGREES if diff > 0 else -STEP_DEGREES
                    # don't overshoot
                    if abs(step) > abs(diff):
                        step = diff
                    new = cur + step
                    # update local state
                    self.angles[ch] = new
                    moved_any = True
                    # we only update one channel at a time in each iteration to keep motion slow and visible
                    break

            if moved_any:
                # prepare integer angles for sending
                to_send = [int(round(a)) for a in self.angles]
                # send as the Arduino expects: "P90,85,140,150,35,90\n"
                cmd = "P" + ",".join(str(a) for a in to_send) + "\n"
                self._write_serial(cmd)
                self._log(f" Sent: {cmd.strip()} (local angles: {to_send})")

                # small delay to control speed
                time.sleep(STEP_DELAY)
                # continue loop (we'll move next step soon)
            else:
                # no channel needs movement right now
                self.is_moving.clear()
                time.sleep(0.05)

    def _write_serial(self, s):
        if not self.ser:
            self._log("Serial not connected: cannot send.")
            return
        try:
            self.ser.write(s.encode('utf-8'))
        except Exception as e:
            self._log("Serial write failed: " + str(e))
            self.ser = None

    def _send_home(self):
        if not self.ser:
            self._log("Serial not connected: cannot send Home.")
            return
        try:
            self.ser.write(b"H\n")
            self._log("Sent: H")
            # Update local angles to known home positions (match Arduino)
            self.angles = list(INITIAL_ANGLES)
            self.target_angles = list(self.angles)
            # update slider to reflect selected channel
            self.slider.set(self.angles[self.channel.get()])
        except Exception as e:
            self._log("Failed to send Home: " + str(e))

    def _send_current_angles(self):
        # Force send the current local angles to Arduino
        to_send = [int(round(a)) for a in self.angles]
        cmd = "P" + ",".join(str(a) for a in to_send) + "\n"
        self._write_serial(cmd)
        self._log(f"Sent (manual): {cmd.strip()}")

    def _reconnect(self):
        self._log("Attempting to reconnect serial...")
        try:
            if self.ser:
                try:
                    self.ser.close()
                except:
                    pass
                self.ser = None
            time.sleep(0.2)
            self._connect_serial()
            if self.ser:
                self._log("Reconnected.")
            else:
                self._log("Reconnect failed.")
        except Exception as e:
            self._log("Reconnect exception: " + str(e))

    def _on_close(self):
        if messagebox.askokcancel("Quit", "Close the motor tester?"):
            self.stop_thread = True
            self.is_moving.set()
            try:
                if self.ser:
                    self.ser.close()
            except:
                pass
            self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = ArmControllerApp(root)
    root.mainloop()
