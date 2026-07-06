#!/bin/bash
# Script de backup do Chatbot
# Uso: ./scripts/backup.sh

BACKUP_DIR="./backups"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
mkdir -p "$BACKUP_DIR"

echo "📦 Iniciando backup $TIMESTAMP..."

# Backup do banco SQLite
if [ -f "./data/chatbot.db" ]; then
    cp "./data/chatbot.db" "$BACKUP_DIR/chatbot_$TIMESTAMP.db"
    echo "✅ Banco: chatbot_$TIMESTAMP.db"
fi

# Backup do ChromaDB
if [ -d "./data/chroma" ]; then
    tar -czf "$BACKUP_DIR/chroma_$TIMESTAMP.tar.gz" -C ./data chroma/
    echo "✅ ChromaDB: chroma_$TIMESTAMP.tar.gz"
fi

# Backup do .env (removendo chaves sensíveis)
if [ -f ".env" ]; then
    cp ".env" "$BACKUP_DIR/env_$TIMESTAMP.txt"
    echo "✅ .env salvo"
fi

# Limpar backups antigos (mais de 7 dias)
find "$BACKUP_DIR" -name "*.db" -mtime +7 -delete
find "$BACKUP_DIR" -name "*.tar.gz" -mtime +7 -delete

echo "✨ Backup concluído em $BACKUP_DIR"
