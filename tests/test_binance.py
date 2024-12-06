# tests/test_main.py
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))
from services.binance_client import get_account_balance, get_realtime_price

def test_get_account_balance():
    """Testa se a função get_account_balance está funcionando corretamente."""
    balance = get_account_balance()
    assert balance is not None, "Deve retornar um saldo válido"
    assert "asset" in balance.columns, "Deve ter uma coluna 'asset' no saldo"

def test_get_realtime_price():
    """Testa se a função get_realtime_price está retornando o preço correto."""
    price = get_realtime_price("BTCUSDT")
    assert price is not None, "Deve retornar um preço válido"
    assert price > 0, "O preço deve ser maior que zero"
