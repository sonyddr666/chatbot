import unittest

from src.core.agent.schemas import ToolResult
from src.core.chat_attachments import ChatAttachmentArtifact


class AgentToolResultTest(unittest.TestCase):
    def test_model_payload_accepts_generated_attachment_artifact(self):
        artifact = ChatAttachmentArtifact(
            id="attachment-1",
            user_id=1,
            filename="generated.png",
            relative_path="chat/generated.png",
            content_type="image/png",
            extension=".png",
            kind="image",
            file_size=42,
            checksum="checksum",
            extracted_text="",
            is_truncated=False,
        )

        payload = ToolResult(
            call_id="image-1",
            name="image_generate",
            status="completed",
            content="Imagem gerada",
            attachments=[artifact],
        ).model_payload()

        self.assertEqual(payload["attachments"], [{
            "filename": "generated.png",
            "relative_path": "chat/generated.png",
            "content_type": "image/png",
        }])


if __name__ == "__main__":
    unittest.main()
