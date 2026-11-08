import unittest
from unittest.mock import patch

from server.policy_client import PolicyClient


class StaleRetryTest(unittest.TestCase):
    def test_late_frames_are_fetched_again(self):
        client = PolicyClient("http://127.0.0.1:1")
        answers = [RuntimeError("Camera/robot observation is stale or unsynchronized"),
                   RuntimeError("Bridge /observation: Camera frame is stale or unsynchronized: age=0.6s"),
                   {"cart6": [1, 2, 3, 0, 0, 0]}]

        def once():
            answer = answers.pop(0)
            if isinstance(answer, Exception):
                raise answer
            return answer

        with patch.object(client, "_observation_once", side_effect=once), patch("server.policy_client.time.sleep"):
            self.assertEqual(client.observation()["cart6"][0], 1)
        self.assertEqual(client.stale_retries, 2)

    def test_persistent_staleness_and_other_errors_still_stop(self):
        client = PolicyClient("http://127.0.0.1:1")
        client.RETRY_BUDGET_S = 0.05
        with patch.object(client, "_observation_once", side_effect=RuntimeError("stale")), \
                self.assertRaisesRegex(RuntimeError, "stale"):
            client.observation()
        with patch.object(client, "_observation_once", side_effect=RuntimeError("Bridge robot fault: x")) as once, \
                self.assertRaisesRegex(RuntimeError, "fault"):
            client.observation()
        self.assertEqual(once.call_count, 1)



class CommandRetryTest(unittest.TestCase):
    def test_dropped_connection_resends_the_same_request_id(self):
        client = PolicyClient("http://127.0.0.1:1")
        seen = []

        def request(path, payload=None, timeout_s=None):
            seen.append(payload["request_id"])
            if len(seen) == 1:
                raise RuntimeError("Cannot reach bridge /command: timed out")
            if len(seen) == 2:
                raise RuntimeError("Bridge /command: Robot must be Idle before a policy command: Run")
            return dict(request_id=payload["request_id"], command=payload["command"], acknowledged=True)

        with patch.object(client, "_request", side_effect=request), patch("server.policy_client.time.sleep"):
            client.command("G0 X1 Y2 Z3 A0 B0 C0")
        self.assertEqual(len(set(seen)), 1)  # never a new id, so never a second motion
        self.assertEqual(client.command_retries, 2)

    def test_robot_fault_is_not_retried(self):
        client = PolicyClient("http://127.0.0.1:1")
        with patch.object(client, "_request", side_effect=RuntimeError("Bridge /command: Idle pose differs")) as call, \
                self.assertRaises(RuntimeError):
            client.command("G90")
        self.assertEqual(call.call_count, 1)


if __name__ == "__main__":
    unittest.main()
