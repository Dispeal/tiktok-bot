import unittest
from pathlib import Path

from clipbot.captions import TELEGRAM_CAPTION_LIMIT, Captioner, clean_caption, finalize_caption
from clipbot.commands import CommandHandler
from clipbot.config import CaptionSettings, ConfigError, parse_settings
from clipbot.db import Database
from clipbot.poller import MAX_ATTEMPTS, Poller, build_routes
from clipbot.tiktok import Video

ENV = {"A_TOKEN": "111:aaa", "B_TOKEN": "222:bbb"}
RAW = {
    "clients": {
        "client_a": {
            "bot_token_env": "A_TOKEN",
            "admins": [42],
            "channels": {
                "main": {"chat_id": -1001, "accounts": ["@Clipper1", "clipper2"]},
                "alt": {"chat_id": "@altchannel", "accounts": ["clipper2"]},
            },
        },
        "client_b": {
            "bot_token_env": "B_TOKEN",
            "credit_clipper": False,
            "channels": {"main": {"chat_id": "-1002", "accounts": ["clipper2", "clipper3"]}},
        },
    }
}


def settings(**overrides):
    s = parse_settings(RAW, ENV)
    for k, v in overrides.items():
        setattr(s, k, v)
    return s


class FakeSource:
    def __init__(self):
        self.catalog = {}
        self.fail_download = set()
        self.downloads = 0

    async def list_recent(self, username, limit):
        if username not in self.catalog:
            raise RuntimeError("blocked")
        return list(self.catalog[username])[:limit]

    async def download(self, video, dest_dir):
        self.downloads += 1
        if video.id in self.fail_download:
            raise RuntimeError("download error")
        path = Path(dest_dir) / f"{video.id}.mp4"
        path.write_bytes(b"x")
        video.file_path = path
        return video


class FakeBot:
    def __init__(self, fail=False):
        self.sent = []
        self.fail = fail
        self.username = "testbot"

    async def send_video(self, chat_id, path, caption, duration=None):
        if self.fail:
            raise RuntimeError("chat not found")
        self.sent.append((chat_id, path.name, caption))

    async def send_message(self, chat_id, text, reply_to=None):
        self.sent.append((chat_id, None, text))


def vid(user, id, ts=0, desc="lol #kick"):
    return Video(id=id, username=user, url=f"https://www.tiktok.com/@{user}/video/{id}", description=desc, timestamp=ts)


class ConfigTests(unittest.TestCase):
    def test_parses_and_normalizes(self):
        s = settings()
        a = s.clients["client_a"]
        self.assertEqual(a.channels["main"].accounts, ["clipper1", "clipper2"])
        self.assertEqual(a.channels["alt"].chat_id, "@altchannel")
        self.assertEqual(s.clients["client_b"].channels["main"].chat_id, -1002)
        self.assertEqual(a.admins, {42})
        self.assertTrue(a.examples)  # default example caption

    def test_missing_token(self):
        with self.assertRaises(ConfigError):
            parse_settings(RAW, {"A_TOKEN": "x"})

    def test_same_token_rejected(self):
        with self.assertRaises(ConfigError):
            parse_settings(RAW, {"A_TOKEN": "x", "B_TOKEN": "x"})


class RoutingTests(unittest.TestCase):
    def test_routes_and_overrides(self):
        db = Database(":memory:")
        s = settings()
        routes = build_routes(s, db)
        self.assertEqual({(r.client, r.channel) for r in routes["clipper2"]},
                         {("client_a", "main"), ("client_a", "alt"), ("client_b", "main")})
        db.set_account_override("client_a", "main", "newguy", removed=False)
        db.set_account_override("client_a", "alt", "clipper2", removed=True)
        db.set_account_override("client_a", "nochannel", "ghost", removed=False)
        routes = build_routes(s, db)
        self.assertIn("newguy", routes)
        self.assertNotIn("ghost", routes)
        self.assertNotIn(("client_a", "alt"), {(r.client, r.channel) for r in routes["clipper2"]})


class StubCaptioner:
    ai_enabled = False

    async def caption(self, video, client):
        return f"[{client.name}] {video.description}"


