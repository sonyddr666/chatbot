import unittest
from unittest.mock import patch


class PersonalRAGIsolationTest(unittest.TestCase):
    def test_add_user_documents_forces_user_metadata_and_collection(self):
        from src.rag.personal import add_user_documents

        with patch("src.rag.personal.add_documents", return_value=["chunk-1"]) as add_mock:
            ids = add_user_documents(
                42,
                ["conteudo privado"],
                metadatas=[{"source": "upload", "user_id": 999}],
            )

        self.assertEqual(ids, ["chunk-1"])
        self.assertEqual(add_mock.call_args.kwargs["collection_name"], "user_42_documents")
        self.assertEqual(add_mock.call_args.args[1][0]["user_id"], 42)
        self.assertEqual(add_mock.call_args.args[1][0]["source"], "upload")

    def test_retrieve_user_context_uses_only_user_collection(self):
        from src.rag.personal import retrieve_user_context

        with patch("src.rag.personal.retrieve_context", return_value="contexto do usuario") as retrieve_mock:
            context = retrieve_user_context(7, "minhas notas", k=3)

        self.assertEqual(context, "contexto do usuario")
        self.assertEqual(retrieve_mock.call_args.args[0], "minhas notas")
        self.assertEqual(retrieve_mock.call_args.kwargs["k"], 3)
        self.assertEqual(retrieve_mock.call_args.kwargs["collection_name"], "user_7_documents")

    def test_delete_user_documents_uses_only_user_collection(self):
        from src.rag.personal import delete_user_documents

        with patch("src.rag.personal.delete_documents") as delete_mock:
            delete_user_documents(9, ["chunk-a", "chunk-b"])

        delete_mock.assert_called_once_with(
            ["chunk-a", "chunk-b"],
            collection_name="user_9_documents",
        )


if __name__ == "__main__":
    unittest.main()
