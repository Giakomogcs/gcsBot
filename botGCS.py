from binance.client import Client
import pandas as pd
import pandas_ta as ta
import time

API_KEY = 'jj9erlxLJ4HIdocAtt1538spv1Ye75o4BSbRb15Ao3Wgd8bWZpnn0lCHzlsWie7m'
API_SECRET = 'zwTvM0wUUsyNMqMXhJLgRV1s6McsZ43mdh7PFZbt2ftcWKIPs7jASV7SqG9vtnf2'

client = Client(API_KEY, API_SECRET, testnet=True)

symbol = 'BTCUSDT'
trade_quantity = 0.00001  # Quantidade inicial

# Função para obter dados de preço
def get_historical_data(symbol, interval='1h', lookback='500'):
    klines = client.get_historical_klines(symbol, interval, lookback + " hours ago UTC")
    data = pd.DataFrame(klines, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time', 
                                         'quote_asset_volume', 'number_of_trades', 'taker_buy_base_asset_volume', 
                                         'taker_buy_quote_asset_volume', 'ignore'])
    data['close'] = data['close'].astype(float)
    return data[['timestamp', 'close']]

# Função para calcular indicadores técnicos com pandas_ta
def calculate_indicators(df):
    df['SMA_50'] = ta.sma(df['close'], length=50)
    df['SMA_200'] = ta.sma(df['close'], length=200)
    df['RSI'] = ta.rsi(df['close'], length=14)
    return df

# Função para calcular quantidade de negociação com base no saldo
def get_trade_quantity():
    balance = client.get_asset_balance(asset='BTC')
    btc_balance = float(balance['free'])
    return btc_balance * 0.01  # Exemplo: usar 1% do saldo

# Função para decidir se deve comprar ou vender
def make_trade_decision(df):
    last_row = df.iloc[-1]
    # Verificar se os valores de SMA e RSI não são None
    if last_row['SMA_50'] is not None and last_row['SMA_200'] is not None and last_row['RSI'] is not None:
        if last_row['SMA_50'] > last_row['SMA_200'] and last_row['RSI'] < 30:
            return "buy"
        elif last_row['SMA_50'] < last_row['SMA_200'] and last_row['RSI'] > 70:
            return "sell"
    return "hold"

# Função para executar ordens com controle de risco
def place_order(decision, symbol, quantity):
    if decision == "buy":
        print("Executando ordem de compra.")
        order = client.order_market_buy(symbol=symbol, quantity=quantity)
        print(f"Ordem de compra executada: {order}")
    elif decision == "sell":
        print("Executando ordem de venda.")
        order = client.order_market_sell(symbol=symbol, quantity=quantity)
        print(f"Ordem de venda executada: {order}")
    else:
        print("Nenhuma ordem executada (hold).")

# Função principal do bot
def trading_bot():
    in_position = False
    while True:
        # Obter dados de preço e calcular indicadores
        df = get_historical_data(symbol)
        df = calculate_indicators(df)
        
        # Atualizar a quantidade de negociação com base no saldo
        quantity = get_trade_quantity()
        
        # Decidir se compra ou vende
        decision = make_trade_decision(df)
        
        # Executar ordem com base na decisão
        place_order(decision, symbol, quantity)
        
        # Esperar até o próximo ciclo
        print("Aguardando próximo ciclo de negociação...")
        time.sleep(3600)  # Intervalo de 1 hora

if __name__ == "__main__":
    trading_bot()
