"""Live-preview recording buttons; motion and serial I/O stay in teleop."""
import queue
import threading


class RecordingControls:
    def __init__(self):
        self.actions = queue.Queue()
        self.lock = threading.Lock()
        self.state = 'homing'
        self.width = self.image_height = 0

    def set_state(self, state):
        with self.lock:
            self.state = state

    def request(self, action):
        with self.lock:
            allowed = (action == 'start' and self.state == 'ready') or (action == 'end' and self.state == 'recording')
            if allowed:
                self.actions.put(action)

    def pending(self):
        result = []
        while True:
            try:
                result.append(self.actions.get_nowait())
            except queue.Empty:
                return result

    def mouse(self, event, x, y, flags, userdata):
        import cv2
        if event != cv2.EVENT_LBUTTONUP or not self.image_height+12 <= y <= self.image_height+52:
            return
        if 12 <= x < self.width//2-6:
            self.request('start')
        elif self.width//2+6 <= x < self.width-12:
            self.request('end')

    def draw(self, frame):
        import cv2
        self.image_height, self.width = frame.shape[:2]
        with self.lock:
            state = self.state
        view = cv2.copyMakeBorder(frame, 0, 112, 0, 0, cv2.BORDER_CONSTANT, value=(30, 30, 30))
        y = self.image_height
        for label, x0, x1, enabled, color in [
            ('START REC (F8)', 12, self.width//2-6, state == 'ready', (40, 140, 40)),
            ('STOP REC (F9)', self.width//2+6, self.width-12, state == 'recording', (50, 50, 190)),
        ]:
            cv2.rectangle(view, (x0, y+12), (x1, y+52), color if enabled else (65, 65, 65), -1)
            cv2.putText(view, label, (x0+10, y+38), cv2.FONT_HERSHEY_SIMPLEX, .55,
                        (255, 255, 255) if enabled else (150, 150, 150), 1, cv2.LINE_AA)
        messages = dict(homing='Homing / initial move... recording disabled',
                        ready='READY - prepare gripper, then click START REC',
                        recording='RECORDING - click STOP REC when finished',
                        ended='STOPPED - press q to save and exit (exit homing)',
                        starting='Starting recording...')
        cv2.putText(view, messages.get(state, state), (12, y+77), cv2.FONT_HERSHEY_SIMPLEX,
                    .48, (220, 220, 220), 1, cv2.LINE_AA)
        cv2.putText(view, 'Live view only before START and after STOP. Esc interrupts.',
                    (12, y+100), cv2.FONT_HERSHEY_SIMPLEX, .43, (180, 180, 180), 1, cv2.LINE_AA)
        return view
