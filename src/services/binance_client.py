import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from binance.client import Client
import pandas as pd
from datetime import datetime, timedelta
from src.config import API_KEY, API_SECRET
from decimal import Decimal, ROUND_DOWN
import logging

# Configuração do logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger()

# Configuração da sessão para lidar com tentativas de repetição em caso de falha de conexão
session = requests.Session()
retries = Retry(total=5, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
session.mount("https://", HTTPAdapter(max_retries=retries))

# Inicializa o cliente da Binance com timeout e configuração de retry
client = Client(API_KEY, API_SECRET, testnet=True)

def get_realtime_price(symbol):
    """Obtém o preço atual em tempo real do símbolo especificado."""
    try:
        ticker = client.get_symbol_ticker(symbol=symbol)
        if not isinstance(ticker, dict) or 'price' not in ticker:
            logger.error(f"Estrutura inesperada ao obter preço em tempo real: {ticker}")
            return None
        return float(ticker['price'])
    except Exception as e:
        logger.error(f"Erro ao obter preço em tempo real para {symbol}: {e}")
        return None

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
        if not isinstance(klines, list) or not klines:
            logger.warning(f"Nenhum dado retornado pela API para o símbolo {symbol}. Dados recebidos: {klines}")
            return None

        # Converte para DataFrame e seleciona colunas necessárias
        data = pd.DataFrame(klines, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_asset_volume', 'number_of_trades',
            'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
        ])
        
        # Converte as colunas relevantes para o tipo apropriado
        try:
            data[['open', 'high', 'low', 'close', 'volume']] = data[['open', 'high', 'low', 'close', 'volume']].astype(float)
        except ValueError as ve:
            logger.error(f"Erro ao converter colunas para float: {ve}")
            return None

        # Mantém apenas as colunas necessárias para a estratégia
        data = data[['timestamp', 'open', 'high', 'low', 'close', 'volume']]

        logger.info(f"Total de {len(data)} dados retornados para {symbol} no intervalo {interval}.")
        return data

    except Exception as e:
        logger.error(f"Erro ao coletar dados históricos: {e}")
        return None

def get_asset_quantity(asset):
    """Obtém a quantidade de um ativo específico na conta Binance."""
    try:
        account_info = client.get_account()
        if not isinstance(account_info, dict) or 'balances' not in account_info:
            logger.error(f"Estrutura inesperada ao obter informações da conta: {account_info}")
            return 0.0
        for balance in account_info['balances']:
            if balance['asset'] == asset:
                return float(balance['free'])
        return 0.0
    except Exception as e:
        logger.error(f"Erro ao obter quantidade para o ativo {asset}: {e}")
        return 0.0

def get_account_balance():
    """Obtém o saldo atual da conta Binance e retorna como DataFrame."""
    try:
        account_info = client.get_account()
        balances = account_info.get('balances', [])
        
        if not isinstance(balances, list) or not balances:
            logger.warning("Nenhum saldo retornado pela API da Binance.")
            return pd.DataFrame(columns=["asset", "free", "locked"])
        
        active_balances = [
            {"asset": balance['asset'], "free": float(balance['free']), "locked": float(balance['locked'])}
            for balance in balances if float(balance['free']) > 0 or float(balance['locked']) > 0
        ]
        
        if not active_balances:
            logger.info("Nenhum ativo com saldo positivo encontrado.")
            return pd.DataFrame(columns=["asset", "free", "locked"])

        df = pd.DataFrame(active_balances)
        logger.info("Dados de saldo atual da Binance carregados com sucesso.")
        
        # Adicionando o print da carteira
        print("\nCarteira Atual:")
        print(df)

        return df
    
    except Exception as e:
        logger.error(f"Erro ao obter saldo da conta Binance: {e}")
        return pd.DataFrame(columns=["asset", "free", "locked"])

def get_lot_size(symbol):
    """Obtém os limites de quantidade (LOT_SIZE) para o ativo."""
    try:
        exchange_info = client.get_symbol_info(symbol)
        if not isinstance(exchange_info, dict) or 'filters' not in exchange_info:
            logger.error(f"Estrutura inesperada ao obter informações do símbolo: {exchange_info}")
            return None, None
        for filt in exchange_info['filters']:
            if filt['filterType'] == 'LOT_SIZE':
                min_qty = float(filt['minQty'])
                step_size = float(filt['stepSize'])
                return min_qty, step_size
        return None, None
    except Exception as e:
        logger.error(f"Erro ao obter LOT_SIZE para {symbol}: {e}")
        return None, None

def adjust_quantity(quantity, symbol):
    """Ajusta a quantidade com base nos limites de quantidade (LOT_SIZE) do ativo."""
    min_qty, step_size = get_lot_size(symbol)
    if min_qty is None or step_size is None:
        raise ValueError(f"Não foi possível obter LOT_SIZE para {symbol}")

    quantity_decimal = Decimal(quantity).quantize(Decimal(str(step_size)), rounding=ROUND_DOWN)
    adjusted_quantity = max(min_qty, float(quantity_decimal))
    
    return adjusted_quantity

def execute_trade(asset, quantity, side, slippage_tolerance=0.01):
    """Envia uma ordem de compra ou venda para a Binance."""
    try:
        # Ajuste de quantidade para atender ao filtro LOT_SIZE
        quantity = adjust_quantity(quantity, asset)

        # Verificar o preço atual e calcular a tolerância de slippage
        current_price = get_realtime_price(asset)
        if current_price is None:
            raise ValueError(f"Preço atual não disponível para {asset}")

        # Ajustar preço com base na tolerância de slippage
        if side.lower() == 'buy':
            max_acceptable_price = current_price * (1 + slippage_tolerance)
            logger.info(f"Executando ordem de COMPRA para {asset} com preço máximo aceitável: {max_acceptable_price:.2f}")
        elif side.lower() == 'sell':
            min_acceptable_price = current_price * (1 - slippage_tolerance)
            logger.info(f"Executando ordem de VENDA para {asset} com preço mínimo aceitável: {min_acceptable_price:.2f}")

        # Enviar ordem de mercado
        order = client.order_market(
            symbol=asset,
            side=side.upper(),  # 'BUY' ou 'SELL'
            quantity=quantity
        )
        if not isinstance(order, dict):
            logger.error(f"Ordem retornada não é do tipo esperado: {type(order)}")
            return None

        logger.info(f"Ordem {side} executada com sucesso: {order}")
        return order
    except Exception as e:
        logger.error(f"Erro ao executar ordem {side} para {asset}: {e}")
        return None

def get_consecutive_trades(symbol, trade_type):
    """
    Recupera o número de transações consecutivas do tipo especificado (buy ou sell)
    no histórico de ordens da Binance.
    """
    try:
        # Recupera o histórico de ordens para o símbolo
        orders = client.get_all_orders(symbol=symbol, limit=100)

        if not isinstance(orders, list):
            logger.error(f"Histórico de ordens não é do tipo lista: {type(orders)}")
            return 0

        # Garante que trade_type está em minúsculas para evitar inconsistências
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
    except Exception as e:
        logger.error(f"Erro ao obter transações consecutivas para {symbol}: {e}")
        return 0
