#!/bin/bash
# Script de restauração do Chatbot
# Uso: ./scripts/restore.sh <arquivo_db> [arquivo_chroma]

if [ $# -lt 1 ]; then
    echo "Uso: ./scripts/restore.sh <arquivo_db> [arquivo_chroma.tar.gz]"
    exit 1
fi

DB_FILE="$1"
CHROMA_FILE="$2"

echo "🔄 Restaurando backup..."

if [ -f "$DB_FILE" ]; then
    mkdir -p ./data
    cp "$DB_FILE" "./data/chatbot.db"
    echo "✅ Banco restaurado: $DB_FILE"
fi

if [ -n "$CHROMA_FILE" ] && [ -f "$CHROMA_FILE" ]; then
    tar -xzf "$CHROMA_FILE" -C ./data/
    echo "✅ ChromaDB restaurado: $CHROMA_FILE"
fi

echo "✨ Restauração concluída!"
