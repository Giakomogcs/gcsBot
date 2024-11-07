from services.binance_client import get_consecutive_trades
from strategies.risk_manager import RiskManager
import pandas as pd
import pandas_ta as ta
import logging

# Configuração do logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger()

def calculate_indicators(df, short_ma_period=10, long_ma_period=60, rsi_period=10, volume_threshold=1.2):
    if len(df) < max(short_ma_period, long_ma_period):
        logger.warning("Dados insuficientes para calcular todos os indicadores. Aguardando mais dados...")
        return None, None, None, None

    # Calcula as Médias Móveis e RSI
    df['SMA_10'] = ta.sma(df['close'], length=short_ma_period)
    df['SMA_60'] = ta.sma(df['close'], length=long_ma_period)
    df['RSI'] = ta.rsi(df['close'], length=rsi_period)
    df['EMA_20'] = ta.ema(df['close'], length=20)
    df['EMA_50'] = ta.ema(df['close'], length=50)

    # Volume filtrado para evitar sinais em mercados sem volume
    df['Volume_Filter'] = df['volume'] > (volume_threshold * df['volume'].rolling(window=10).mean())

    # Verifica se os indicadores estão prontos para uso
    if df[['SMA_10', 'SMA_60', 'RSI', 'Volume_Filter', 'EMA_20', 'EMA_50']].iloc[-1].isna().any():
        logger.warning("Um ou mais indicadores contêm valores NaN. Verifique os dados históricos.")
        return None, None, None, None, None, None

    short_ma = df['SMA_10'].iloc[-1]
    long_ma = df['SMA_60'].iloc[-1]
    rsi = df['RSI'].iloc[-1]
    volume_filter = df['Volume_Filter'].iloc[-1]
    ema_20 = df['EMA_20'].iloc[-1]
    ema_50 = df['EMA_50'].iloc[-1]

    return short_ma, long_ma, rsi, volume_filter, ema_20, ema_50

