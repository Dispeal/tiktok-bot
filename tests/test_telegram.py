import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import httpx

from clipbot.telegram import TelegramBot, TelegramError


class TelegramTests(unittest.IsolatedAsyncioTestCase):
    async def test_send_video_multipart_and_rate_limit_retry(self):
        calls = []

        def handler(request: httpx.Request):
            calls.append(request)
            if len(calls) == 1:
                return httpx.Response(200, json={"ok": False, "error_code": 429,
                                                 "description": "Too Many Requests", "parameters": {"retry_after": 0}})
            return httpx.Response(200, json={"ok": True, "result": {"message_id": 1}})

        bot = TelegramBot("123:abc", http=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
        with tempfile.TemporaryDirectory() as d, mock.patch("asyncio.sleep", new=mock.AsyncMock()):
            p = Path(d) / "v.mp4"
            p.write_bytes(b"videobytes")
            result = await bot.send_video(-1001, p, "Tonight, @x went live.", 12.4)
        self.assertEqual(result, {"message_id": 1})
        self.assertEqual(len(calls), 2)
        body = calls[1].content
        self.assertIn(b"videobytes", body)  # file re-sent on retry
        self.assertIn(b"Tonight, @x went live.", body)
        self.assertTrue(str(calls[1].url).endswith("/bot123:abc/sendVideo"))

    async def test_error_raises(self):
        def handler(request):
            return httpx.Response(400, json={"ok": False, "description": "Bad Request: chat not found"})

        bot = TelegramBot("t", http=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
        with self.assertRaises(TelegramError) as cm:
            await bot.send_message(-1, "hi", reply_to=3)
        self.assertIn("chat not found", str(cm.exception))

    async def test_send_message_json(self):
        seen = {}

        def handler(request):
            seen.update(json.loads(request.content))
            return httpx.Response(200, json={"ok": True, "result": {}})

        bot = TelegramBot("t", http=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
        await bot.send_message(-1, "hi")
        self.assertEqual(seen, {"chat_id": -1, "text": "hi", "disable_web_page_preview": True})
