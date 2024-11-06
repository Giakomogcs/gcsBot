from src.strategies.indicators import moving_average
import pandas as pd

def trading_decision(asset, price, portfolio_manager, df):
    short_ma_period = 10
    long_ma_period = 20

    # Extrair o ativo base de 'BTCUSDT' (resultado será 'BTC')
    base_asset = asset.replace('USDT', '')  # Remover 'USDT' para obter apenas 'BTC'

    # Verifica se temos dados suficientes para calcular as médias móveis
    if len(df) < long_ma_period:
        print("DEBUG: Dados insuficientes para calcular médias móveis. Aguardando mais dados...")
        return {
            'asset': asset,
            'quantity': 0,
            'price': price,
            'type': 'hold',
            'reason': "Insufficient data for Long MA. Waiting for more historical data."
        }

    # Calcula as médias móveis
    short_ma = moving_average(df['close'], period=short_ma_period).iloc[-1]
    long_ma = moving_average(df['close'], period=long_ma_period).iloc[-1]

    # Verifica se temos valores válidos para as médias móveis
    if pd.isna(short_ma) or pd.isna(long_ma):
        print("DEBUG: Média móvel inválida detectada.")
        return {
            'asset': asset,
            'quantity': 0,
            'price': price,
            'type': 'hold',
            'reason': "Insufficient data to calculate Short MA or Long MA. Waiting for more data."
        }

    # Obter saldo de USDT e quantidade de BTC diretamente da tabela balance_df
    cash_balance = portfolio_manager.get_balance('USDT')
    asset_quantity = portfolio_manager.get_balance(base_asset)
    investment_percentage = portfolio_manager.get_investment_percentage()

    # Log detalhado de informações antes da decisão
    print(f"DEBUG: short_ma={short_ma}, long_ma={long_ma}, cash_balance={cash_balance}, "
          f"asset_quantity={asset_quantity}, investment_percentage={investment_percentage}")

    # Quantidade para comprar, com base no saldo e no percentual de investimento
    quantity_to_buy = (cash_balance * investment_percentage) / price
    # Quantidade para vender
    quantity_to_sell = asset_quantity * investment_percentage

    # Decisão de Compra
    if short_ma > long_ma:
        if cash_balance >= quantity_to_buy * price:
            print(f"DEBUG: Sinal de COMPRA detectado. Quantidade para comprar: {quantity_to_buy}, Cash Balance: {cash_balance}, Price: {price}")
            return {
                'asset': asset,
                'quantity': quantity_to_buy,
                'price': price,
                'type': 'buy',
                'reason': (f"Golden Cross detected - Short MA ({short_ma}) crossed above Long MA ({long_ma})."
                           f" Comprando ativo com perfil {portfolio_manager.investor_profile}.")
            }
        else:
            print(f"DEBUG: Sinal de COMPRA detectado, mas saldo insuficiente. Necessário: {quantity_to_buy * price}, Disponível: {cash_balance}")

    # Decisão de Venda
    elif short_ma < long_ma:
        if asset_quantity >= quantity_to_sell:
            print(f"DEBUG: Sinal de VENDA detectado. Quantidade para vender: {quantity_to_sell}, Asset Quantity: {asset_quantity}, Price: {price}")
            return {
                'asset': asset,
                'quantity': quantity_to_sell,
                'price': price,
                'type': 'sell',
                'reason': (f"Death Cross detected - Short MA ({short_ma}) crossed below Long MA ({long_ma})."
                           f" Vendendo ativo com perfil {portfolio_manager.investor_profile}.")
            }
        else:
            print(f"DEBUG: Sinal de VENDA detectado, mas quantidade insuficiente. Necessário: {quantity_to_sell}, Disponível: {asset_quantity}")

    # Caso nenhum dos critérios seja atendido
    else:
        print("DEBUG: Nenhum sinal de compra ou venda detectado. Mantendo posição atual.")
        return {
            'asset': asset,
            'quantity': 0,
            'price': price,
            'type': 'hold',
            'reason': (f"No trade action taken. Current Short MA ({short_ma}) and Long MA ({long_ma}) suggest unclear trend. "
                       f"Cash balance at {cash_balance}, holding existing positions.")
        }
