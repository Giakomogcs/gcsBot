import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import os
from binance.client import Client
import pandas as pd
from datetime import datetime, timedelta
from dotenv import load_dotenv
from decimal import Decimal, ROUND_DOWN
import logging

# Carregar variáveis do .env
load_dotenv()

# Obter as variáveis de ambiente
API_KEY = os.getenv('BINANCE_API_KEY')
API_SECRET = os.getenv('BINANCE_API_SECRET')

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
    

def get_price_trend(symbol, interval='1m', lookback=10):
    """
    Analisa a tendência de preços recentes para verificar se há um padrão de alta ou baixa.
    Retorna 'up' se estiver em alta, 'down' se estiver em baixa, e 'neutral' se não houver tendência definida.
    """
    try:
        # Obtem os dados históricos recentes para o cálculo de tendência
        recent_data = client.get_klines(symbol=symbol, interval=interval, limit=lookback)
        
        if not isinstance(recent_data, list) or len(recent_data) < lookback:
            logger.warning(f"Dados insuficientes para calcular tendência para {symbol}.")
            return 'neutral'

        # Extrai os preços de fechamento
        closing_prices = [float(candle[4]) for candle in recent_data]
        
        # Calcula a média dos preços
        price_change = sum(closing_prices[i+1] - closing_prices[i] for i in range(len(closing_prices) - 1)) / (len(closing_prices) - 1)
        
        if price_change > 0:
            return 'up'
        elif price_change < 0:
            return 'down'
        else:
            return 'neutral'
    except Exception as e:
        logger.error(f"Erro ao obter tendência de preço para {symbol}: {e}")
        return 'neutral'



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


def execute_trade(asset, quantity, side, slippage_tolerance=0.005):  # ajustado para 0.5%
    try:
        quantity = adjust_quantity(quantity, asset)
        current_price = get_realtime_price(asset)

        if current_price is None:
            raise ValueError(f"Preço atual não disponível para {asset}")

        # Ajuste de preço com base na tolerância de slippage
        if side.lower() == 'buy':
            max_acceptable_price = current_price * (1 + slippage_tolerance)
            if current_price > max_acceptable_price:
                logger.warning(f"Preço muito alto para compra. Evitando compra.")
                return None

        elif side.lower() == 'sell':
            min_acceptable_price = current_price * (1 - slippage_tolerance)
            if current_price < min_acceptable_price:
                logger.warning(f"Preço muito baixo para venda. Evitando venda.")
                return None

        # Envia ordem
        order = client.order_market(
            symbol=asset,
            side=side.upper(),
            quantity=quantity
        )

        if not isinstance(order, dict):
            logger.error(f"Ordem não é do tipo esperado: {type(order)}")
            return None

        logger.info(f"Ordem {side} executada com sucesso: {order}")
        return order

    except Exception as e:
        logger.error(f"Erro ao executar ordem {side} para {asset}: {e}")
        return None


def get_consecutive_trades(symbol, trade_type):
    """
    Recupera o número de transações consecutivas do tipo especificado (buy ou sell)
    no histórico de ordens da Binance, começando a partir da última transação e parando ao encontrar uma transação oposta.
    """
    try:
        # Recupera o histórico de ordens para o símbolo
        orders = client.get_all_orders(symbol=symbol, limit=100)

        if not isinstance(orders, list):
            logger.error(f"Histórico de ordens não é do tipo lista: {type(orders)}")
            return 0

        # Filtra apenas ordens preenchidas ('FILLED')
        filled_orders = [order for order in orders if order['status'] == 'FILLED']

        # Inicia as contagens para compras e vendas consecutivas
        consecutive_count = 0

        # Define o lado da última transação (baseando a contagem)
        last_trade_type = filled_orders[-1]['side'].lower() if filled_orders else None

        # Conta as transações consecutivas a partir da última
        for order in reversed(filled_orders):
            current_trade_type = order['side'].lower()
            
            if current_trade_type == trade_type:
                consecutive_count += 1
            else:
                # Encontra um tipo oposto; para a contagem de consecutivas
                break

        # Retorna o total de transações consecutivas para o tipo especificado
        return consecutive_count
    except Exception as e:
        logger.error(f"Erro ao obter transações consecutivas para {symbol}: {e}")
        return 0



def get_last_trade(symbol):
    """
    Obtém o preço e a quantidade da última compra e venda realizadas para o símbolo especificado.
    """
    try:
        # Recupera o histórico de ordens para o símbolo
        orders = client.get_all_orders(symbol=symbol, limit=100)

        if not isinstance(orders, list):
            logger.error(f"Histórico de ordens não é do tipo lista: {type(orders)}")
            return None, None

        # Filtra apenas ordens preenchidas ('FILLED')
        filled_orders = [order for order in orders if order['status'] == 'FILLED']

        # Inicializa variáveis para armazenar a última compra e venda
        last_buy = None
        last_sell = None

        # Procura a última compra e a última venda
        for order in reversed(filled_orders):
            if order['side'].lower() == 'buy' and last_buy is None:
                last_buy = {
                    'price': float(order['price']),
                    'quantity': float(order['origQty'])
                }
            elif order['side'].lower() == 'sell' and last_sell is None:
                last_sell = {
                    'price': float(order['price']),
                    'quantity': float(order['origQty'])
                }

            # Se ambos foram encontrados, interrompe a busca
            if last_buy and last_sell:
                break

        # Retorna as últimas transações de compra e venda
        return last_buy, last_sell

    except Exception as e:
        logger.error(f"Erro ao obter última transação para {symbol}: {e}")
        return None, None

def get_recent_prices(symbol, interval='1h', lookback_hours=5):
    """
    Obtém a média de preços de fechamento dos últimos 'lookback_hours' para o símbolo especificado.
    """
    try:
        # Calcula a quantidade de velas necessárias
        lookback_intervals = lookback_hours
        klines = client.get_klines(symbol=symbol, interval=interval, limit=lookback_intervals)

        if not isinstance(klines, list) or len(klines) < lookback_intervals:
            logger.warning(f"Dados insuficientes para calcular média de preços recentes para {symbol}.")
            return None

        # Extrai os preços de fechamento e calcula a média
        closing_prices = [float(candle[4]) for candle in klines]
        recent_average_price = sum(closing_prices) / len(closing_prices)

        logger.info(f"Média de preços recentes para {symbol} nos últimos {lookback_hours} horas: {recent_average_price}")
        return recent_average_price

    except Exception as e:
        logger.error(f"Erro ao obter preços recentes para {symbol}: {e}")
        return None
