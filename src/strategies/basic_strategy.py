from services.binance_client import get_consecutive_trades
from src.strategies.indicators import moving_average
from strategies.risk_manager import RiskManager
import pandas as pd
from datetime import datetime, timedelta

def trading_decision(asset, price, portfolio_manager, df):
    risk_manager = RiskManager(portfolio_manager)  # Passando o PortfolioManager para o RiskManager

    short_ma_period = 8
    long_ma_period = 50
    rsi_period = 10
    min_asset_quantity = 0.001

    base_asset = asset.replace('USDT', '')

    if len(df) < long_ma_period:
        print("DEBUG: Dados insuficientes para calcular médias móveis. Aguardando mais dados...")
        return {'asset': asset, 'quantity': 0, 'price': price, 'type': 'hold', 'reason': "Insufficient data for Long MA."}

    short_ma = moving_average(df['close'], period=short_ma_period).iloc[-1]
    long_ma = moving_average(df['close'], period=long_ma_period).iloc[-1]
    rsi = calculate_rsi(df['close'], period=rsi_period)

    # Obter saldo de caixa disponível para investimento, respeitando a reserva mínima
    cash_balance = portfolio_manager.get_cash_balance()
    asset_quantity = portfolio_manager.get_balance(base_asset)
    investment_percentage = portfolio_manager.get_investment_percentage()

    # Calcular a quantidade a comprar levando em conta o reserve_cash
    quantity_to_buy = (cash_balance * investment_percentage) / price
    total_purchase_cost = quantity_to_buy * price  # Custo total da compra

    # Cálculo da quantidade de venda, respeitando a quantidade mínima
    quantity_to_sell = min(asset_quantity * investment_percentage, asset_quantity - min_asset_quantity)

    print(f"DEBUG: short_ma={short_ma}, long_ma={long_ma}, RSI={rsi}, cash_balance={cash_balance}, "
          f"asset_quantity={asset_quantity}, investment_percentage={investment_percentage}")

    # Critérios de Compra com verificação de reserva de segurança
    if (
        short_ma > long_ma and 
        rsi < 40 and 
        cash_balance >= total_purchase_cost and 
        cash_balance - total_purchase_cost >= portfolio_manager.reserve_cash  # Verifica a reserva de segurança
    ):
        if not risk_manager.can_trade(asset, 'buy', quantity_to_buy, price):
            print("DEBUG: Compra bloqueada pelo RiskManager.")
            print("Motivo: Limite de compras consecutivas atingido ou preço acima da média histórica de compras.")
            return {'asset': asset, 'quantity': 0, 'price': price, 'type': 'hold', 'reason': "RiskManager restricted buy."}
        
        print(f"DEBUG: Sinal de COMPRA confirmado com RSI: {rsi}")
        return {
            'asset': asset,
            'quantity': quantity_to_buy,
            'price': price,
            'type': 'buy',
            'reason': f"Golden Cross detected - Short MA ({short_ma}) crossed above Long MA ({long_ma}) with RSI ({rsi})."
        }

    # Critérios de Venda com RSI de Sobrecompra
    elif rsi > 80 and quantity_to_sell > min_asset_quantity:
        if not risk_manager.can_trade(asset, 'sell', quantity_to_sell, price):
            print("DEBUG: Venda bloqueada pelo RiskManager.")
            print("Motivo: Limite de vendas consecutivas atingido ou preço abaixo da média histórica de vendas.")
            return {'asset': asset, 'quantity': 0, 'price': price, 'type': 'hold', 'reason': "RiskManager restricted sell."}
        
        print(f"DEBUG: Sinal de VENDA confirmado com RSI elevado: {rsi}")
        return {
            'asset': asset,
            'quantity': quantity_to_sell,
            'price': price,
            'type': 'sell',
            'reason': f"RSI elevated - extreme overbought condition with RSI ({rsi})."
        }

    # Critérios de Venda com Cruzamento de Médias
    elif short_ma < long_ma and rsi > 65 and quantity_to_sell > min_asset_quantity:
        if not risk_manager.can_trade(asset, 'sell', quantity_to_sell, price):
            print("DEBUG: Venda bloqueada pelo RiskManager.")
            print("Motivo: Limite de vendas consecutivas atingido ou preço abaixo da média histórica de vendas.")
            return {'asset': asset, 'quantity': 0, 'price': price, 'type': 'hold', 'reason': "RiskManager restricted sell."}
        
        print(f"DEBUG: Sinal de VENDA confirmado com RSI: {rsi}")
        return {
            'asset': asset,
            'quantity': quantity_to_sell,
            'price': price,
            'type': 'sell',
            'reason': f"Death Cross detected - Short MA ({short_ma}) crossed below Long MA ({long_ma}) with RSI ({rsi})."
        }

    print("DEBUG: Nenhum sinal de compra ou venda detectado. Mantendo posição atual.")
    return {
        'asset': asset,
        'quantity': 0,
        'price': price,
        'type': 'hold',
        'reason': f"Hold - Short MA ({short_ma}) and Long MA ({long_ma}) do not confirm clear trend."
    }


# Função RSI
def calculate_rsi(series, period=10):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.iloc[-1] if not pd.isna(rsi.iloc[-1]) else 50
