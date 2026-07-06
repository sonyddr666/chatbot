# Testes de Carga

## Instalação

```bash
pip install locust
```

## Uso

```bash
# Iniciar API primeiro
python -m src.main serve

# Rodar testes (terminal 2)
locust -f load_tests/locustfile.py --host=http://localhost:8000

# Ou modo headless (500 usuários, 10/s)
locust -f load_tests/locustfile.py --host=http://localhost:8000 \
  --headless -u 500 -r 10 --run-time 5m
```

Acessar UI: http://localhost:8089
