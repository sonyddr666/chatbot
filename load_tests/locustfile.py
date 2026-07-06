"""Testes de carga com Locust.

Uso:
    locust -f load_tests/locustfile.py --host=http://localhost:8000
"""

from locust import HttpUser, task, between


class ChatbotUser(HttpUser):
    wait_time = between(1, 5)

    def on_start(self):
        """Setup por usuário."""
        self.session_id = f"load-test-{hash(self)}"
        self.messages = [
            "Olá! Como você está?",
            "O que é Python?",
            "Explique o que é machine learning",
            "Qual a capital do Brasil?",
            "Me conte uma curiosidade",
        ]
        self.msg_idx = 0

    @task(3)
    def send_message(self):
        """Envia mensagem para o chat."""
        msg = self.messages[self.msg_idx % len(self.messages)]
        self.msg_idx += 1

        with self.client.post(
            "/api/v1/chat",
            json={
                "message": msg,
                "session_id": self.session_id,
            },
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"Status: {resp.status_code}")

    @task(1)
    def check_health(self):
        """Verifica health check."""
        self.client.get("/api/v1/health")

    @task(1)
    def get_stats(self):
        """Verifica estatísticas."""
        self.client.get("/api/v1/stats")
