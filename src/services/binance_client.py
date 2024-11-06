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

def get_historical_data(symbol, interval='1h', periods=200, max_lookback_days=60):
    """Obtém dados históricos em lotes controlados até alcançar o período desejado."""
    end_date = datetime.now()
    all_klines = []

    while len(all_klines) < periods:
        # Calcula o intervalo de dias para a requisição atual
        start_date = end_date - timedelta(days=max_lookback_days)

        # Obtém dados históricos para o intervalo especificado
        klines = client.get_historical_klines(
            symbol, interval,
            start_str=start_date.strftime('%d %b %Y %H:%M:%S'),
            end_str=end_date.strftime('%d %b %Y %H:%M:%S')
        )

        # Verifica se obteve dados
        if not klines:
            print("DEBUG: Nenhum dado obtido para o intervalo atual. Encerrando coleta.")
            break

        # Adiciona novos dados ao acumulador
        all_klines = klines + all_klines  # Insere no início para manter ordem cronológica
        end_date = datetime.fromtimestamp(klines[0][0] / 1000)  # Atualiza a data final para próxima requisição

        # Log da quantidade de dados coletados
        print(f"DEBUG: {len(klines)} novos dados coletados, total acumulado: {len(all_klines)} linhas.")

    # Converte os dados para um DataFrame
    data = pd.DataFrame(all_klines, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 
                                             'close_time', 'quote_asset_volume', 'number_of_trades', 
                                             'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'])
    data['close'] = data['close'].astype(float)

    # Limita os dados ao número necessário de períodos
    data = data[['timestamp', 'close']].tail(periods)
    
    # Log final para verificação
    print(f"DEBUG: Total de {len(data)} dados retornados para {symbol} no intervalo {interval}.")
    
    return data

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
