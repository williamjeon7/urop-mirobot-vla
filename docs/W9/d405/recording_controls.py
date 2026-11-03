"""Live-preview recording buttons; motion and serial I/O stay in teleop."""
import queue
import threading

# RESET discards the current take and returns the arm to the initial pose. It
# sits in its own row so it is not clicked by mistake next to STOP.
RESETTABLE = ('ready', 'recording', 'ended')


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
            allowed = ((action == 'start' and self.state == 'ready') or
                       (action == 'end' and self.state == 'recording') or
                       (action == 'reset' and self.state in RESETTABLE))
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
        if event != cv2.EVENT_LBUTTONUP:
            return
        if self.image_height+12 <= y <= self.image_height+52:
            if 12 <= x < self.width//2-6:
                self.request('start')
            elif self.width//2+6 <= x < self.width-12:
                self.request('end')
        elif self.image_height+62 <= y <= self.image_height+102 and 12 <= x < self.width-12:
            self.request('reset')

    def draw(self, frame):
        import cv2
        self.image_height, self.width = frame.shape[:2]
        with self.lock:
            state = self.state
        view = cv2.copyMakeBorder(frame, 0, 160, 0, 0, cv2.BORDER_CONSTANT, value=(30, 30, 30))
        y = self.image_height
        for label, x0, x1, y0, y1, enabled, color in [
            ('START REC (F8)', 12, self.width//2-6, 12, 52, state == 'ready', (40, 140, 40)),
            ('STOP REC (F9)', self.width//2+6, self.width-12, 12, 52, state == 'recording', (50, 50, 190)),
            ('RESET - discard this take, back to initial pose', 12, self.width-12, 62, 102,
             state in RESETTABLE, (30, 110, 200)),
        ]:
            cv2.rectangle(view, (x0, y+y0), (x1, y+y1), color if enabled else (65, 65, 65), -1)
            cv2.putText(view, label, (x0+10, y+y0+26), cv2.FONT_HERSHEY_SIMPLEX, .55,
                        (255, 255, 255) if enabled else (150, 150, 150), 1, cv2.LINE_AA)
        messages = dict(homing='Homing / initial move... recording disabled',
                        ready='READY - prepare gripper, then click START REC',
                        recording='RECORDING - click STOP REC when finished',
                        ended='STOPPED - press q to save and exit',
                        starting='Starting recording...',
                        resetting='RESET - take discarded, returning to the initial pose...')
        cv2.putText(view, messages.get(state, state), (12, y+125), cv2.FONT_HERSHEY_SIMPLEX,
                    .48, (220, 220, 220), 1, cv2.LINE_AA)
        cv2.putText(view, 'Live view only before START and after STOP. Esc interrupts.',
                    (12, y+148), cv2.FONT_HERSHEY_SIMPLEX, .43, (180, 180, 180), 1, cv2.LINE_AA)
        return view
