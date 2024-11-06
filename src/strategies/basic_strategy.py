from src.strategies.indicators import moving_average
import pandas as pd

def trading_decision(asset, price, portfolio_manager, df):
    short_ma_period = 5  # Período da média curta ajustado
    long_ma_period = 40  # Período da média longa ajustado
    rsi_period = 10  # Período do RSI ajustado para reatividade

    # Extrair o ativo base de 'BTCUSDT' para 'BTC'
    base_asset = asset.replace('USDT', '')

    # Verifica se temos dados suficientes para calcular as médias móveis
    if len(df) < long_ma_period:
        print("DEBUG: Dados insuficientes para calcular médias móveis. Aguardando mais dados...")
        return {'asset': asset, 'quantity': 0, 'price': price, 'type': 'hold', 'reason': "Insufficient data for Long MA."}

    # Calcula as médias móveis
    short_ma = moving_average(df['close'], period=short_ma_period).iloc[-1]
    long_ma = moving_average(df['close'], period=long_ma_period).iloc[-1]

    # Verifica o valor do RSI
    rsi = calculate_rsi(df['close'], period=rsi_period)

    # Obter saldo e quantidade de ativos
    cash_balance = portfolio_manager.get_balance('USDT')
    asset_quantity = portfolio_manager.get_balance(base_asset)
    investment_percentage = portfolio_manager.get_investment_percentage()

    # Calcular quantidades ajustadas para compra/venda
    quantity_to_buy = (cash_balance * investment_percentage) / price
    quantity_to_sell = asset_quantity * investment_percentage

    # Log detalhado para depuração
    print(f"DEBUG: short_ma={short_ma}, long_ma={long_ma}, RSI={rsi}, cash_balance={cash_balance}, "
          f"asset_quantity={asset_quantity}, investment_percentage={investment_percentage}")

    # Critérios de Compra
    if short_ma > long_ma and rsi < 40 and cash_balance >= quantity_to_buy * price:
        print(f"DEBUG: Sinal de COMPRA confirmado com RSI: {rsi}")
        return {
            'asset': asset,
            'quantity': quantity_to_buy,
            'price': price,
            'type': 'buy',
            'reason': f"Golden Cross detected - Short MA ({short_ma}) crossed above Long MA ({long_ma}) with RSI ({rsi})."
        }

    # Critérios de Venda com RSI de Sobrecompra Extremada
    elif rsi > 80 and asset_quantity >= quantity_to_sell:
        print(f"DEBUG: Sinal de VENDA confirmado com RSI elevado: {rsi}")
        return {
            'asset': asset,
            'quantity': quantity_to_sell,
            'price': price,
            'type': 'sell',
            'reason': f"RSI elevated - extreme overbought condition with RSI ({rsi})."
        }

    # Critérios de Venda com Cruzamento de Médias
    elif short_ma < long_ma and rsi > 65 and asset_quantity >= quantity_to_sell:
        print(f"DEBUG: Sinal de VENDA confirmado com RSI: {rsi}")
        return {
            'asset': asset,
            'quantity': quantity_to_sell,
            'price': price,
            'type': 'sell',
            'reason': f"Death Cross detected - Short MA ({short_ma}) crossed below Long MA ({long_ma}) with RSI ({rsi})."
        }

    # Nenhum critério atendido
    print("DEBUG: Nenhum sinal de compra ou venda detectado. Mantendo posição atual.")
    return {
        'asset': asset,
        'quantity': 0,
        'price': price,
        'type': 'hold',
        'reason': f"Hold - Short MA ({short_ma}) and Long MA ({long_ma}) do not confirm clear trend."
    }

# Função RSI para confirmar sinais
def calculate_rsi(series, period=10):  # Período do RSI ajustado
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.iloc[-1] if not pd.isna(rsi.iloc[-1]) else 50