def trading_decision(asset, price, portfolio_manager, df, volume_threshold=1.2):
    risk_manager = RiskManager(portfolio_manager)
    short_ma_period = 10
    long_ma_period = 70
    rsi_period = 10
    min_asset_quantity = 0.001
    max_trade_amount = 0.05  # Máximo de 5% da carteira em cada operação para diversificação

    base_asset = asset.replace('USDT', '')

    if len(df) < long_ma_period:
        logger.info("DEBUG: Dados insuficientes para calcular indicadores. Aguardando mais dados...")
        return {'asset': asset, 'quantity': 0, 'price': price, 'type': 'hold', 'reason': "Insufficient data for Long MA."}

    short_ma, long_ma, rsi, volume_filter, ema_20, ema_50 = calculate_indicators(df, short_ma_period, long_ma_period, rsi_period)

    if None in (short_ma, long_ma, rsi, volume_filter, ema_20, ema_50):
        return {'asset': asset, 'quantity': 0, 'price': price, 'type': 'hold', 'reason': "Indicators contain NaN values."}

    # Pontuações para condições de compra e venda
    buy_score = 0
    sell_score = 0

    # --------------------
    # Condições de Compra
    # --------------------
    logger.info("Analisando condições de compra...")

    # Volume alto - Máximo: 1 ponto
    if volume_filter:
        buy_score += 1
        logger.info("Condição de compra atendida: Volume alto. Pontuação: +1")
    else:
        # Adiciona pontuação proporcional se estiver próximo do limiar
        volume_proximity = df['volume'].iloc[-1] / (volume_threshold * df['volume'].rolling(window=10).mean().iloc[-1])
        buy_score += min(0.5 * volume_proximity, 0.5)
        logger.info(f"Volume próximo do limite, pontuação extra adicionada: +{min(0.5 * volume_proximity, 0.5):.2f}")

    # Short MA acima da Long MA - Máximo: 4 pontos
    ma_distance = short_ma - long_ma
    if ma_distance > 0:
        buy_score += min(4 * (ma_distance / long_ma), 4)
        logger.info(f"Condição de compra atendida: Short MA acima da Long MA com distância {ma_distance:.2f}. Pontuação: +{min(4 * (ma_distance / long_ma), 4):.2f}")
    else:
        # Pontuação proporcional para proximidade
        proximity_score = min(2 * (1 - (abs(ma_distance) / long_ma)), 2)
        buy_score += proximity_score
        logger.info(f"Short MA próximo da Long MA, pontuação extra adicionada: +{proximity_score:.2f}. Distância: {ma_distance:.2f}")

    # EMA_20 acima da EMA_50 - Máximo: 3 pontos
    ema_distance = ema_20 - ema_50
    if ema_distance > 0:
        buy_score += min(3 * (ema_distance / ema_50), 3)
        logger.info(f"Condição de compra atendida: EMA_20 acima da EMA_50 com distância {ema_distance:.2f}. Pontuação: +{min(3 * (ema_distance / ema_50), 3):.2f}")
    else:
        # Pontuação extra se próximo ao limiar
        proximity_score = min(1.5 * (1 - (abs(ema_distance) / ema_50)), 1.5)
        buy_score += proximity_score
        logger.info(f"EMA_20 próximo da EMA_50, pontuação extra adicionada: +{proximity_score:.2f}. Distância: {ema_distance:.2f}")

    # RSI baixo (< 55) - Máximo: 1 ponto
    if rsi < 55:
        buy_score += min(1 * ((55 - rsi) / 55), 1)
        logger.info(f"Condição de compra atendida: RSI ({rsi}) abaixo de 55. Pontuação: +{min(1 * ((55 - rsi) / 55), 1):.2f}")
    else:
        proximity_score = min(0.5 * ((60 - rsi) / 60), 0.5)
        buy_score += proximity_score
        logger.info(f"RSI próximo do limite, pontuação extra adicionada: +{proximity_score:.2f}")

    # Saldo de caixa suficiente - Máximo: 1 ponto
    if portfolio_manager.get_cash_balance() > (price * min_asset_quantity):
        buy_score += 1
        logger.info("Condição de compra atendida: Saldo de caixa suficiente. Pontuação: +1")
    else:
        logger.info("Condição de compra não atendida: Saldo de caixa insuficiente.")

    # --------------------
    # Condições de Venda
    # --------------------
    logger.info("Analisando condições de venda...")

    # RSI alto (> 60) - Máximo: 2 pontos
    if rsi > 60:
        sell_score += min(2 * ((rsi - 60) / 40), 2)
        logger.info(f"Condição de venda atendida: RSI ({rsi}) acima de 60. Pontuação: +{min(2 * ((rsi - 60) / 40), 2):.2f}")
    else:
        proximity_score = min(1 * ((rsi - 55) / 60), 1) if rsi > 55 else 0
        sell_score += proximity_score
        logger.info(f"RSI próximo do limite, pontuação extra adicionada: +{proximity_score:.2f}")

    # Short MA abaixo da Long MA - Máximo: 4 pontos
    if short_ma < long_ma:
        sell_score += min(4 * (abs(short_ma - long_ma) / long_ma), 4)
        logger.info(f"Condição de venda atendida: Short MA abaixo da Long MA com distância {short_ma - long_ma:.2f}. Pontuação: +{min(4 * (abs(short_ma - long_ma) / long_ma), 4):.2f}")
    else:
        proximity_score = min(2 * (1 - (abs(short_ma - long_ma) / long_ma)), 2)
        sell_score += proximity_score
        logger.info(f"Short MA próximo da Long MA, pontuação extra adicionada: +{proximity_score:.2f}")

    # EMA_20 abaixo da EMA_50 - Máximo: 3 pontos
    if ema_20 < ema_50:
        sell_score += min(3 * (abs(ema_20 - ema_50) / ema_50), 3)
        logger.info(f"Condição de venda atendida: EMA_20 abaixo da EMA_50 com distância {ema_20 - ema_50:.2f}. Pontuação: +{min(3 * (abs(ema_20 - ema_50) / ema_50), 3):.2f}")
    else:
        proximity_score = min(1.5 * (1 - (abs(ema_20 - ema_50) / ema_50)), 1.5)
        sell_score += proximity_score
        logger.info(f"EMA_20 próximo da EMA_50, pontuação extra adicionada: +{proximity_score:.2f}")

    # Quantidade suficiente para venda - Máximo: 1 ponto
    if portfolio_manager.get_balance(base_asset) > min_asset_quantity:
        sell_score += 1
        logger.info("Condição de venda atendida: Quantidade suficiente para venda. Pontuação: +1")
    else:
        logger.info("Condição de venda não atendida: Quantidade mínima para venda não atingida.")

    # Preço atual acima do preço médio de compra - Máximo: 1 ponto
    if price > portfolio_manager.assets.get(base_asset, {}).get('average_cost', 0):
        sell_score += 1
        logger.info("Condição de venda atendida: Preço atual acima do preço médio de compra. Pontuação: +1")
    else:
        logger.info(f"Condição de venda não atendida: Preço atual ({price}) não é maior que o preço médio de compra.")


    # Pontuação Máxima de Venda: 11 pontos

    # Define os limiares para compra e venda
    buy_threshold = 5.5  # Reduzido para 55% da pontuação máxima
    sell_threshold = 6  # Reduzido para 60% da pontuação máxima

    # Determina o valor de compra e venda com base no saldo disponível
    cash_balance = portfolio_manager.get_cash_balance()
    asset_quantity = portfolio_manager.get_balance(base_asset)
    quantity_to_buy = min((cash_balance * portfolio_manager.get_investment_percentage()) / price, max_trade_amount * asset_quantity)
    quantity_to_sell = min(asset_quantity * portfolio_manager.get_investment_percentage(), asset_quantity - min_asset_quantity, max_trade_amount * asset_quantity)

    # Executa a compra se a pontuação de compra for suficiente
    if buy_score >= buy_threshold and cash_balance >= price * quantity_to_buy:
        logger.info(f"Condições de compra atendidas com pontuação total {buy_score}/{buy_threshold}")
        if risk_manager.can_trade(asset, 'buy', quantity_to_buy, price, df):
            return {
                'asset': asset,
                'quantity': quantity_to_buy,
                'price': price,
                'type': 'buy',
                'reason': f"Buy conditions met with score {buy_score}"
            }
        else:
            logger.info("Compra bloqueada pelo RiskManager.")
    
    # Executa a venda se a pontuação de venda for suficiente
    if sell_score >= sell_threshold and asset_quantity >= min_asset_quantity:
        logger.info(f"Condições de venda atendidas com pontuação total {sell_score}/{sell_threshold}")
        if risk_manager.can_trade(asset, 'sell', quantity_to_sell, price, df):
            return {
                'asset': asset,
                'quantity': quantity_to_sell,
                'price': price,
                'type': 'sell',
                'reason': f"Sell conditions met with score {sell_score}"
            }
        else:
            logger.info("Venda bloqueada pelo RiskManager.")

    # Mantém a posição caso as condições não sejam atingidas
    logger.info(f"Nenhuma condição de compra ou venda foi suficientemente atendida (Pontuação de Compra: {buy_score}, Pontuação de Venda: {sell_score}). Mantendo posição.")
    return {
        'asset': asset,
        'quantity': 0,
        'price': price,
        'type': 'hold',
        'reason': "Hold - Pontuações insuficientes para compra ou venda"
    }
