import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class FrontendStreamingUiTest(unittest.TestCase):
    def test_http_stream_sends_response_mode_and_displays_status(self):
        api = (ROOT / "frontend/src/lib/api.ts").read_text(encoding="utf-8")
        store = (ROOT / "frontend/src/hooks/useChatStore.ts").read_text(encoding="utf-8")
        message = (ROOT / "frontend/src/components/ChatMessage.tsx").read_text(encoding="utf-8")

        self.assertIn("response_mode: responseMode", api)
        self.assertIn("'normal' | 'thinking' | 'live'", api)
        self.assertIn("streamStatus: chunk.text || 'Processando...'", store)
        self.assertIn("status || 'Aguardando o primeiro token...'", message)

    def test_reasoning_remains_visible_while_content_streams(self):
        app = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")
        message = (ROOT / "frontend/src/components/ChatMessage.tsx").read_text(encoding="utf-8")

        self.assertIn("const hasReasoning = !!message.reasoning", message)
        self.assertIn("msg.id === messages[messages.length - 1]?.id", app)
        self.assertIn("onStatus: status =>", app)

    def test_completed_skill_activity_is_visible_with_source_links(self):
        api = (ROOT / "frontend/src/lib/api.ts").read_text(encoding="utf-8")
        app = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")
        block = (ROOT / "frontend/src/components/SkillActivityBlock.tsx").read_text(encoding="utf-8")

        self.assertIn("type: 'skill_activity'", api)
        self.assertIn("chunk.type === 'skill_activity'", app)
        self.assertIn("Ferramentas e Skills", block)
        self.assertIn("fontes verificadas", block)
        self.assertIn("Consulta usada", block)
        self.assertIn("Prompt usado", block)
        self.assertIn('target="_blank"', block)

    def test_input_remains_editable_while_model_is_busy(self):
        app = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")
        chat_input = (ROOT / "frontend/src/components/ChatInput.tsx").read_text(encoding="utf-8")

        self.assertIn("busy={isLoading}", app)
        self.assertNotIn("disabled={busy}", chat_input)
        self.assertIn("Continue digitando", chat_input)
        self.assertIn("value={input}", chat_input)
        self.assertIn("if (!busy && !isSubmitting)", chat_input)

    def test_sse_parser_preserves_model_spaces_and_multiline_data(self):
        api = (ROOT / "frontend/src/lib/api.ts").read_text(encoding="utf-8")

        self.assertIn("dataLines.join('\\n')", api)
        self.assertIn("dataLines.push(line.slice(5).replace(/^ /, ''))", api)
        self.assertIn("type: 'content', text: raw", api)
        self.assertNotIn("const raw = line.slice(6).trim()", api)

    def test_chat_input_supports_files_without_automatic_rag(self):
        chat_input = (ROOT / "frontend/src/components/ChatInput.tsx").read_text(encoding="utf-8")
        store = (ROOT / "frontend/src/hooks/useChatStore.ts").read_text(encoding="utf-8")

        self.assertIn("type=\"file\"", chat_input)
        self.assertNotIn("accept={ACCEPTED_FILES}", chat_input)
        self.assertIn("window.addEventListener('drop'", chat_input)
        self.assertIn("Workspace/chat/uploads", chat_input)
        self.assertIn("api.uploadChatAttachments", store)
        self.assertIn("attachments.map(attachment => attachment.id)", store)
        self.assertIn("filesRef.current = next", chat_input)
        self.assertNotIn("setFiles(current => {", chat_input)
        self.assertIn("onPaste={handlePaste}", chat_input)
        self.assertIn("event.clipboardData.items", chat_input)
        self.assertIn("item.getAsFile()", chat_input)
        self.assertIn("clipboardImageFile", chat_input)
        self.assertIn("PendingImageThumbnail", chat_input)
        self.assertIn("URL.revokeObjectURL", chat_input)
        self.assertIn("if (!pastedImages.length) return", chat_input)

    def test_chat_images_have_thumbnail_and_accessible_lightbox(self):
        message = (ROOT / "frontend/src/components/ChatMessage.tsx").read_text(encoding="utf-8")

        self.assertIn("URL.createObjectURL(blob)", message)
        self.assertIn("createPortal(", message)
        self.assertIn('role="dialog"', message)
        self.assertIn("event.key === 'Escape'", message)
        self.assertIn("event.currentTarget === event.target", message)
        self.assertIn("Ampliar", message)
        self.assertIn("URL.revokeObjectURL", message)

    def test_html_and_markdown_code_blocks_have_safe_preview(self):
        message = (ROOT / "frontend/src/components/ChatMessage.tsx").read_text(encoding="utf-8")

        self.assertIn("CodePreviewModal", message)
        self.assertIn("rawLanguage === 'html'", message)
        self.assertIn("rawLanguage === 'markdown'", message)
        self.assertIn('sandbox="allow-scripts"', message)
        self.assertIn("Content-Security-Policy", message)
        self.assertIn('referrerPolicy="no-referrer"', message)
        self.assertIn("Prévia Markdown", message)
        self.assertIn("navigator.clipboard.writeText(code)", message)

    def test_saved_trace_is_restored_when_conversation_reopens(self):
        store = (ROOT / "frontend/src/hooks/useChatStore.ts").read_text(encoding="utf-8")

        self.assertIn("reasoning: m.reasoning || ''", store)
        self.assertIn("skillActivities: Array.isArray(m.skill_activities)", store)

    def test_provider_fallback_is_a_persistent_compact_tag(self):
        message = (ROOT / "frontend/src/components/ChatMessage.tsx").read_text(encoding="utf-8")
        jobs = (ROOT / "src/core/chat_jobs.py").read_text(encoding="utf-8")

        self.assertIn("Falhou: {activity.failed_provider", message)
        self.assertIn("Redirecionado: {activity.target_provider", message)
        self.assertIn('"name": "provider_fallback"', jobs)
        self.assertIn('await _add_event(job_id, "skill"', jobs)

    def test_chat_jobs_are_primary_and_reattachable(self):
        api = (ROOT / "frontend/src/lib/api.ts").read_text(encoding="utf-8")
        store = (ROOT / "frontend/src/hooks/useChatStore.ts").read_text(encoding="utf-8")

        self.assertIn("createChatJob", api)
        self.assertIn("after_id=${Math.max(0, afterId)}", api)
        self.assertIn("await api.createChatJob", store)
        self.assertIn("resumePersistedJob", store)
        self.assertIn("reasoningEffort: ReasoningEffort", api)

    def test_provider_names_use_compact_lobehub_icons(self):
        selector = (ROOT / "frontend/src/components/ModelSelector.tsx").read_text(encoding="utf-8")
        message = (ROOT / "frontend/src/components/ChatMessage.tsx").read_text(encoding="utf-8")
        icon = (ROOT / "frontend/src/components/AIProviderIcon.tsx").read_text(encoding="utf-8")

        self.assertIn("@lobehub/icons", icon)
        self.assertIn("WorkersAI", icon)
        self.assertIn("Gemini", icon)
        self.assertIn("import.meta.glob('/node_modules/@lobehub/icons/es/*/components/Color.js'", icon)
        self.assertIn("import.meta.glob('/node_modules/@lobehub/icons/es/*/components/Mono.js'", icon)
        self.assertIn("lobeExports.SubModel", icon)
        self.assertNotIn("models.dev/logos", icon)
        self.assertNotIn("lucide-react", icon)
        self.assertIn("<AIProviderIcon", selector)
        self.assertIn("displayedModelName", selector)
        self.assertIn("<AIProviderIcon", message)
        self.assertNotIn("<span>{message.providerName || message.providerId || 'Provider'}</span>", message)

        manager = (ROOT / "frontend/src/components/ProviderManager.tsx").read_text(encoding="utf-8")
        self.assertIn('provider={`${provider.name} ${provider.id}`}', manager)
        self.assertIn('model={`${model.name} ${model.id}`}', manager)
        self.assertIn('provider="Codex ChatGPT"', manager)
        self.assertNotIn('<Cpu className="mt-1 shrink-0 sm:mt-0"', manager)
        self.assertIn("borderColor: provider.active ? '#16a34a'", manager)
        self.assertIn("background: provider.active ? 'rgba(22, 163, 74, 0.10)'", manager)
        self.assertNotIn('>ACTIVE</span>', manager)
        self.assertIn('Obter chave API', manager)
        self.assertIn('selected.docs_url', manager)

    def test_provider_order_is_per_user_and_disabled_actions_are_blocked(self):
        manager = (ROOT / "frontend/src/components/ProviderManager.tsx").read_text(encoding="utf-8")
        repository = (ROOT / "src/db/repository.py").read_text(encoding="utf-8")

        self.assertIn("api.setPreference('provider_order', nextOrder)", manager)
        self.assertIn("preferences.preferences.provider_order?.value", manager)
        self.assertIn("draggable", manager)
        self.assertIn("<GripVertical", manager)
        self.assertIn("providerEnabled={selected.enabled}", manager)
        self.assertIn("Provider desativado. Habilite-o antes de testar.", manager)
        self.assertIn('if key in {"provider_order"}:', repository)

    def test_stream_rendering_is_batched_and_frontend_errors_are_recoverable(self):
        store = (ROOT / "frontend/src/hooks/useChatStore.ts").read_text(encoding="utf-8")
        main = (ROOT / "frontend/src/main.tsx").read_text(encoding="utf-8")
        boundary = (ROOT / "frontend/src/components/FrontendErrorBoundary.tsx").read_text(encoding="utf-8")
        vite = (ROOT / "frontend/vite.config.ts").read_text(encoding="utf-8")

        self.assertIn("STREAM_RENDER_INTERVAL_MS = 40", store)
        self.assertIn("createStreamRenderBuffer", store)
        self.assertIn("deltaBuffer.flush()", store)
        self.assertIn("resumeJobRuns", store)
        self.assertIn("sessionLoadSequence", store)
        self.assertIn("pendingOwner() === loadOwner", store)
        self.assertIn("detachActiveChatStreams()", boundary)
        self.assertIn("<FrontendErrorBoundary>", main)
        self.assertIn("chatbot_last_frontend_error_v1", boundary)
        self.assertIn("A resposta continua salva no servidor", boundary)
        self.assertIn("sourcemap: true", vite)


if __name__ == "__main__":
    unittest.main()
