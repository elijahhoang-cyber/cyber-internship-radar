import contextlib
import io
import os
import unittest
from unittest.mock import patch
from notifications.check import main


class NotificationDiagnosticsTests(unittest.TestCase):
    @patch('notifications.check.notify_cover_letter', return_value=True)
    @patch('notifications.check.notify_discord', return_value=True)
    def test_synthetic_notifications_do_not_use_profile(self, alert, letter):
        with patch.dict(os.environ, {'DISCORD_WEBHOOK_URL': 'secret', 'RESUME_PROFILE_JSON': 'PRIVATE_MARKER'}), contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(), 0)
        self.assertNotIn('secret', output.getvalue())
        self.assertNotIn('PRIVATE_MARKER', str(alert.call_args) + str(letter.call_args))

    @patch('notifications.check.notify_discord', side_effect=RuntimeError('https://discord.com/api/webhooks/secret'))
    def test_failure_does_not_log_webhook(self, alert):
        with patch.dict(os.environ, {'DISCORD_WEBHOOK_URL': 'secret'}), contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(), 1)
        self.assertNotIn('https://discord', output.getvalue())

    def test_missing_secret_fails(self):
        with patch.dict(os.environ, {}, clear=True), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(), 1)
