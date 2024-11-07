import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from binance.client import Client
import pandas as pd
from datetime import datetime, timedelta
from src.config import API_KEY, API_SECRET
from decimal import Decimal, ROUND_DOWN

# Configuração da sessão para lidar com tentativas de repetição em caso de falha de conexão
session = requests.Session()
retries = Retry(total=5, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
session.mount("https://", HTTPAdapter(max_retries=retries))

# Inicializa o cliente da Binance com timeout e configuração de retry
client = Client(API_KEY, API_SECRET, testnet=True)

def get_realtime_price(symbol):
    """Obtém o preço atual em tempo real do símbolo especificado."""
    ticker = client.get_symbol_ticker(symbol=symbol)
    return float(ticker['price'])

from binance.client import Client
from datetime import datetime, timedelta
import pandas as pd
import time


import pandas as pd

def get_historical_data(symbol, interval='30m', max_limit=1000):
    """
    Obtém até o máximo de dados históricos disponíveis para o 'symbol' e 'interval' especificados.
    """
    try:
        # Solicita até 1000 registros, o máximo permitido pela API sem especificar datas
        klines = client.get_historical_klines(
            symbol,
            interval,
            limit=max_limit
        )

        # Verifica se os dados foram recebidos
        if not klines:
            print("Nenhum dado retornado pela API.")
            return None

        # Converte para DataFrame e seleciona colunas necessárias
        data = pd.DataFrame(klines, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_asset_volume', 'number_of_trades',
            'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
        ])
        data['close'] = data['close'].astype(float)
        data = data[['timestamp', 'close']]

        print(f"DEBUG: Total de {len(data)} dados retornados para {symbol} no intervalo {interval}.")
        return data

    except Exception as e:
        print(f"Erro ao coletar dados históricos: {e}")
        return None


def get_asset_quantity(asset):
    """Obtém a quantidade de um ativo específico na conta Binance."""
    account_info = client.get_account()
    for balance in account_info['balances']:
        if balance['asset'] == asset:
            return float(balance['free'])
    return 0.0  # Retorna 0.0 se o ativo não estiver presente na conta

def get_account_balance():
    """Obtém o saldo atual da conta Binance e retorna como DataFrame."""
    try:
        # Obter informações da conta
        account_info = client.get_account()
        balances = account_info.get('balances', [])
        
        # Verifica se temos dados no saldo
        if not balances:
            print("DEBUG: Nenhum saldo retornado pela API da Binance.")
            return None
        
        # Filtrar apenas ativos com saldo positivo
        active_balances = [
            {"asset": balance['asset'], "free": float(balance['free']), "locked": float(balance['locked'])}
            for balance in balances if float(balance['free']) > 0 or float(balance['locked']) > 0
        ]
        
        # Verifica se há algum saldo positivo
        if not active_balances:
            print("DEBUG: Nenhum ativo com saldo positivo encontrado.")
            return pd.DataFrame(columns=["asset", "free", "locked"])  # Retorna DataFrame vazio se não houver saldo positivo

        # Converter para DataFrame e exibir para debug
        df = pd.DataFrame(active_balances)
        print("DEBUG: Dados de saldo atual da Binance carregados:")
        print(df)
        
        return df
    
    except Exception as e:
        print(f"Erro ao obter saldo da conta Binance: {e}")
        return None
    


def get_lot_size(symbol):
    """Obtém os limites de quantidade (LOT_SIZE) para o ativo."""
    exchange_info = client.get_symbol_info(symbol)
    for filt in exchange_info['filters']:
        if filt['filterType'] == 'LOT_SIZE':
            min_qty = float(filt['minQty'])
            step_size = float(filt['stepSize'])
            return min_qty, step_size
    return None, None

def adjust_quantity(quantity, symbol):
    """Ajusta a quantidade com base nos limites de quantidade (LOT_SIZE) do ativo."""
    min_qty, step_size = get_lot_size(symbol)
    if min_qty is None or step_size is None:
        raise ValueError(f"Não foi possível obter LOT_SIZE para {symbol}")

    # Usa Decimal para arredondar a quantidade conforme o step_size
    quantity_decimal = Decimal(quantity).quantize(Decimal(str(step_size)), rounding=ROUND_DOWN)
    adjusted_quantity = max(min_qty, float(quantity_decimal))
    
    return adjusted_quantity

def execute_trade(asset, quantity, side):
    """Envia uma ordem de compra ou venda para a Binance."""
    try:
        # Ajuste de quantidade para atender ao filtro LOT_SIZE
        quantity = adjust_quantity(quantity, asset)

        order = client.order_market(
            symbol=asset,
            side=side.upper(),  # 'BUY' ou 'SELL'
            quantity=quantity
        )
        print(f"Ordem {side} executada com sucesso: {order}")
        return order
    except Exception as e:
        print(f"Erro ao executar ordem {side} para {asset}: {e}")
        return None


def get_consecutive_trades(symbol, trade_type):
    """
    Recupera o número de transações consecutivas do tipo especificado (buy ou sell)
    no histórico de ordens da Binance.
    """
    # Recupera o histórico de ordens para o símbolo
    orders = client.get_all_orders(symbol=symbol, limit=100)

    # Garante que `trade_type` está em minúsculas para evitar inconsistências
    trade_type = trade_type.lower()

    # Filtra apenas ordens preenchidas ('FILLED') e do tipo especificado
    filled_orders = [order for order in orders if order['status'] == 'FILLED']

    # Conta as transações consecutivas do tipo especificado
    consecutive_count = 0
    for order in reversed(filled_orders):
        # Verifica e conta apenas transações consecutivas do tipo correto
        if order['side'].lower() == trade_type:
            consecutive_count += 1
        else:
            # Interrompe a contagem ao encontrar uma transação de tipo oposto
            break

    # Retorna o total de transações consecutivas do tipo especificado
    return consecutive_count