class PollerTests(unittest.IsolatedAsyncioTestCase):
    def make(self, **kw):
        self.db = Database(":memory:")
        self.source = FakeSource()
        self.bots = {"client_a": FakeBot(), "client_b": FakeBot()}
        self.poller = Poller(settings(**kw), self.db, self.source, StubCaptioner(), self.bots)

    async def test_first_run_seeds_then_posts_only_new(self):
        self.make()
        self.source.catalog = {"clipper1": [vid("clipper1", "1")], "clipper2": [vid("clipper2", "2")],
                               "clipper3": [vid("clipper3", "3")]}
        stats = await self.poller.run_cycle()
        self.assertEqual(stats.posted, 0)
        self.assertEqual(self.source.downloads, 0)

        self.source.catalog["clipper2"] = [vid("clipper2", "5", ts=20), vid("clipper2", "4", ts=10), vid("clipper2", "2")]
        stats = await self.poller.run_cycle()
        self.assertEqual(stats.new_videos, 2)
        self.assertEqual(stats.posted, 6)  # 2 videos x 3 channels
        self.assertEqual(self.source.downloads, 2)  # downloaded once per video, not per channel
        a_sent = self.bots["client_a"].sent
        self.assertEqual([s[1] for s in a_sent], ["4.mp4", "4.mp4", "5.mp4", "5.mp4"])  # oldest first
        self.assertTrue(a_sent[0][2].startswith("[client_a]"))
        self.assertTrue(self.bots["client_b"].sent[0][2].startswith("[client_b]"))

        stats = await self.poller.run_cycle()
        self.assertEqual(stats.posted, 0)

    async def test_failing_account_does_not_block_others(self):
        self.make()
        self.source.catalog = {"clipper1": [], "clipper3": []}
        stats = await self.poller.run_cycle()
        self.assertEqual(stats.accounts_failed, 1)
        self.assertEqual(stats.accounts_checked, 2)
        self.assertTrue(self.poller.status.errors)

    async def test_download_failure_retries_then_gives_up(self):
        self.make()
        self.source.catalog = {"clipper1": [], "clipper2": [], "clipper3": []}
        await self.poller.run_cycle()
        self.source.catalog["clipper1"] = [vid("clipper1", "9")]
        self.source.fail_download.add("9")
        for _ in range(MAX_ATTEMPTS):
            self.assertFalse(self.db.is_seen("clipper1", "9"))
            await self.poller.run_cycle()
        self.assertTrue(self.db.is_seen("clipper1", "9"))

    async def test_failed_channel_retried_without_duplicating(self):
        self.make()
        self.source.catalog = {"clipper1": [], "clipper2": [], "clipper3": []}
        await self.poller.run_cycle()
        self.bots["client_b"].fail = True
        self.source.catalog["clipper2"] = [vid("clipper2", "7")]
        await self.poller.run_cycle()
        self.assertEqual(len(self.bots["client_a"].sent), 2)
        self.bots["client_b"].fail = False
        await self.poller.run_cycle()
        self.assertEqual(len(self.bots["client_a"].sent), 2)  # not re-sent
        self.assertEqual(len(self.bots["client_b"].sent), 1)
        self.assertTrue(self.db.is_seen("clipper2", "7"))


class CaptionTests(unittest.IsolatedAsyncioTestCase):
    def test_finalize_adds_credit_and_respects_limit(self):
        client = settings().clients["client_a"]
        out = finalize_caption("x" * 2000, vid("clipper1", "1"), client)
        self.assertLessEqual(len(out), TELEGRAM_CAPTION_LIMIT)
        self.assertTrue(out.endswith("🎥 @clipper1"))
        self.assertEqual(finalize_caption("hi", vid("c", "1"), settings().clients["client_b"]), "hi")

    def test_clean_caption_strips_quotes(self):
        self.assertEqual(clean_caption('"Tonight, @x did a thing."'), "Tonight, @x did a thing.")

    async def test_without_api_key_uses_original_caption(self):
        cap = Captioner(CaptionSettings(enabled=True), api_key="")
        self.assertFalse(cap.ai_enabled)
        out = await cap.caption(vid("clipper1", "1", desc="crazy moment #kick"), settings().clients["client_b"])
        self.assertEqual(out, "crazy moment #kick")


class CommandTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = Database(":memory:")
        s = settings()
        self.bot = FakeBot()
        self.poller = Poller(s, self.db, FakeSource(), StubCaptioner(), {"client_a": self.bot})
        self.handler = CommandHandler(self.bot, s.clients["client_a"], self.db, self.poller)

    def msg(self, text, user=42, chat_type="private"):
        return {"update_id": 1, "message": {"message_id": 5, "text": text, "from": {"id": user},
                                            "chat": {"id": 99, "type": chat_type}}}

    async def test_add_remove_and_accounts(self):
        await self.handler.handle(self.msg("/add main @NewClipper"))
        self.assertIn("Following @newclipper in main", self.bot.sent[-1][2])
        await self.handler.handle(self.msg("/accounts"))
        self.assertIn("@newclipper", self.bot.sent[-1][2])
        await self.handler.handle(self.msg("/remove main newclipper"))
        await self.handler.handle(self.msg("/accounts"))
        self.assertNotIn("@newclipper", self.bot.sent[-1][2])
        await self.handler.handle(self.msg("/add nope @x"))
        self.assertIn("Unknown channel", self.bot.sent[-1][2])

    async def test_non_admin_blocked_but_helpers_work(self):
        await self.handler.handle(self.msg("/add main @x", user=7))
        self.assertIn("not an admin", self.bot.sent[-1][2])
        self.assertEqual(self.db.account_overrides("client_a"), [])
        await self.handler.handle({"update_id": 2, "channel_post": {"message_id": 1, "text": "/chatid",
                                                                    "chat": {"id": -1009, "type": "channel"}}})
        self.assertIn("-1009", self.bot.sent[-1][2])

    async def test_status(self):
        await self.handler.handle(self.msg("/status"))
        self.assertIn("Accounts followed: 2", self.bot.sent[-1][2])


if __name__ == "__main__":
    unittest.main()


class FakeMessages:
    def __init__(self, text, stop_reason="end_turn"):
        self.calls = []
        self.text = text
        self.stop_reason = stop_reason

    async def create(self, **kwargs):
        from types import SimpleNamespace
        self.calls.append(kwargs)
        return SimpleNamespace(stop_reason=self.stop_reason,
                               content=[SimpleNamespace(type="thinking", thinking=""),
                                        SimpleNamespace(type="text", text=self.text)])


class AICaptionTests(unittest.IsolatedAsyncioTestCase):
    def make(self, text, stop_reason="end_turn", model="claude-opus-5-5"):
        from types import SimpleNamespace
        cap = Captioner(CaptionSettings(enabled=True, model=model), api_key="")
        self.msgs = FakeMessages(text, stop_reason)
        cap._client = SimpleNamespace(messages=self.msgs, beta=SimpleNamespace(messages=self.msgs))
        return cap

    async def test_generates_in_house_style(self):
        cap = self.make('"Live on stream, @adinross reacted to the #kick moment."')
        client = settings().clients["client_a"]
        out = await cap.caption(vid("clipper1", "1", desc="adin crazy #kick @adinross"), client)
        self.assertEqual(out, "Live on stream, @adinross reacted to the #kick moment.\n\n🎥 @clipper1")
        call = self.msgs.calls[0]
        self.assertEqual(call["model"], "claude-opus-5-5")
        self.assertEqual(call["fallbacks"], "default")
        self.assertEqual(call["output_config"], {"effort": "low"})
        self.assertIn("#VogueWorld", call["system"])  # example caption included
        self.assertIn("adin crazy #kick @adinross", call["messages"][0]["content"][-1]["text"])

    async def test_refusal_falls_back_to_original(self):
        cap = self.make("", stop_reason="refusal")
        out = await cap.caption(vid("c", "1", desc="original text"), settings().clients["client_b"])
        self.assertEqual(out, "original text")

    async def test_haiku_skips_effort_and_fallbacks(self):
        cap = self.make("ok", model="claude-haiku-4-5")
        await cap.caption(vid("c", "1"), settings().clients["client_b"])
        self.assertNotIn("output_config", self.msgs.calls[0])
        self.assertNotIn("fallbacks", self.msgs.calls[0])
