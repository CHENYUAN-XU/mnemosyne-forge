"""Offline checks for the authoring, export, and asset workflows."""

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, patch
from urllib.parse import unquote

import httpx
from fastapi.testclient import TestClient

from app import auth, config, db, llm_client, oc_export, oc_image_critic, oc_image_gen, oc_session, server
from app.oc_models import OCDraft
from app.voice_providers.elevenlabs_provider import ElevenLabsProvider


class LLMRequestTests(unittest.IsolatedAsyncioTestCase):
    async def test_chat_url_accepts_versioned_and_unversioned_base_urls(self):
        requests = []

        def handler(request):
            requests.append(str(request.url))
            return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

        client = httpx.AsyncClient
        transport = httpx.MockTransport(handler)
        with patch.object(llm_client.httpx, "AsyncClient", side_effect=lambda **kw: client(transport=transport, **kw)):
            for base_url in ("https://example.test", "https://example.test/v1/"):
                await llm_client._call_api({}, {"base_url": base_url, "api_key": "test-key"})
        self.assertEqual(requests, ["https://example.test/v1/chat/completions"] * 2)


class ProjectWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(TemporaryDirectory()))
        self.enterContext(patch.object(config, "_config_cache", {
            "app": {"database_path": str(self.root / "forge.db"), "export_dir": str(self.root / "cards")},
            "voice": {"provider": "elevenlabs", "output_dir": str(self.root / "voices")},
        }))
        self.enterContext(patch.object(auth, "_auth_db_cache", self.root / "auth.db"))
        self.enterContext(patch.object(server.app, "dependency_overrides", {
            auth.current_user: lambda: {"id": 7, "role": "user"},
        }))
        self.client = self.enterContext(TestClient(server.app, raise_server_exceptions=False))
        now = "2026-01-01T00:00:00Z"
        db.create_session("owned", 7, "草稿", OCDraft(core_concept="守夜人", appearance="银发"), now, now)
        db.create_session("other", 8, "别人的草稿", OCDraft(), now, now)
        self.session = "/api/sessions/owned"

    def test_create_converse_resume_and_respect_locked_field(self):
        guide = AsyncMock(return_value="请继续描述角色。")
        designer = AsyncMock(return_value={"updates": {"name": "月见", "core_concept": "守夜人"}})
        with patch.object(oc_session, "extract_settings", designer), patch.object(oc_session, "generate_guide_message", guide):
            created = self.client.post("/api/sessions", json={"initial_idea": "一位守夜人"})
            self.assertEqual(created.status_code, 200, created.text)
            session = f"/api/sessions/{created.json()['session_id']}"
            updated = self.client.patch(session + "/draft", json={
                "updates": {"name": "映雪"}, "locked_fields": ["name"],
            })
            self.assertEqual(updated.status_code, 200, updated.text)
            designer.return_value = {"updates": {"name": "不可覆盖", "appearance": "银发"}}
            result = self.client.post(session + "/messages", json={"message": "她有银发"})
            self.assertEqual(result.status_code, 200, result.text)
        resumed = self.client.get(session + "/resume").json()
        self.assertEqual(resumed["draft"]["name"], "映雪")
        self.assertEqual(resumed["draft"]["appearance"], "银发")
        self.assertEqual([m["role"] for m in resumed["messages"]], ["user", "assistant", "user", "assistant"])
        self.assertEqual(self.client.get("/api/sessions/other/resume").status_code, 404)

    def test_manual_edit_validates_before_saving_and_updates_progress(self):
        url = self.session + "/draft"
        for payload in (
            {"updates": {"personality": "安静"}},
            {"updates": {"completion_score": 1}},
            {"locked_fields": "name"},
        ):
            with self.subTest(payload=payload):
                response = self.client.patch(url, json=payload)
                self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(self.client.get(url).json()["draft"]["personality"], [])
        response = self.client.patch(url, json={"updates": {"name": "映雪", "personality": ["安静"]}})
        self.assertEqual(response.status_code, 200, response.text)
        draft = response.json()["draft"]
        self.assertEqual(draft["completion_score"], 0.8)
        self.assertEqual(draft["missing_fields"], ["background"])
        self.assertEqual(draft["current_stage"], "background")
        self.assertEqual(db.get_session("owned")["title"], "映雪")

    def test_download_preserves_chinese_filename_and_uses_configured_export(self):
        self.client.patch(self.session + "/draft", json={"updates": {"name": '月见/"霜'}})
        with patch.object(oc_export, "_generate_missing_fields", AsyncMock(return_value={})):
            exported = self.client.post(self.session + "/export/card-v2")
        self.assertEqual(exported.status_code, 200, exported.text)
        with patch.object(oc_session, "export_session_card", AsyncMock(side_effect=AssertionError("unexpected regeneration"))):
            downloaded = self.client.get(self.session + "/export/download")
        self.assertEqual(downloaded.status_code, 200, downloaded.text)
        header = downloaded.headers["Content-Disposition"]
        self.assertEqual(unquote(header.split("filename*=UTF-8''")[1]), "月见__霜_card.json")
        self.assertEqual(downloaded.json()["data"]["name"], '月见/"霜')
        self.assertTrue((self.root / "cards" / "owned_角色卡.md").is_file())
        self.assertEqual(self.client.get("/api/sessions/other/export/download").status_code, 404)

    def test_image_retry_passes_negative_prompt_and_preserves_asset_origin(self):
        generate = AsyncMock(return_value={"ok": True, "image_path": "exports/images/test.png", "seed": 42})
        with patch.object(oc_image_gen, "generate_character_image", generate), patch.object(
            oc_image_critic, "critique_image_prompt", AsyncMock(return_value={})
        ):
            response = self.client.post(self.session + "/image-candidates", json={
                "provider": "seedream", "retry_style": "anime", "retry_prompt": "silver hair",
                "retry_negative_prompt": "watermark",
            })
        self.assertEqual(response.status_code, 200, response.text)
        generate.assert_awaited_once()
        self.assertEqual(generate.await_args.kwargs["negative_prompt"], "watermark")
        candidate = response.json()["candidates"][0]
        locked = self.client.post(self.session + "/visual-canon-lock", json={"asset_id": candidate["asset_id"]})
        self.assertEqual(locked.status_code, 200, locked.text)
        canon = locked.json()["canon"]
        self.assertEqual(canon["negative_prompt"], "watermark")
        self.assertEqual(canon["seed"], 42)
        self.assertEqual(db.list_assets("owned", "image_locked")[0]["provider"], "seedream")

    def test_asset_type_mismatch_leaves_existing_selection_intact(self):
        voice_id = db.insert_asset("owned", "voice_identity", "elevenlabs", "test-voice", selected=True)
        image_id = db.insert_asset("owned", "image_candidate", "seedream", "exports/images/test.png")
        response = self.client.post(self.session + f"/assets/{image_id}/select", json={"asset_type": "voice_identity"})
        self.assertEqual(response.status_code, 404, response.text)
        self.assertEqual([asset["id"] for asset in db.list_assets("owned", selected=True)], [voice_id])

    def test_optional_services_are_rejected_before_generation_when_disabled(self):
        flags = self.client.get("/api/features").json()
        self.assertFalse(flags["world_enabled"])
        self.assertFalse(flags["bridge_enabled"])
        with patch.object(oc_export, "export_card_v2", AsyncMock()) as export:
            self.assertEqual(self.client.post(self.session + "/import-to-mnemosyne").status_code, 400)
            export.assert_not_awaited()
        self.assertEqual(self.client.post(self.session + "/world").status_code, 400)

    def test_visual_canon_can_only_bind_an_image_from_its_own_session(self):
        other_path = "exports/images/other.png"
        other_id = db.insert_asset("other", "image_candidate", "seedream", other_path)
        own_path = "exports/images/owned.png"
        own_id = db.insert_asset("owned", "image_candidate", "seedream", own_path)
        url = self.session + "/visual-canon-lock"
        self.assertEqual(self.client.post(url, json={"image_path": other_path}).status_code, 404)
        self.assertEqual(self.client.post(url, json={"asset_id": other_id}).status_code, 404)
        response = self.client.post(url, json={"asset_id": own_id, "image_path": other_path})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["canon"]["image_path"], own_path)
        self.assertEqual(self.client.post(url, json={"image_path": own_path}).status_code, 200)

    def test_voice_regeneration_uses_new_parameters_and_favorite_saves_them(self):
        db.save_voice_profile("owned", json.dumps({"provider_hints": {
            "elevenlabs_voice_id": "test-voice",
            "performance_units": [{"clean_text": "你好。", "speed": "normal"}],
        }}))
        synth = AsyncMock(return_value=str(self.root / "voices" / "test.mp3"))
        with patch.object(ElevenLabsProvider, "text_to_speech", synth):
            first = self.client.post(self.session + "/voice-unit-regenerate", json={"unit_index": 0, "speed": "fast"})
            second = self.client.post(self.session + "/voice-unit-regenerate", json={"unit_index": 0, "speed": "slow"})
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(second.status_code, 200, second.text)
        calls = synth.await_args_list
        self.assertEqual(calls[0].args[2]["provider_hints"]["performance_units"][0]["speed"], "fast")
        self.assertEqual(calls[1].args[2]["provider_hints"]["performance_units"][0]["speed"], "slow")
        self.assertNotEqual(calls[0].args[3], calls[1].args[3])
        favorite = self.client.post(self.session + "/voice-unit-favorite", json={"unit_index": 0})
        self.assertEqual(favorite.status_code, 200, favorite.text)
        self.assertEqual(db.get_voice_profile("owned")["unit_favorites"][0]["unit"]["speed"], "slow")


if __name__ == "__main__":
    unittest.main()
