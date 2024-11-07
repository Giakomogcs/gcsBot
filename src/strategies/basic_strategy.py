from services.binance_client import get_consecutive_trades
from strategies.risk_manager import RiskManager
import pandas as pd
import pandas_ta as ta
import logging

# Configuração do logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger()

# Configurações de lucro e perda
MIN_PROFIT_PERCENTAGE = 0.02  # 2% de lucro
STOP_LOSS_PERCENTAGE = 0.01  # 1% de perda

# Variáveis globais para armazenar o preço de compra/venda mais recente
last_buy_price = None
last_sell_price = None

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

    # Volume filtrado para sinais em mercados de menor volume
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

def trading_decision(asset, price, portfolio_manager, df, volume_threshold=1.4):
    global last_buy_price, last_sell_price
    risk_manager = RiskManager(portfolio_manager)
    short_ma_period = 10
    long_ma_period = 70
    rsi_period = 10
    min_asset_quantity = 0.001
    max_trade_amount = 0.05
    base_asset = asset.replace('USDT', '')

    if len(df) < long_ma_period:
        logger.info("DEBUG: Dados insuficientes para calcular indicadores. Aguardando mais dados...")
        return {'asset': asset, 'quantity': 0, 'price': price, 'type': 'hold', 'reason': "Insufficient data for Long MA."}

    short_ma, long_ma, rsi, volume_filter, ema_20, ema_50 = calculate_indicators(df, short_ma_period, long_ma_period, rsi_period)

    if None in (short_ma, long_ma, rsi, volume_filter, ema_20, ema_50):
        return {'asset': asset, 'quantity': 0, 'price': price, 'type': 'hold', 'reason': "Indicators contain NaN values."}

    # Pontuações para compra e venda
    buy_score = 0
    sell_score = 0

    # --------------------
    # Condições de Compra
    # --------------------
    logger.info("Analisando condições de compra...")

    # Volume alto - Pontuação ajustada
    if volume_filter:
        buy_score += 1
    else:
        volume_proximity = df['volume'].iloc[-1] / (volume_threshold * df['volume'].rolling(window=10).mean().iloc[-1])
        buy_score += min(0.5 * volume_proximity, 0.5)

    # Short MA acima da Long MA - Pontuação ajustada
    ma_distance = short_ma - long_ma
    if ma_distance > 0:
        buy_score += min(3 * (ma_distance / long_ma), 3)
    else:
        proximity_score = min(1.5 * (1 - (abs(ma_distance) / long_ma)), 1.5)
        buy_score += proximity_score

    # EMA_20 acima da EMA_50 - Pontuação ajustada
    ema_distance = ema_20 - ema_50
    if ema_distance > 0:
        buy_score += min(2 * (ema_distance / ema_50), 2)
    else:
        proximity_score = min(1 * (1 - (abs(ema_distance) / ema_50)), 1)
        buy_score += proximity_score

    # RSI baixo (< 60) - Pontuação ajustada
    if rsi < 60:
        buy_score += min(0.75 * ((60 - rsi) / 60), 0.75)

    # Saldo de caixa suficiente
    if portfolio_manager.get_cash_balance() > (price * min_asset_quantity):
        buy_score += 1

    # --------------------
    # Condições de Venda
    # --------------------
    logger.info("Analisando condições de venda...")

    # RSI alto (> 60) - Pontuação ajustada
    if rsi > 60:
        sell_score += min(1.5 * ((rsi - 60) / 40), 1.5)

    # Short MA abaixo da Long MA - Pontuação ajustada
    if short_ma < long_ma:
        sell_score += min(3 * (abs(short_ma - long_ma) / long_ma), 3)
    else:
        proximity_score = min(1.5 * (1 - (abs(short_ma - long_ma) / long_ma)), 1.5)
        sell_score += proximity_score

    # EMA_20 abaixo da EMA_50 - Pontuação ajustada
    if ema_20 < ema_50:
        sell_score += min(2 * (abs(ema_20 - ema_50) / ema_50), 2)
    else:
        proximity_score = min(1 * (1 - (abs(ema_distance) / ema_50)), 1)
        sell_score += proximity_score

    # Quantidade suficiente para venda
    if portfolio_manager.get_balance(base_asset) > min_asset_quantity:
        sell_score += 1

    # Define os limiares para compra e venda
    buy_threshold = 4.0
    sell_threshold = 5.0

    cash_balance = portfolio_manager.get_cash_balance()
    asset_quantity = portfolio_manager.get_balance(base_asset)
    quantity_to_buy = min((cash_balance * portfolio_manager.get_investment_percentage()) / price, max_trade_amount * asset_quantity)
    quantity_to_sell = min(asset_quantity * portfolio_manager.get_investment_percentage(), asset_quantity - min_asset_quantity, max_trade_amount * asset_quantity)

    # Estratégia de Compra
    if buy_score >= buy_threshold and cash_balance >= price * quantity_to_buy:
        logger.info(f"Condições de compra atendidas com pontuação total {buy_score}/{buy_threshold}")
        
        # Salva o preço de compra mais recente
        last_buy_price = price
        
        if risk_manager.can_trade(asset, 'buy', quantity_to_buy, price, df):
            return {
                'asset': asset,
                'quantity': quantity_to_buy,
                'price': price,
                'type': 'buy',
                'reason': f"Buy conditions met with score {buy_score}"
            }

    # Estratégia de Venda com Meta de Lucro e Stop Loss
    if sell_score >= sell_threshold and asset_quantity >= min_asset_quantity:
        logger.info(f"Condições de venda atendidas com pontuação total {sell_score}/{sell_threshold}")

        # Verifica o lucro ou perda potencial com base no preço de compra mais recente
        if last_buy_price:
            potential_profit = (price - last_buy_price) / last_buy_price
            
            # Condição de venda para garantir lucro
            if potential_profit >= MIN_PROFIT_PERCENTAGE:
                logger.info(f"Condição de lucro atendida: lucro de {potential_profit * 100:.2f}%")
                last_sell_price = price
                if risk_manager.can_trade(asset, 'sell', quantity_to_sell, price, df):
                    return {
                        'asset': asset,
                        'quantity': quantity_to_sell,
                        'price': price,
                        'type': 'sell',
                        'reason': f"Sell for profit with {potential_profit * 100:.2f}% profit"
                    }
            
            # Condição de venda para stop loss
            elif potential_profit <= -STOP_LOSS_PERCENTAGE:
                logger.info(f"Condição de stop loss atingida: perda de {potential_profit * 100:.2f}%")
                last_sell_price = price
                if risk_manager.can_trade(asset, 'sell', quantity_to_sell, price, df):
                    return {
                        'asset': asset,
                        'quantity': quantity_to_sell,
                        'price': price,
                        'type': 'sell',
                        'reason': f"Sell for stop loss with {potential_profit * 100:.2f}% loss"
                    }

    logger.info(f"Posição mantida (Compra: {buy_score}, Venda: {sell_score}).")
    return {
        'asset': asset,
        'quantity': 0,
        'price': price,
        'type': 'hold',
        'reason': "Hold - Pontuações insuficientes para compra ou venda"
    }
