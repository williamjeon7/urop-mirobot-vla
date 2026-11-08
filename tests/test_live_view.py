import json
import threading
import time
import unittest
import urllib.request

import numpy as np

from server.live_view import attach


class LiveViewTest(unittest.TestCase):
    def test_observations_are_streamed_without_extra_bridge_requests(self):
        class Client:
            calls = 0

            def observation(self):
                Client.calls += 1
                return dict(rgb=np.zeros((480, 640, 3), np.uint8), cart6=[198.7, 0, 230.4, 0, 0, 0])

        client = Client()
        view = attach(client, 0, lambda o: f"red | Z {o['cart6'][2]:.0f}", log=lambda _: None)
        try:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            client.observation()
            self.assertEqual(json.loads(opener.open(view.url + "/status").read())["text"], "red | Z 230")
            stream = opener.open(view.url + "/stream", timeout=3)
            self.assertTrue(stream.read(60).startswith(b"--frame\r\nContent-Type: image/jpeg"))
            self.assertEqual(Client.calls, 1)  # the viewer itself never asks the bridge
        finally:
            view.close()


if __name__ == "__main__":
    unittest.main()
